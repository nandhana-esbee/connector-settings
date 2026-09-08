import os
import httpx
from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass
class JiraSettings:
    """
    Configuration settings for Atlassian Jira integration.
    Supports API Token and OAuth 2.0 authentication configurations.
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

    async def test_connection(self) -> Dict[str, Any]:
        """
        Test the connection to Atlassian Jira by calling the 'myself' endpoint
        and checking target project accessibility.
        """
        if not self.is_configured():
            return {
                "success": False,
                "error": "Jira is not configured. Server URL, User Email, and API Token are required.",
                "details": None,
            }

        base_url = (self.server_url or "").rstrip("/")
        # Jira Cloud typically uses /rest/api/3/myself or /rest/api/2/myself
        myself_url = f"{base_url}/rest/api/3/myself"
        
        auth = (self.user_email or "", self.api_token or "")
        headers = {
            "Accept": "application/json",
            "User-Agent": "Connector-Module/0.1.0"
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                resp = await client.get(myself_url, auth=auth, headers=headers)
                if resp.status_code == 404:
                    # Fallback to API v2 (for Jira Server / Data Center)
                    myself_url = f"{base_url}/rest/api/2/myself"
                    resp = await client.get(myself_url, auth=auth, headers=headers)

                if resp.status_code == 200:
                    user_data = resp.json()
                    user_name = user_data.get("displayName") or user_data.get("name") or self.user_email
                    account_id = user_data.get("accountId") or user_data.get("key")
                    
                    project_info = None
                    if self.project_key:
                        proj_url = f"{base_url}/rest/api/3/project/{self.project_key}"
                        proj_resp = await client.get(proj_url, auth=auth, headers=headers)
                        if proj_resp.status_code == 200:
                            proj_data = proj_resp.json()
                            project_info = {
                                "key": proj_data.get("key"),
                                "name": proj_data.get("name"),
                                "id": proj_data.get("id"),
                            }
                        else:
                            project_info = {"key": self.project_key, "warning": f"Project check returned status {proj_resp.status_code}"}

                    return {
                        "success": True,
                        "message": f"Successfully authenticated with Jira as '{user_name}'.",
                        "user": {
                            "displayName": user_name,
                            "email": user_data.get("emailAddress", self.user_email),
                            "accountId": account_id,
                            "active": user_data.get("active", True),
                        },
                        "project": project_info,
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
