import os
import urllib.parse
from typing import Optional, Dict, Any, List
import httpx

from ..oauth_store import OAuthStore, JiraConnectionRecord


class JiraOAuthService:
    """
    Atlassian Jira Cloud OAuth 2.0 (3LO) service handler.
    Manages authorization URLs, token exchanges, automatic token refreshes,
    cloud resource discovery, project retrieval, and issue creation.
    """

    AUTH_BASE_URL = "https://auth.atlassian.com/authorize"
    TOKEN_URL = "https://auth.atlassian.com/oauth/token"
    ACCESSIBLE_RESOURCES_URL = "https://api.atlassian.com/oauth/token/accessible-resources"
    JIRA_API_BASE = "https://api.atlassian.com/ex/jira"

    DEFAULT_SCOPES = [
        "read:jira-work",
        "manage:jira-project",
        "manage:jira-configuration",
        "read:jira-user",
        "write:jira-work",
        "manage:jira-webhook",
        "read:me",
        "offline_access",
    ]

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        redirect_uri: Optional[str] = None,
        scopes: Optional[List[str]] = None,
        store: Optional[OAuthStore] = None,
    ):
        self.client_id = client_id or os.getenv("JIRA_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("JIRA_CLIENT_SECRET")
        self.redirect_uri = redirect_uri or os.getenv("JIRA_REDIRECT_URI", "http://127.0.0.1:8000/auth/jira/callback")
        env_scopes = os.getenv("JIRA_OAUTH_SCOPES")
        if scopes:
            self.scopes = scopes
        elif env_scopes:
            self.scopes = env_scopes.split()
        else:
            self.scopes = self.DEFAULT_SCOPES
        self.store = store or OAuthStore()

    def is_configured(self) -> bool:
        """Checks whether the minimum required OAuth client environment variables are set."""
        return bool(self.client_id and self.client_secret and self.redirect_uri)

    def get_authorization_url(self, state: str) -> str:
        """
        Generates the Atlassian OAuth 2.0 (3LO) authorization URL.
        """
        if not self.is_configured():
            raise ValueError(
                "Jira OAuth 2.0 is not configured. JIRA_CLIENT_ID, JIRA_CLIENT_SECRET, and JIRA_REDIRECT_URI must be set."
            )

        params = {
            "audience": "api.atlassian.com",
            "client_id": self.client_id,
            "scope": " ".join(self.scopes),
            "redirect_uri": self.redirect_uri,
            "state": state,
            "response_type": "code",
            "prompt": "consent",
        }
        return f"{self.AUTH_BASE_URL}?{urllib.parse.urlencode(params)}"

    async def exchange_code(self, code: str) -> Dict[str, Any]:
        """
        Exchanges the authorization code for access and refresh tokens.
        """
        payload = {
            "grant_type": "authorization_code",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "redirect_uri": self.redirect_uri,
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                self.TOKEN_URL,
                json=payload,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
            )
            if resp.status_code != 200:
                raise RuntimeError(
                    f"Failed to exchange Jira OAuth authorization code (Status {resp.status_code}): {resp.text}"
                )
            return resp.json()

    async def get_accessible_resources(self, access_token: str) -> List[Dict[str, Any]]:
        """
        Retrieves Jira Cloud sites and cloud IDs accessible to the authenticated token.
        """
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "User-Agent": "Connector-Jira-OAuth/1.0",
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(self.ACCESSIBLE_RESOURCES_URL, headers=headers)
            if resp.status_code != 200:
                raise RuntimeError(
                    f"Failed to retrieve accessible Jira resources (Status {resp.status_code}): {resp.text}"
                )
            return resp.json()

    async def get_myself(self, access_token: str, cloud_id: str) -> Dict[str, Any]:
        """
        Retrieves user profile details for the connected Atlassian account.
        """
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "User-Agent": "Connector-Jira-OAuth/1.0",
        }
        url = f"{self.JIRA_API_BASE}/{cloud_id}/rest/api/3/myself"

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 404:
                # Fallback to v2
                url = f"{self.JIRA_API_BASE}/{cloud_id}/rest/api/2/myself"
                resp = await client.get(url, headers=headers)

            if resp.status_code != 200:
                # Try User identity API /me endpoint (supported with read:me scope)
                try:
                    me_resp = await client.get("https://api.atlassian.com/me", headers=headers)
                    if me_resp.status_code == 200:
                        me_data = me_resp.json()
                        return {
                            "displayName": me_data.get("name") or me_data.get("nickname"),
                            "emailAddress": me_data.get("email"),
                            "accountId": me_data.get("account_id"),
                            "avatarUrls": {"48x48": me_data.get("picture")},
                        }
                except Exception:
                    pass
                return {}
            return resp.json()

    async def ensure_valid_token(self, user_id: str) -> JiraConnectionRecord:
        """
        Checks if the stored access token for the given user is valid.
        If expired (or about to expire), refreshes it using the refresh token.
        """
        conn = self.store.get_connection(user_id)
        if not conn:
            raise ValueError(f"No Jira connection found for user '{user_id}'.")

        if not conn.is_expired(buffer_seconds=90.0):
            return conn

        # Attempt token refresh
        if not conn.refresh_token:
            raise ValueError("Token is expired and no refresh token is available. Please re-authorize.")

        payload = {
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": conn.refresh_token,
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                self.TOKEN_URL,
                json=payload,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
            )
            if resp.status_code != 200:
                raise RuntimeError(
                    f"Failed to refresh Jira access token (Status {resp.status_code}). Please reconnect."
                )
            token_data = resp.json()

        new_access = token_data.get("access_token")
        new_refresh = token_data.get("refresh_token") or conn.refresh_token
        expires_in = token_data.get("expires_in", 3600)

        self.store.update_tokens(
            user_id=user_id,
            access_token=new_access,
            refresh_token=new_refresh,
            expires_in=expires_in,
        )

        refreshed_conn = self.store.get_connection(user_id)
        if not refreshed_conn:
            raise ValueError("Failed to retrieve updated connection after refresh.")
        return refreshed_conn

    def _text_to_adf(self, text: str) -> Dict[str, Any]:
        """Converts plain text or multiline text into Atlassian Document Format (ADF)."""
        paragraphs = (text or "").split("\n")
        content_nodes = []
        for p in paragraphs:
            if not p:
                content_nodes.append({"type": "paragraph", "content": []})
            else:
                content_nodes.append({
                    "type": "paragraph",
                    "content": [{"type": "text", "text": p}],
                })

        if not content_nodes:
            content_nodes = [{"type": "paragraph", "content": [{"type": "text", "text": "Generated from application"}]}]

        return {
            "version": 1,
            "type": "doc",
            "content": content_nodes,
        }

    async def fetch_projects(self, user_id: str) -> Dict[str, Any]:
        """
        Retrieves projects available to the connected Jira user.
        """
        conn = await self.ensure_valid_token(user_id)
        if not conn.cloud_id:
            return {"success": False, "error": "Missing Cloud ID for connected Jira site.", "total": 0, "projects": []}

        headers = {
            "Authorization": f"Bearer {conn.access_token}",
            "Accept": "application/json",
            "User-Agent": "Connector-Jira-OAuth/1.0",
        }

        base_url = f"{self.JIRA_API_BASE}/{conn.cloud_id}"
        projects: List[Dict[str, Any]] = []

        async with httpx.AsyncClient(timeout=20.0) as client:
            try:
                search_url = f"{base_url}/rest/api/3/project/search"
                start_at = 0
                max_results = 50
                is_search_supported = True

                while is_search_supported:
                    params = {
                        "startAt": start_at,
                        "maxResults": max_results,
                        "expand": "description,lead,issueTypes,url,projectKeys",
                    }
                    resp = await client.get(search_url, headers=headers, params=params)

                    if resp.status_code == 200:
                        data = resp.json()
                        values = data.get("values", [])
                        for p in values:
                            projects.append(self._format_project(p, conn.site_url or ""))

                        total = data.get("total", len(projects))
                        is_last = data.get("isLast", (start_at + len(values) >= total))
                        if is_last or not values:
                            break
                        start_at += len(values)
                    elif resp.status_code == 404:
                        is_search_supported = False
                        break
                    elif resp.status_code in (401, 403):
                        return {
                            "success": False,
                            "error": f"Authorization error querying Jira projects (Status {resp.status_code}).",
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

                # Fallback if search endpoint returned 404
                if not is_search_supported:
                    for api_ver in ("3", "2"):
                        fallback_url = f"{base_url}/rest/api/{api_ver}/project"
                        resp = await client.get(
                            fallback_url,
                            headers=headers,
                            params={"expand": "description,lead,issueTypes,url,projectKeys"},
                        )
                        if resp.status_code == 200:
                            raw_projects = resp.json()
                            if isinstance(raw_projects, list):
                                projects = [self._format_project(p, conn.site_url or "") for p in raw_projects]
                            break

                return {
                    "success": True,
                    "total": len(projects),
                    "projects": projects,
                }
            except Exception as e:
                return {
                    "success": False,
                    "error": f"Error fetching projects: {str(e)}",
                    "total": 0,
                    "projects": [],
                }

    def _format_project(self, raw: Dict[str, Any], site_url: str) -> Dict[str, Any]:
        """Format and sanitize a project object."""
        lead_data = raw.get("lead") or {}
        lead_info = None
        if isinstance(lead_data, dict) and lead_data:
            lead_info = {
                "displayName": lead_data.get("displayName") or lead_data.get("name"),
                "accountId": lead_data.get("accountId") or lead_data.get("key"),
                "emailAddress": lead_data.get("emailAddress"),
                "active": lead_data.get("active", True),
            }

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

        key = raw.get("key", "")
        project_url = (
            raw.get("url")
            or (f"{site_url.rstrip('/')}/browse/{key}" if site_url and key else "")
        )

        return {
            "id": raw.get("id"),
            "key": key,
            "name": raw.get("name"),
            "projectTypeKey": raw.get("projectTypeKey", "software"),
            "style": raw.get("style", "classic"),
            "description": raw.get("description") or "",
            "lead": lead_info,
            "issueTypes": issue_types,
            "issueTypesCount": len(issue_types),
            "url": project_url,
        }

    async def create_story(
        self,
        user_id: str,
        project_key: str,
        summary: str,
        description: str,
        issue_type: str = "Story",
    ) -> Dict[str, Any]:
        """
        Creates a Jira Story or Issue in Jira Cloud using the connected user's OAuth token.
        """
        conn = await self.ensure_valid_token(user_id)
        if not conn.cloud_id:
            raise ValueError("Jira connection has no associated cloud_id.")

        headers = {
            "Authorization": f"Bearer {conn.access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Connector-Jira-OAuth/1.0",
        }

        url = f"{self.JIRA_API_BASE}/{conn.cloud_id}/rest/api/3/issue"
        adf_desc = self._text_to_adf(description)

        payload = {
            "fields": {
                "project": {"key": project_key.strip().upper()},
                "summary": summary.strip(),
                "description": adf_desc,
                "issuetype": {"name": issue_type.strip() or "Story"},
            }
        }

        async with httpx.AsyncClient(timeout=25.0) as client:
            resp = await client.post(url, headers=headers, json=payload)

            # If v3 ADF fails or issue type name doesn't match exactly, inspect response
            if resp.status_code == 400:
                err_data = resp.json() if "application/json" in resp.headers.get("content-type", "") else {}
                errors = err_data.get("errors", {})
                error_messages = err_data.get("errorMessages", [])

                # If issue type is not found, check available issue types for the project
                if "issuetype" in errors:
                    # Try fallback to "Task" if Story wasn't found, or inspect project issue types
                    proj_resp = await client.get(
                        f"{self.JIRA_API_BASE}/{conn.cloud_id}/rest/api/3/project/{project_key}",
                        headers=headers,
                    )
                    if proj_resp.status_code == 200:
                        proj_data = proj_resp.json()
                        available_types = [it.get("name") for it in proj_data.get("issueTypes", []) if not it.get("subtask")]
                        for fallback in ("Story", "Task", "User Story", "Bug"):
                            if fallback in available_types:
                                payload["fields"]["issuetype"]["name"] = fallback
                                retry_resp = await client.post(url, headers=headers, json=payload)
                                if retry_resp.status_code in (200, 201):
                                    resp = retry_resp
                                    break

            if resp.status_code not in (200, 201):
                err_text = resp.text
                try:
                    err_json = resp.json()
                    err_text = str(err_json.get("errors") or err_json.get("errorMessages") or err_text)
                except Exception:
                    pass
                raise RuntimeError(f"Failed to create Jira issue (Status {resp.status_code}): {err_text}")

            res_data = resp.json()
            issue_key = res_data.get("key")
            issue_id = res_data.get("id")
            site_url = (conn.site_url or "").rstrip("/")
            browse_url = f"{site_url}/browse/{issue_key}" if site_url and issue_key else res_data.get("self", "")

            return {
                "success": True,
                "key": issue_key,
                "id": issue_id,
                "url": browse_url,
                "summary": summary,
                "issue_type": payload["fields"]["issuetype"]["name"],
                "project_key": project_key.upper(),
            }
