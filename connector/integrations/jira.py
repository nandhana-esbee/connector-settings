import os
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
import httpx


@dataclass
class JiraSettings:
    """
    Configuration settings for Atlassian Jira integration.
    Supports API Token and OAuth 2.0 authentication configurations,
    with comprehensive project retrieval capabilities.
    """
    server_url: Optional[str] = None
    user_email: Optional[str] = None
    api_token: Optional[str] = None
    project_key: Optional[str] = None

    @classmethod
    def from_env(cls) -> "JiraSettings":
        """Load Jira settings from environment variables."""
        return cls(
            server_url=os.getenv("JIRA_SERVER_URL"),
            user_email=os.getenv("JIRA_USER_EMAIL"),
            api_token=os.getenv("JIRA_API_TOKEN"),
            project_key=os.getenv("JIRA_DEFAULT_PROJECT_KEY"),
        )

    def is_configured(self) -> bool:
        """Check if minimum required settings for Jira are present."""
        return bool(self.server_url and self.api_token and self.user_email)

    def to_dict(self, mask_secrets: bool = True) -> Dict[str, Any]:
        """Return dictionary representation of Jira settings."""
        token = "********" if mask_secrets and self.api_token else self.api_token
        return {
            "server_url": self.server_url,
            "user_email": self.user_email,
            "api_token": token,
            "project_key": self.project_key,
            "is_configured": self.is_configured(),
        }

    def _get_auth_headers(self) -> tuple[tuple[str, str], dict[str, str]]:
        """Return auth tuple and common headers."""
        auth = (self.user_email or "", self.api_token or "")
        headers = {
            "Accept": "application/json",
            "User-Agent": "Connector-Module/0.2.0",
        }
        return auth, headers

    async def fetch_all_projects(self) -> Dict[str, Any]:
        """
        Fetch all available Jira projects with complete metadata (key, name, id,
        projectTypeKey, lead, description, issueTypes, category, etc.).
        """
        if not self.is_configured():
            return {
                "success": False,
                "error": "Jira is not configured. Server URL, User Email, and API Token are required.",
                "total": 0,
                "projects": [],
            }

        base_url = (self.server_url or "").rstrip("/")
        auth, headers = self._get_auth_headers()
        projects: List[Dict[str, Any]] = []

        async with httpx.AsyncClient(timeout=20.0) as client:
            try:
                # 1. Try paginated Jira Cloud /rest/api/3/project/search endpoint
                search_url = f"{base_url}/rest/api/3/project/search"
                start_at = 0
                max_results = 50
                is_search_supported = True

                while is_search_supported:
                    params = {
                        "startAt": start_at,
                        "maxResults": max_results,
                        "expand": "description,lead,issueTypes,url,projectKeys,insight",
                    }
                    resp = await client.get(search_url, auth=auth, headers=headers, params=params)

                    if resp.status_code == 200:
                        data = resp.json()
                        values = data.get("values", [])
                        for p in values:
                            projects.append(self._format_project(p, base_url))

                        total = data.get("total", len(projects))
                        is_last = data.get("isLast", (start_at + len(values) >= total))
                        if is_last or not values:
                            break
                        start_at += len(values)
                    elif resp.status_code == 404:
                        # Endpoint not supported (Server/Data Center or older API)
                        is_search_supported = False
                        break
                    elif resp.status_code in (401, 403):
                        return {
                            "success": False,
                            "error": f"Authentication failed (Status {resp.status_code}). Check your Email and API Token.",
                            "total": 0,
                            "projects": [],
                        }
                    else:
                        return {
                            "success": False,
                            "error": f"Failed to fetch projects (Status {resp.status_code}): {resp.text}",
                            "total": 0,
                            "projects": [],
                        }

                # 2. Fallback to /rest/api/3/project or /rest/api/2/project if search not available
                if not is_search_supported:
                    for api_ver in ("3", "2"):
                        fallback_url = f"{base_url}/rest/api/{api_ver}/project"
                        resp = await client.get(
                            fallback_url,
                            auth=auth,
                            headers=headers,
                            params={"expand": "description,lead,issueTypes,url,projectKeys"}
                        )
                        if resp.status_code == 200:
                            raw_projects = resp.json()
                            if isinstance(raw_projects, list):
                                projects = [self._format_project(p, base_url) for p in raw_projects]
                            break

                return {
                    "success": True,
                    "total": len(projects),
                    "projects": projects,
                }

            except Exception as e:
                return {
                    "success": False,
                    "error": f"Exception while fetching Jira projects: {str(e)}",
                    "total": 0,
                    "projects": [],
                }

    def _format_project(self, raw: Dict[str, Any], base_url: str) -> Dict[str, Any]:
        """Format and sanitize a raw Jira project response dictionary."""
        lead_data = raw.get("lead") or {}
        lead_info = None
        if isinstance(lead_data, dict) and lead_data:
            lead_info = {
                "displayName": lead_data.get("displayName") or lead_data.get("name"),
                "accountId": lead_data.get("accountId") or lead_data.get("key"),
                "emailAddress": lead_data.get("emailAddress"),
                "active": lead_data.get("active", True),
            }

        # Issue types
        issue_types_raw = raw.get("issueTypes") or []
        issue_types = []
        if isinstance(issue_types_raw, list):
            for it in issue_types_raw:
                if isinstance(it, dict):
                    issue_types.append({
                        "id": it.get("id"),
                        "name": it.get("name"),
                        "subtask": it.get("subtask", False),
                        "description": it.get("description"),
                        "iconUrl": it.get("iconUrl"),
                    })

        category = raw.get("projectCategory")
        category_name = category.get("name") if isinstance(category, dict) else None

        key = raw.get("key", "")
        project_url = raw.get("url") or f"{base_url}/browse/{key}" if key else ""

        return {
            "id": raw.get("id"),
            "key": key,
            "name": raw.get("name"),
            "projectTypeKey": raw.get("projectTypeKey", "software"),
            "style": raw.get("style", "classic"),
            "description": raw.get("description") or "",
            "lead": lead_info,
            "category": category_name,
            "issueTypesCount": len(issue_types),
            "issueTypes": issue_types,
            "avatarUrls": raw.get("avatarUrls"),
            "url": project_url,
            "isPrivate": raw.get("isPrivate", False),
            "simplified": raw.get("simplified", False),
        }

    async def test_connection(self) -> Dict[str, Any]:
        """
        Test the connection to Atlassian Jira:
        1. Authenticate with the user account ('myself' endpoint)
        2. Fetch all project details across the Jira workspace
        """
        if not self.is_configured():
            return {
                "success": False,
                "error": "Jira is not configured. Server URL, User Email, and API Token are required.",
                "details": None,
            }

        base_url = (self.server_url or "").rstrip("/")
        auth, headers = self._get_auth_headers()
        myself_url = f"{base_url}/rest/api/3/myself"

        async with httpx.AsyncClient(timeout=20.0) as client:
            try:
                resp = await client.get(myself_url, auth=auth, headers=headers)
                if resp.status_code == 404:
                    myself_url = f"{base_url}/rest/api/2/myself"
                    resp = await client.get(myself_url, auth=auth, headers=headers)

                if resp.status_code == 200:
                    user_data = resp.json()
                    user_name = user_data.get("displayName") or user_data.get("name") or self.user_email
                    account_id = user_data.get("accountId") or user_data.get("key")

                    # Fetch all project details!
                    projects_result = await self.fetch_all_projects()

                    return {
                        "success": True,
                        "message": f"Successfully authenticated with Jira as '{user_name}'. Fetched {projects_result.get('total', 0)} project(s).",
                        "user": {
                            "displayName": user_name,
                            "email": user_data.get("emailAddress", self.user_email),
                            "accountId": account_id,
                            "active": user_data.get("active", True),
                            "timeZone": user_data.get("timeZone"),
                        },
                        "total_projects": projects_result.get("total", 0),
                        "projects": projects_result.get("projects", []),
                    }
                elif resp.status_code in (401, 403):
                    return {
                        "success": False,
                        "error": f"Authentication failed (Status {resp.status_code}). Check your Email and API Token.",
                        "status_code": resp.status_code,
                    }
                else:
                    return {
                        "success": False,
                        "error": f"Jira returned unexpected status {resp.status_code}: {resp.text}",
                        "status_code": resp.status_code,
                    }
            except Exception as e:
                return {
                    "success": False,
                    "error": f"Failed to connect to Jira server ({base_url}): {str(e)}",
                }
