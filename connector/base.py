import os
import asyncio
from dataclasses import dataclass, field
from typing import Dict, Any, Optional

from .integrations.teams import TeamsSettings
from .integrations.jira import JiraSettings
from .integrations.sharepoint import SharePointSettings


def load_env_file(dotenv_path: str = ".env") -> None:
    """
    Parse .env file into os.environ if present.
    """
    if not os.path.exists(dotenv_path):
        return
    
    try:
        from dotenv import load_dotenv  # type: ignore
        load_dotenv(dotenv_path, override=True)
    except ImportError:
        with open(dotenv_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("'\"")
                    os.environ[key] = val


@dataclass
class ConnectorSettings:
    """
    Master Connector Settings loader, updater, and tester.
    Aggregates configurations for Teams, Jira, SharePoint, and custom connectors.
    """
    environment: str = "development"
    log_level: str = "INFO"
    teams: TeamsSettings = field(default_factory=TeamsSettings)
    jira: JiraSettings = field(default_factory=JiraSettings)
    sharepoint: SharePointSettings = field(default_factory=SharePointSettings)
    jira_client_id: Optional[str] = None
    jira_client_secret: Optional[str] = None
    jira_redirect_uri: Optional[str] = None
    custom: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, env_file: Optional[str] = ".env") -> "ConnectorSettings":
        """
        Load all connector settings from environment variables (and optional .env file).
        """
        if env_file:
            load_env_file(env_file)

        return cls(
            environment=os.getenv("ENVIRONMENT", "development"),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            teams=TeamsSettings.from_env(),
            jira=JiraSettings.from_env(),
            sharepoint=SharePointSettings.from_env(),
            jira_client_id=os.getenv("JIRA_CLIENT_ID"),
            jira_client_secret=os.getenv("JIRA_CLIENT_SECRET"),
            jira_redirect_uri=os.getenv("JIRA_REDIRECT_URI", "http://127.0.0.1:8000/auth/jira/callback"),
        )

    def register_custom_connector(self, name: str, config: Any) -> None:
        """Register configuration for a custom connector."""
        self.custom[name] = config

    def status_summary(self) -> Dict[str, bool]:
        """Return configuration status summary for all connectors."""
        return {
            "teams": self.teams.is_configured(),
            "jira": self.jira.is_configured(),
            "sharepoint": self.sharepoint.is_configured(),
            **{name: True for name in self.custom},
        }

    def update_teams(
        self,
        webhook_url: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> TeamsSettings:
        """Update Teams settings and set corresponding environment variables."""
        if webhook_url is not None:
            self.teams.webhook_url = webhook_url.strip() or None
            if self.teams.webhook_url:
                os.environ["TEAMS_WEBHOOK_URL"] = self.teams.webhook_url
            elif "TEAMS_WEBHOOK_URL" in os.environ:
                del os.environ["TEAMS_WEBHOOK_URL"]

        if client_id is not None:
            self.teams.client_id = client_id.strip() or None
            if self.teams.client_id:
                os.environ["TEAMS_CLIENT_ID"] = self.teams.client_id
            elif "TEAMS_CLIENT_ID" in os.environ:
                del os.environ["TEAMS_CLIENT_ID"]

        if client_secret is not None:
            self.teams.client_secret = client_secret.strip() or None
            if self.teams.client_secret:
                os.environ["TEAMS_CLIENT_SECRET"] = self.teams.client_secret
            elif "TEAMS_CLIENT_SECRET" in os.environ:
                del os.environ["TEAMS_CLIENT_SECRET"]

        if tenant_id is not None:
            self.teams.tenant_id = tenant_id.strip() or None
            if self.teams.tenant_id:
                os.environ["TEAMS_TENANT_ID"] = self.teams.tenant_id
            elif "TEAMS_TENANT_ID" in os.environ:
                del os.environ["TEAMS_TENANT_ID"]

        return self.teams

    def update_jira(
        self,
        server_url: Optional[str] = None,
        user_email: Optional[str] = None,
        api_token: Optional[str] = None,
        project_key: Optional[str] = None,
    ) -> JiraSettings:
        """Update Jira settings and set corresponding environment variables."""
        if server_url is not None:
            self.jira.server_url = server_url.strip() or None
            if self.jira.server_url:
                os.environ["JIRA_SERVER_URL"] = self.jira.server_url
            elif "JIRA_SERVER_URL" in os.environ:
                del os.environ["JIRA_SERVER_URL"]

        if user_email is not None:
            self.jira.user_email = user_email.strip() or None
            if self.jira.user_email:
                os.environ["JIRA_USER_EMAIL"] = self.jira.user_email
            elif "JIRA_USER_EMAIL" in os.environ:
                del os.environ["JIRA_USER_EMAIL"]

        if api_token is not None:
            self.jira.api_token = api_token.strip() or None
            if self.jira.api_token:
                os.environ["JIRA_API_TOKEN"] = self.jira.api_token
            elif "JIRA_API_TOKEN" in os.environ:
                del os.environ["JIRA_API_TOKEN"]

        if project_key is not None:
            self.jira.project_key = project_key.strip() or None
            if self.jira.project_key:
                os.environ["JIRA_DEFAULT_PROJECT_KEY"] = self.jira.project_key
            elif "JIRA_DEFAULT_PROJECT_KEY" in os.environ:
                del os.environ["JIRA_DEFAULT_PROJECT_KEY"]

        return self.jira

    def update_sharepoint(
        self,
        site_url: Optional[str] = None,
        tenant_id: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        document_library: Optional[str] = None,
    ) -> SharePointSettings:
        """Update SharePoint settings and set corresponding environment variables."""
        if site_url is not None:
            self.sharepoint.site_url = site_url.strip() or None
            if self.sharepoint.site_url:
                os.environ["SHAREPOINT_SITE_URL"] = self.sharepoint.site_url
            elif "SHAREPOINT_SITE_URL" in os.environ:
                del os.environ["SHAREPOINT_SITE_URL"]

        if tenant_id is not None:
            self.sharepoint.tenant_id = tenant_id.strip() or None
            if self.sharepoint.tenant_id:
                os.environ["SHAREPOINT_TENANT_ID"] = self.sharepoint.tenant_id
            elif "SHAREPOINT_TENANT_ID" in os.environ:
                del os.environ["SHAREPOINT_TENANT_ID"]

        if client_id is not None:
            self.sharepoint.client_id = client_id.strip() or None
            if self.sharepoint.client_id:
                os.environ["SHAREPOINT_CLIENT_ID"] = self.sharepoint.client_id
            elif "SHAREPOINT_CLIENT_ID" in os.environ:
                del os.environ["SHAREPOINT_CLIENT_ID"]

        if client_secret is not None:
            self.sharepoint.client_secret = client_secret.strip() or None
            if self.sharepoint.client_secret:
                os.environ["SHAREPOINT_CLIENT_SECRET"] = self.sharepoint.client_secret
            elif "SHAREPOINT_CLIENT_SECRET" in os.environ:
                del os.environ["SHAREPOINT_CLIENT_SECRET"]

        if document_library is not None:
            self.sharepoint.document_library = document_library.strip() or "Shared Documents"
            os.environ["SHAREPOINT_DOCUMENT_LIBRARY"] = self.sharepoint.document_library

        return self.sharepoint

    def save_to_env(self, env_path: str = ".env") -> None:
        """
        Persist current settings to a .env file.
        """
        lines = [
            "# ==========================================",
            "# CONNECTOR MODULE ENVIRONMENT CONFIGURATION",
            "# ==========================================",
            f"ENVIRONMENT={self.environment}",
            f"LOG_LEVEL={self.log_level}",
            "",
            "# Microsoft Teams Configuration",
            f"TEAMS_WEBHOOK_URL={self.teams.webhook_url or ''}",
            f"TEAMS_CLIENT_ID={self.teams.client_id or ''}",
            f"TEAMS_CLIENT_SECRET={self.teams.client_secret or ''}",
            f"TEAMS_TENANT_ID={self.teams.tenant_id or ''}",
            "",
            "# Atlassian Jira Configuration",
            f"JIRA_SERVER_URL={self.jira.server_url or ''}",
            f"JIRA_USER_EMAIL={self.jira.user_email or ''}",
            f"JIRA_API_TOKEN={self.jira.api_token or ''}",
            f"JIRA_DEFAULT_PROJECT_KEY={self.jira.project_key or ''}",
            f"JIRA_CLIENT_ID={self.jira_client_id or ''}",
            f"JIRA_CLIENT_SECRET={self.jira_client_secret or ''}",
            f"JIRA_REDIRECT_URI={self.jira_redirect_uri or 'http://127.0.0.1:8000/auth/jira/callback'}",
            "",
            "# Microsoft SharePoint Configuration",
            f"SHAREPOINT_SITE_URL={self.sharepoint.site_url or ''}",
            f"SHAREPOINT_TENANT_ID={self.sharepoint.tenant_id or ''}",
            f"SHAREPOINT_CLIENT_ID={self.sharepoint.client_id or ''}",
            f"SHAREPOINT_CLIENT_SECRET={self.sharepoint.client_secret or ''}",
            f"SHAREPOINT_DOCUMENT_LIBRARY={self.sharepoint.document_library or 'Shared Documents'}",
            "",
        ]

        with open(env_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    async def test_all(self) -> Dict[str, Any]:
        """Test connections to all configured services in parallel."""
        tasks = {
            "teams": self.teams.test_connection(),
            "jira": self.jira.test_connection(),
            "sharepoint": self.sharepoint.test_connection(),
        }
        
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        
        output = {}
        for (name, _), res in zip(tasks.items(), results):
            if isinstance(res, Exception):
                output[name] = {"success": False, "error": str(res)}
            else:
                output[name] = res
        return output

    def to_dict(self, mask_secrets: bool = True) -> Dict[str, Any]:
        """Export full configuration tree as a dictionary."""
        masked_secret = "********" if mask_secrets and self.jira_client_secret else self.jira_client_secret
        return {
            "environment": self.environment,
            "log_level": self.log_level,
            "connectors": {
                "teams": self.teams.to_dict(mask_secrets=mask_secrets),
                "jira": self.jira.to_dict(mask_secrets=mask_secrets),
                "sharepoint": self.sharepoint.to_dict(mask_secrets=mask_secrets),
                "jira_oauth": {
                    "client_id": self.jira_client_id,
                    "client_secret": masked_secret,
                    "redirect_uri": self.jira_redirect_uri,
                    "is_configured": bool(self.jira_client_id and self.jira_client_secret and self.jira_redirect_uri),
                },
                "custom": self.custom,
            },
            "status": self.status_summary(),
        }
