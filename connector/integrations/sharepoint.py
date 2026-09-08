import os
import re
import httpx
from dataclasses import dataclass
from typing import Optional, Dict, Any
from urllib.parse import urlparse


@dataclass
class SharePointSettings:
    """
    Configuration settings for Microsoft SharePoint integration.
    Supports App-Only (Azure AD Client Credentials) authentication.
    """
    site_url: Optional[str] = None
    tenant_id: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    document_library: Optional[str] = "Shared Documents"

    @classmethod
    def from_env(cls) -> "SharePointSettings":
        """Load SharePoint settings from environment variables."""
        return cls(
            site_url=os.getenv("SHAREPOINT_SITE_URL"),
            tenant_id=os.getenv("SHAREPOINT_TENANT_ID"),
            client_id=os.getenv("SHAREPOINT_CLIENT_ID"),
            client_secret=os.getenv("SHAREPOINT_CLIENT_SECRET"),
            document_library=os.getenv("SHAREPOINT_DOCUMENT_LIBRARY", "Shared Documents"),
        )

    def is_configured(self) -> bool:
        """Check if minimum required settings for SharePoint are present."""
        return bool(self.site_url and self.tenant_id and self.client_id and self.client_secret)

    def to_dict(self, mask_secrets: bool = True) -> Dict[str, Any]:
        """Return dictionary representation of SharePoint settings."""
        secret = "********" if mask_secrets and self.client_secret else self.client_secret
        return {
            "site_url": self.site_url,
            "tenant_id": self.tenant_id,
            "client_id": self.client_id,
            "client_secret": secret,
            "document_library": self.document_library,
            "is_configured": self.is_configured(),
        }

    async def test_connection(self) -> Dict[str, Any]:
        """
        Test connection to SharePoint by obtaining an OAuth token from Azure AD
        and querying the SharePoint site via Microsoft Graph.
        """
        if not self.is_configured():
            return {
                "success": False,
                "error": "SharePoint is not configured. Site URL, Tenant ID, Client ID, and Client Secret are required.",
                "details": None,
            }

        token_url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        token_data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                # 1. Request Azure AD token
                token_resp = await client.post(token_url, data=token_data)
                if token_resp.status_code != 200:
                    return {
                        "success": False,
                        "error": f"Azure AD token acquisition failed ({token_resp.status_code}): {token_resp.text}",
                        "status_code": token_resp.status_code,
                    }

                token_json = token_resp.json()
                access_token = token_json.get("access_token")

                # 2. Extract hostname and relative path to query site via Microsoft Graph
                parsed_url = urlparse(self.site_url)
                hostname = parsed_url.netloc
                site_path = parsed_url.path.strip("/")

                site_details = None
                if hostname and access_token:
                    graph_headers = {
                        "Authorization": f"Bearer {access_token}",
                        "Accept": "application/json"
                    }
                    if site_path:
                        graph_url = f"https://graph.microsoft.com/v1.0/sites/{hostname}:/{site_path}"
                    else:
                        graph_url = f"https://graph.microsoft.com/v1.0/sites/{hostname}"

                    graph_resp = await client.get(graph_url, headers=graph_headers)
                    if graph_resp.status_code == 200:
                        site_data = graph_resp.json()
                        site_details = {
                            "siteId": site_data.get("id"),
                            "displayName": site_data.get("displayName"),
                            "webUrl": site_data.get("webUrl"),
                        }
                    else:
                        site_details = {
                            "warning": f"Site lookup returned status {graph_resp.status_code}",
                            "message": graph_resp.text
                        }

                return {
                    "success": True,
                    "message": "Successfully authenticated with Microsoft SharePoint via Azure AD.",
                    "token_type": token_json.get("token_type"),
                    "expires_in": token_json.get("expires_in"),
                    "site": site_details,
                    "document_library": self.document_library,
                }

            except Exception as e:
                return {
                    "success": False,
                    "error": f"Failed to connect to SharePoint: {str(e)}",
                }
