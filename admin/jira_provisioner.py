import os
import json
import asyncio
import httpx
from typing import Dict, Any, List, Optional
from pathlib import Path

from connector import ConnectorSettings


class JiraAdminProvisioner:
    """
    Admin Provisioner for Atlassian Jira.
    Connects to the user's Jira workspace using credentials in .env / ConnectorSettings,
    reads JSON specifications from the 'data/' folder, and automatically provisions 
    Jira Projects, Components, Versions, and User Stories/Issues.
    """

    def __init__(self, settings: Optional[ConnectorSettings] = None, data_dir: Optional[str] = None):
        admin_folder = Path(__file__).resolve().parent
        admin_env_file = admin_folder / ".env"
        
        if admin_env_file.exists():
            admin_settings = ConnectorSettings.load(env_file=str(admin_env_file))
            if admin_settings.jira.is_configured():
                self.settings = admin_settings
            else:
                self.settings = settings or admin_settings
        elif settings and settings.jira.is_configured():
            self.settings = settings
        else:
            self.settings = settings or ConnectorSettings.load(env_file=".env")

        root_dir = admin_folder.parent
        self.data_dir = Path(data_dir) if data_dir else (root_dir / "data")



    def _get_auth(self) -> tuple[tuple[str, str], dict[str, str], str]:
        """Return auth tuple, headers dict, and base_url."""
        if not self.settings.jira.is_configured():
            raise RuntimeError(
                "Jira credentials are not configured. Please set JIRA_SERVER_URL, JIRA_USER_EMAIL, and JIRA_API_TOKEN in .env."
            )
        
        server_url = (self.settings.jira.server_url or "").rstrip("/")
        auth = (self.settings.jira.user_email or "", self.settings.jira.api_token or "")
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Connector-Admin-Provisioner/1.0",
        }
        return auth, headers, server_url

    def _text_to_adf(self, text: str) -> Dict[str, Any]:
        """Convert multiline plain text to Atlassian Document Format (ADF)."""
        paragraphs = (text or "").split("\n")
        content_nodes = []
        for p in paragraphs:
            if not p.strip():
                content_nodes.append({"type": "paragraph", "content": []})
            else:
                content_nodes.append({
                    "type": "paragraph",
                    "content": [{"type": "text", "text": p}],
                })
        if not content_nodes:
            content_nodes = [{"type": "paragraph", "content": [{"type": "text", "text": "Provisioned via Admin Tool"}]}]

        return {
            "version": 1,
            "type": "doc",
            "content": content_nodes,
        }

    def load_json_from_data(self, file_name: str = "jira_projects.json") -> Dict[str, Any]:
        """Load JSON file from the data/ directory."""
        file_path = self.data_dir / file_name
        if not file_path.exists():
            raise FileNotFoundError(f"JSON file '{file_name}' not found in data folder: {self.data_dir}")

        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)

    async def create_project(
        self,
        key: str,
        name: str,
        project_type_key: str = "software",
        description: str = "",
        lead_account_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new project in Jira or verify if it already exists."""
        auth, headers, base_url = self._get_auth()
        key_upper = key.strip().upper()

        async with httpx.AsyncClient(timeout=25.0) as client:
            # 1. Check if project already exists
            check_url = f"{base_url}/rest/api/3/project/{key_upper}"
            check_resp = await client.get(check_url, auth=auth, headers=headers)
            if check_resp.status_code == 200:
                p_data = check_resp.json()
                return {
                    "success": True,
                    "action": "already_exists",
                    "key": key_upper,
                    "id": p_data.get("id"),
                    "name": p_data.get("name"),
                    "message": f"Project '{key_upper}' already exists in Jira.",
                }

            # 2. Get current user's account ID if lead_account_id is not supplied
            if not lead_account_id:
                me_resp = await client.get(f"{base_url}/rest/api/3/myself", auth=auth, headers=headers)
                if me_resp.status_code == 200:
                    lead_account_id = me_resp.json().get("accountId")

            # 3. Create project payload
            payload = {
                "key": key_upper,
                "name": name.strip(),
                "projectTypeKey": project_type_key.lower(),
                "description": description,
                "leadAccountId": lead_account_id,
            }

            create_url = f"{base_url}/rest/api/3/project"
            resp = await client.post(create_url, auth=auth, headers=headers, json=payload)

            if resp.status_code in (200, 201):
                p_res = resp.json()
                return {
                    "success": True,
                    "action": "created",
                    "key": key_upper,
                    "id": p_res.get("id"),
                    "name": name,
                    "message": f"Project '{key_upper}' successfully created in Jira.",
                }
            else:
                err_msg = resp.text
                try:
                    err_json = resp.json()
                    err_msg = str(err_json.get("errors") or err_json.get("errorMessages") or err_msg)
                except Exception:
                    pass

                # If error indicates project key exists, treat as existing
                if "already" in err_msg.lower() or "exists" in err_msg.lower():
                    return {
                        "success": True,
                        "action": "already_exists",
                        "key": key_upper,
                        "message": f"Project '{key_upper}' already exists in Jira.",
                    }

                return {
                    "success": False,
                    "action": "failed",
                    "key": key_upper,
                    "error": f"Failed to create project '{key_upper}' ({resp.status_code}): {err_msg}",
                }

    async def create_component(self, project_key: str, name: str, description: str = "") -> Dict[str, Any]:
        """Create a component under a Jira project."""
        auth, headers, base_url = self._get_auth()
        url = f"{base_url}/rest/api/3/component"
        payload = {
            "name": name.strip(),
            "description": description,
            "project": project_key.strip().upper(),
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, auth=auth, headers=headers, json=payload)
            if resp.status_code in (200, 201):
                res_data = resp.json()
                return {"success": True, "id": res_data.get("id"), "name": name}
            elif resp.status_code == 400 and "exists" in resp.text.lower():
                return {"success": True, "name": name, "message": "Component already exists."}
            else:
                return {"success": False, "error": resp.text}

    async def create_version(self, project_key: str, name: str, description: str = "") -> Dict[str, Any]:
        """Create a version under a Jira project."""
        auth, headers, base_url = self._get_auth()
        url = f"{base_url}/rest/api/3/version"
        payload = {
            "name": name.strip(),
            "description": description,
            "project": project_key.strip().upper(),
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, auth=auth, headers=headers, json=payload)
            if resp.status_code in (200, 201):
                res_data = resp.json()
                return {"success": True, "id": res_data.get("id"), "name": name}
            elif resp.status_code == 400 and "exists" in resp.text.lower():
                return {"success": True, "name": name, "message": "Version already exists."}
            else:
                return {"success": False, "error": resp.text}

    async def create_issue(
        self,
        project_key: str,
        summary: str,
        description: str = "",
        issue_type: str = "Story",
        component_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create an Issue or User Story in Jira."""
        auth, headers, base_url = self._get_auth()
        url = f"{base_url}/rest/api/3/issue"
        
        fields: Dict[str, Any] = {
            "project": {"key": project_key.strip().upper()},
            "summary": summary.strip(),
            "description": self._text_to_adf(description),
            "issuetype": {"name": issue_type.strip() or "Story"},
        }

        if component_name:
            fields["components"] = [{"name": component_name.strip()}]

        payload = {"fields": fields}

        async with httpx.AsyncClient(timeout=25.0) as client:
            resp = await client.post(url, auth=auth, headers=headers, json=payload)
            if resp.status_code in (200, 201):
                res_data = resp.json()
                issue_key = res_data.get("key")
                browse_url = f"{base_url}/browse/{issue_key}" if issue_key else ""
                return {"success": True, "key": issue_key, "id": res_data.get("id"), "url": browse_url}
            else:
                # Try fallback if issue type name varies (e.g. Task or Story)
                if resp.status_code == 400:
                    for fallback in ("Task", "Story", "Bug"):
                        if fallback != issue_type:
                            fields["issuetype"]["name"] = fallback
                            retry_resp = await client.post(url, auth=auth, headers=headers, json={"fields": fields})
                            if retry_resp.status_code in (200, 201):
                                rdata = retry_resp.json()
                                issue_key = rdata.get("key")
                                return {"success": True, "key": issue_key, "id": rdata.get("id"), "url": f"{base_url}/browse/{issue_key}"}

                return {"success": False, "error": f"Status {resp.status_code}: {resp.text}"}

    def _normalize_project_spec(self, proj: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize different JSON schemas (standard, fundex_jira_proj, AppMiner, etc.)."""
        key = proj.get("key") or proj.get("projectKey") or ""
        name = proj.get("name") or proj.get("projectName") or ""
        description = proj.get("description") or proj.get("goal") or ""
        
        components = list(proj.get("components", []))
        versions = list(proj.get("versions", []))
        issues = list(proj.get("issues", []))

        # Handle epics -> components & stories -> issues
        if "epics" in proj and isinstance(proj["epics"], list):
            for epic in proj["epics"]:
                epic_name = epic.get("name") or epic.get("epicKey", "Epic")
                epic_desc = epic.get("description", "")
                components.append({"name": epic_name, "description": epic_desc})
                
                for story in epic.get("stories", []):
                    issues.append({
                        "summary": story.get("summary"),
                        "description": story.get("description", ""),
                        "issue_type": story.get("type") or story.get("issue_type", "Story"),
                        "component": epic_name,
                    })

        return {
            "key": key,
            "name": name,
            "projectTypeKey": proj.get("projectTypeKey", "software"),
            "description": description,
            "components": components,
            "versions": versions,
            "issues": issues,
        }

    async def provision_from_json_data(self, data: Any, source_name: str = "custom_json") -> Dict[str, Any]:
        """
        Provision Jira projects directly from raw JSON data (dict or list).
        Supports standard project schema, fundex_jira_proj schema, and AppMiner schema.
        """
        projects_list = []

        # 1. Handle AppMiner schema format (sites / flow_summaries)
        if isinstance(data, dict) and "sites" in data:
            for site in data.get("sites", []):
                domain = site.get("domain") or site.get("name", "Site")
                clean_domain = "".join(c for c in domain if c.isalnum()).upper()
                proj_key = (clean_domain[:8] or "SITE")

                app_ctx = site.get("app_context", {})
                desc = app_ctx.get("text", f"Site project for {domain}")

                issues = []
                for summary_item in site.get("flow_summaries", []):
                    flow_name = summary_item.get("flow_name", "Flow")
                    goal = summary_item.get("goal", "")
                    story_text = summary_item.get("text", "")
                    full_desc = f"Goal: {goal}\n\n{story_text}" if goal else story_text

                    issues.append({
                        "summary": f"{flow_name}: {goal or 'User Flow'}",
                        "description": full_desc,
                        "issue_type": "Story",
                        "component": flow_name,
                    })

                components = list({iss["component"] for iss in issues if iss.get("component")})

                projects_list.append({
                    "key": proj_key,
                    "name": domain,
                    "projectTypeKey": "software",
                    "description": desc,
                    "components": [{"name": c} for c in components],
                    "versions": [{"name": "v1.0.0"}],
                    "issues": issues,
                })
        elif isinstance(data, dict) and "projects" in data:
            projects_list = data["projects"]
        elif isinstance(data, list):
            projects_list = data
        elif isinstance(data, dict):
            projects_list = [data]

        report = {
            "source": source_name,
            "total_projects": len(projects_list),
            "projects_created": 0,
            "components_created": 0,
            "versions_created": 0,
            "issues_created": 0,
            "details": [],
        }

        for raw_proj in projects_list:
            proj = self._normalize_project_spec(raw_proj)
            key = proj.get("key")
            name = proj.get("name")
            if not key or not name:
                continue

            proj_res = await self.create_project(
                key=key,
                name=name,
                project_type_key=proj.get("projectTypeKey", "software"),
                description=proj.get("description", ""),
            )

            proj_summary = {
                "key": key,
                "name": name,
                "project_status": proj_res,
                "components": [],
                "versions": [],
                "issues": [],
            }

            if proj_res.get("success"):
                report["projects_created"] += 1

                # Provision components
                for comp in proj.get("components", []):
                    c_name = comp.get("name") if isinstance(comp, dict) else comp
                    c_desc = comp.get("description", "") if isinstance(comp, dict) else ""
                    if c_name:
                        c_res = await self.create_component(key, c_name, c_desc)
                        proj_summary["components"].append(c_res)
                        if c_res.get("success"):
                            report["components_created"] += 1

                # Provision versions
                for ver in proj.get("versions", []):
                    v_name = ver.get("name") if isinstance(ver, dict) else ver
                    v_desc = ver.get("description", "") if isinstance(ver, dict) else ""
                    if v_name:
                        v_res = await self.create_version(key, v_name, v_desc)
                        proj_summary["versions"].append(v_res)
                        if v_res.get("success"):
                            report["versions_created"] += 1

                # Provision issues
                for iss in proj.get("issues", []):
                    summary = iss.get("summary")
                    if summary:
                        i_res = await self.create_issue(
                            project_key=key,
                            summary=summary,
                            description=iss.get("description", ""),
                            issue_type=iss.get("issue_type", "Story"),
                            component_name=iss.get("component"),
                        )
                        proj_summary["issues"].append(i_res)
                        if i_res.get("success"):
                            report["issues_created"] += 1

            report["details"].append(proj_summary)

        return {
            "success": True,
            "message": f"Successfully processed {report['total_projects']} project specification(s) from '{source_name}'.",
            "report": report,
        }


    async def provision_from_data_file(self, file_name: str = "jira_projects.json") -> Dict[str, Any]:
        """
        Loads specified JSON file from data/ directory and provisions all projects into Jira.
        """
        data = self.load_json_from_data(file_name)
        return await self.provision_from_json_data(data, source_name=f"data/{file_name}")

