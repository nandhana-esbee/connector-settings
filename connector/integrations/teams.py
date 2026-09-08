import os
import httpx
from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass
class TeamsSettings:
    """
    Configuration settings for Microsoft Teams integration.
    Supports incoming webhooks and Azure AD / Microsoft Graph API credentials.
    """
    webhook_url: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    tenant_id: Optional[str] = None

    @classmethod
    def from_env(cls) -> "TeamsSettings":
        """Load Teams settings from environment variables."""
        return cls(
            webhook_url=os.getenv("TEAMS_WEBHOOK_URL"),
            client_id=os.getenv("TEAMS_CLIENT_ID"),
            client_secret=os.getenv("TEAMS_CLIENT_SECRET"),
            tenant_id=os.getenv("TEAMS_TENANT_ID"),
        )

    def is_configured(self) -> bool:
        """Check if minimum required settings for Teams are present."""
        return bool(self.webhook_url or (self.client_id and self.client_secret and self.tenant_id))

    def to_dict(self, mask_secrets: bool = True) -> Dict[str, Any]:
        """Return dictionary representation of Teams settings."""
        secret = "********" if mask_secrets and self.client_secret else self.client_secret
        return {
            "webhook_url": self.webhook_url,
            "client_id": self.client_id,
            "client_secret": secret,
            "tenant_id": self.tenant_id,
            "is_configured": self.is_configured(),
        }

    async def test_connection(self, send_test_message: bool = True) -> Dict[str, Any]:
        """
        Test the connection to Microsoft Teams.
        Returns connection result status, response code, and details.
        """
        if not self.is_configured():
            return {
                "success": False,
                "error": "Teams is not configured. Provide TEAMS_WEBHOOK_URL or Azure AD credentials.",
                "details": None,
            }

        async with httpx.AsyncClient(timeout=15.0) as client:
            # 1. Test via Webhook
            if self.webhook_url:
                try:
                    payload = {
                        "text": "🎉 **Connector Module Test**: Microsoft Teams Webhook connection is active and working!"
                    }
                    response = await client.post(self.webhook_url, json=payload)
                    if response.status_code in (200, 202):
                        return {
                            "success": True,
                            "type": "webhook",
                            "message": "Successfully sent test message to Teams incoming webhook.",
                            "status_code": response.status_code,
                        }
                    else:
                        return {
                            "success": False,
                            "type": "webhook",
                            "error": f"Teams webhook responded with status {response.status_code}: {response.text}",
                            "status_code": response.status_code,
                        }
                except Exception as e:
                    return {
                        "success": False,
                        "type": "webhook",
                        "error": f"Failed to reach Teams webhook URL: {str(e)}",
                    }

            # 2. Test via Azure AD / Graph OAuth
            if self.client_id and self.client_secret and self.tenant_id:
                try:
                    token_url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
                    data = {
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "scope": "https://graph.microsoft.com/.default",
                        "grant_type": "client_credentials",
                    }
                    resp = await client.post(token_url, data=data)
                    if resp.status_code == 200:
                        token_info = resp.json()
                        return {
                            "success": True,
                            "type": "azure_ad",
                            "message": "Successfully authenticated with Azure AD / Microsoft Graph.",
                            "token_type": token_info.get("token_type"),
                            "expires_in": token_info.get("expires_in"),
                        }
                    else:
                        return {
                            "success": False,
                            "type": "azure_ad",
                            "error": f"Azure AD authentication failed (status {resp.status_code}): {resp.text}",
                            "status_code": resp.status_code,
                        }
                except Exception as e:
                    return {
                        "success": False,
                        "type": "azure_ad",
                        "error": f"Failed to authenticate with Azure AD: {str(e)}",
                    }

        return {"success": False, "error": "Unknown configuration state"}
