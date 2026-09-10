import sys
import json
import secrets
import urllib.parse
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
import uvicorn

from connector import ConnectorSettings, OAuthStore, JiraOAuthService

# Initialize FastAPI App
app = FastAPI(
    title="Connector Settings & Integration API",
    description="Centralized settings management, Jira Cloud OAuth 2.0 (3LO), project discovery, and live connection testing service for Microsoft Teams, Jira, SharePoint, and custom connectors.",
    version="0.3.0",
)

# Global stores and services
settings = ConnectorSettings.load(env_file=".env")
oauth_store = OAuthStore()
jira_oauth = JiraOAuthService(store=oauth_store)

SESSION_COOKIE_NAME = "app_session_id"


@app.middleware("http")
async def ensure_session_cookie(request: Request, call_next):
    """Ensure every client has an isolated session ID for per-user token storage."""
    existing_cookie = request.cookies.get(SESSION_COOKIE_NAME)
    user_id = existing_cookie or secrets.token_urlsafe(24)
    request.state.user_id = user_id

    response = await call_next(request)

    if not existing_cookie:
        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=user_id,
            httponly=True,
            samesite="lax",
            max_age=60 * 60 * 24 * 30,  # 30 days
        )
    return response


# ---------------------------------------------------------
# Request Models for User Input
# ---------------------------------------------------------

class TeamsUpdateRequest(BaseModel):
    webhook_url: Optional[str] = Field(None, description="Microsoft Teams incoming webhook URL")
    client_id: Optional[str] = Field(None, description="Azure AD Application / Client ID")
    client_secret: Optional[str] = Field(None, description="Azure AD Application Client Secret")
    tenant_id: Optional[str] = Field(None, description="Azure AD Directory / Tenant ID")
    test_now: bool = Field(True, description="Immediately test connection after saving")
    persist_to_env: bool = Field(True, description="Save changes to .env file")


class JiraUpdateRequest(BaseModel):
    server_url: Optional[str] = Field(None, description="Atlassian Jira base URL (e.g. https://your-domain.atlassian.net)")
    user_email: Optional[str] = Field(None, description="Atlassian Account User Email")
    api_token: Optional[str] = Field(None, description="Atlassian Jira API Token")
    project_key: Optional[str] = Field(None, description="Default Jira Project Key")
    test_now: bool = Field(True, description="Immediately test connection and fetch all projects after saving")
    persist_to_env: bool = Field(True, description="Save changes to .env file")


class JiraCreateIssueRequest(BaseModel):
    project_key: str = Field(..., description="Target Jira Project Key (e.g. PROJ)")
    summary: str = Field(..., description="Issue summary headline")
    description: str = Field(..., description="Issue description or user story details")
    issue_type: str = Field("Story", description="Issue type name (defaults to Story)")


class SharePointUpdateRequest(BaseModel):
    site_url: Optional[str] = Field(None, description="SharePoint site URL (e.g. https://yourtenant.sharepoint.com/sites/SiteName)")
    tenant_id: Optional[str] = Field(None, description="Azure AD Tenant ID")
    client_id: Optional[str] = Field(None, description="Azure AD Client ID")
    client_secret: Optional[str] = Field(None, description="Azure AD Client Secret")
    document_library: Optional[str] = Field("Shared Documents", description="Target Document Library name")
    test_now: bool = Field(True, description="Immediately test connection after saving")
    persist_to_env: bool = Field(True, description="Save changes to .env file")


# ---------------------------------------------------------
# Interactive Web Dashboard (HTML / CSS / JS)
# ---------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def get_dashboard(request: Request):
    """Renders the modern interactive connector configuration, project explorer, and testing dashboard."""
    raw_config = settings.to_dict(mask_secrets=False)
    
    teams = raw_config["connectors"]["teams"]
    jira = raw_config["connectors"]["jira"]
    sp = raw_config["connectors"]["sharepoint"]

    user_id = getattr(request.state, "user_id", "")
    oauth_conn = oauth_store.get_connection(user_id) if user_id else None
    is_oauth_connected = bool(oauth_conn and oauth_conn.cloud_id)
    oauth_site_name = (oauth_conn.site_name if oauth_conn else "") or "Atlassian Jira Cloud"
    oauth_site_url = (oauth_conn.site_url if oauth_conn else "") or ""
    oauth_cloud_id = (oauth_conn.cloud_id if oauth_conn else "") or ""
    oauth_email = (oauth_conn.account_email if oauth_conn else "") or ""
    oauth_name = (oauth_conn.display_name if oauth_conn else "") or ""

    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Connector Settings & Project Explorer Hub</title>
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
        <style>
            :root {{
                --bg-primary: #0b0f19;
                --bg-secondary: #111827;
                --bg-card: #1f2937;
                --bg-input: #0f172a;
                --border-color: #374151;
                --text-primary: #f9fafb;
                --text-secondary: #9ca3af;
                --accent-blue: #3b82f6;
                --accent-blue-hover: #2563eb;
                --accent-green: #10b981;
                --accent-green-hover: #059669;
                --accent-red: #ef4444;
                --accent-purple: #8b5cf6;
                --accent-amber: #f59e0b;
            }}
            * {{ box-sizing: border-box; margin: 0; padding: 0; }}
            body {{
                font-family: 'Inter', -apple-system, sans-serif;
                background-color: var(--bg-primary);
                color: var(--text-primary);
                line-height: 1.5;
                padding: 30px 20px;
            }}
            .container {{ max-width: 1100px; margin: 0 auto; }}
            header {{
                text-align: center;
                margin-bottom: 30px;
                padding-bottom: 20px;
                border-bottom: 1px solid var(--border-color);
            }}
            .badge-header {{
                display: inline-block;
                background: rgba(59, 130, 246, 0.15);
                color: #60a5fa;
                padding: 4px 12px;
                border-radius: 999px;
                font-size: 0.8rem;
                font-weight: 600;
                margin-bottom: 8px;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }}
            h1 {{ font-size: 2.2rem; font-weight: 700; color: #fff; margin-bottom: 8px; }}
            .subtitle {{ color: var(--text-secondary); font-size: 1rem; }}
            
            .tabs-nav {{
                display: flex;
                gap: 12px;
                margin-bottom: 24px;
                background: var(--bg-secondary);
                padding: 6px;
                border-radius: 12px;
                border: 1px solid var(--border-color);
            }}
            .tab-btn {{
                flex: 1;
                background: transparent;
                border: none;
                color: var(--text-secondary);
                padding: 12px 18px;
                border-radius: 8px;
                font-size: 0.95rem;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.2s ease;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 8px;
            }}
            .tab-btn:hover {{ color: #fff; background: rgba(255,255,255,0.05); }}
            .tab-btn.active {{
                background: var(--accent-blue);
                color: #fff;
                box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
            }}
            
            .tab-content {{ display: none; }}
            .tab-content.active {{ display: block; }}

            .card {{
                background: var(--bg-secondary);
                border-radius: 14px;
                border: 1px solid var(--border-color);
                padding: 28px;
                margin-bottom: 24px;
                box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.4);
            }}
            .card-header {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 20px;
            }}
            .card-title {{ font-size: 1.3rem; font-weight: 600; color: #fff; }}
            
            .status-pill {{
                padding: 4px 12px;
                border-radius: 20px;
                font-size: 0.8rem;
                font-weight: 600;
            }}
            .status-configured {{ background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid #059669; }}
            .status-unconfigured {{ background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid #b91c1c; }}

            .form-grid {{
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 20px;
                margin-bottom: 24px;
            }}
            .form-group.full {{ grid-column: span 2; }}
            label {{
                display: block;
                font-size: 0.85rem;
                font-weight: 600;
                color: var(--text-secondary);
                margin-bottom: 6px;
            }}
            input {{
                width: 100%;
                background: var(--bg-input);
                border: 1px solid var(--border-color);
                color: #fff;
                padding: 11px 14px;
                border-radius: 8px;
                font-size: 0.95rem;
                font-family: inherit;
                outline: none;
                transition: border-color 0.2s;
            }}
            input:focus {{ border-color: var(--accent-blue); box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.2); }}

            .actions {{
                display: flex;
                gap: 12px;
                justify-content: flex-end;
                flex-wrap: wrap;
            }}
            .btn {{
                padding: 10px 20px;
                border-radius: 8px;
                font-size: 0.95rem;
                font-weight: 600;
                cursor: pointer;
                border: none;
                transition: all 0.2s ease;
                display: inline-flex;
                align-items: center;
                gap: 8px;
            }}
            .btn-primary {{ background: var(--accent-blue); color: #fff; }}
            .btn-primary:hover {{ background: var(--accent-blue-hover); }}
            .btn-success {{ background: var(--accent-green); color: #fff; }}
            .btn-success:hover {{ background: var(--accent-green-hover); }}
            .btn-purple {{ background: var(--accent-purple); color: #fff; }}
            .btn-purple:hover {{ background: #7c3aed; }}
            .btn-secondary {{ background: var(--bg-card); color: var(--text-primary); border: 1px solid var(--border-color); }}
            .btn-secondary:hover {{ background: #374151; }}
            
            .result-box {{
                margin-top: 20px;
                padding: 16px;
                border-radius: 8px;
                background: var(--bg-input);
                border: 1px solid var(--border-color);
                font-family: 'JetBrains Mono', monospace;
                font-size: 0.85rem;
                display: none;
                white-space: pre-wrap;
                word-break: break-word;
            }}
            .result-box.success {{ border-color: var(--accent-green); background: rgba(16, 185, 129, 0.08); color: #6ee7b7; }}
            .result-box.error {{ border-color: var(--accent-red); background: rgba(239, 68, 68, 0.08); color: #fca5a5; }}

            /* Projects Grid / Table */
            .projects-container {{
                margin-top: 24px;
                display: none;
            }}
            .projects-header {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 14px;
            }}
            .projects-count {{
                background: rgba(59, 130, 246, 0.2);
                color: #60a5fa;
                padding: 3px 10px;
                border-radius: 12px;
                font-size: 0.8rem;
                font-weight: 600;
            }}
            .project-card {{
                background: var(--bg-input);
                border: 1px solid var(--border-color);
                border-radius: 10px;
                padding: 18px;
                margin-bottom: 14px;
                transition: transform 0.15s, border-color 0.15s;
            }}
            .project-card:hover {{
                border-color: var(--accent-blue);
                transform: translateY(-2px);
            }}
            .project-card-header {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 8px;
            }}
            .project-key {{
                background: #1e3a8a;
                color: #bfdbfe;
                font-weight: 700;
                padding: 3px 8px;
                border-radius: 6px;
                font-size: 0.85rem;
                font-family: 'JetBrains Mono', monospace;
            }}
            .project-name {{
                font-size: 1.1rem;
                font-weight: 600;
                color: #fff;
            }}
            .project-meta {{
                font-size: 0.85rem;
                color: var(--text-secondary);
                margin-top: 6px;
                display: flex;
                gap: 16px;
                flex-wrap: wrap;
            }}
            .project-types {{
                margin-top: 10px;
                display: flex;
                gap: 6px;
                flex-wrap: wrap;
            }}
            .type-badge {{
                background: #334155;
                color: #cbd5e1;
                font-size: 0.75rem;
                padding: 2px 8px;
                border-radius: 4px;
            }}

            /* Toast Notifications */
            .toast-container {{
                margin-bottom: 20px;
                display: none;
            }}
            .toast {{
                padding: 14px 20px;
                border-radius: 10px;
                font-size: 0.95rem;
                font-weight: 600;
                display: flex;
                align-items: center;
                justify-content: space-between;
                box-shadow: 0 4px 15px rgba(0,0,0,0.3);
            }}
            .toast.success {{ background: rgba(16, 185, 129, 0.15); border: 1px solid #10b981; color: #6ee7b7; }}
            .toast.error {{ background: rgba(239, 68, 68, 0.15); border: 1px solid #ef4444; color: #fca5a5; }}

            /* Jira OAuth Card Styles */
            .jira-oauth-card {{
                background: linear-gradient(145deg, #111827, #1e293b);
                border: 1px solid #2563eb;
                border-radius: 14px;
                padding: 28px;
                margin-bottom: 24px;
                box-shadow: 0 10px 25px -5px rgba(37, 99, 235, 0.25);
            }}
            .jira-header {{
                display: flex;
                align-items: center;
                gap: 16px;
                margin-bottom: 12px;
            }}
            .jira-logo {{
                width: 40px;
                height: 40px;
                flex-shrink: 0;
            }}
            .jira-title {{
                font-size: 1.45rem;
                font-weight: 700;
                color: #fff;
                margin: 0;
            }}
            .jira-description {{
                color: var(--text-secondary);
                font-size: 0.95rem;
                margin-bottom: 20px;
                line-height: 1.5;
            }}
            .btn-jira-connect {{
                background: #0052cc;
                color: #fff;
                font-size: 1rem;
                font-weight: 600;
                padding: 12px 24px;
                border-radius: 8px;
                border: none;
                cursor: pointer;
                display: inline-flex;
                align-items: center;
                gap: 10px;
                transition: background 0.2s, transform 0.1s;
            }}
            .btn-jira-connect:hover {{
                background: #0747a6;
                transform: translateY(-1px);
            }}
            .btn-jira-connect:disabled {{
                opacity: 0.6;
                cursor: not-allowed;
            }}
            .btn-danger {{
                background: #ef4444;
                color: #fff;
            }}
            .btn-danger:hover {{
                background: #dc2626;
            }}
            .jira-connected-meta {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
                gap: 16px;
                background: var(--bg-input);
                border: 1px solid var(--border-color);
                border-radius: 10px;
                padding: 18px;
                margin: 18px 0;
            }}
            .meta-group label {{
                font-size: 0.75rem;
                text-transform: uppercase;
                letter-spacing: 0.5px;
                color: var(--text-secondary);
                margin-bottom: 4px;
                display: block;
            }}
            .meta-group .meta-val {{
                font-size: 0.95rem;
                font-weight: 600;
                color: #fff;
                word-break: break-all;
            }}
            .story-creator-box {{
                margin-top: 24px;
                padding: 20px;
                border-radius: 12px;
                background: rgba(15, 23, 42, 0.8);
                border: 1px solid var(--border-color);
            }}
            .story-creator-title {{
                font-size: 1.15rem;
                font-weight: 600;
                color: #fff;
                margin-bottom: 12px;
                display: flex;
                align-items: center;
                gap: 8px;
            }}
            textarea {{
                width: 100%;
                background: var(--bg-input);
                border: 1px solid var(--border-color);
                color: #fff;
                padding: 11px 14px;
                border-radius: 8px;
                font-size: 0.95rem;
                font-family: inherit;
                outline: none;
                resize: vertical;
            }}
            textarea:focus {{
                border-color: var(--accent-blue);
                box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.2);
            }}
            select {{
                width: 100%;
                background: var(--bg-input);
                border: 1px solid var(--border-color);
                color: #fff;
                padding: 11px 14px;
                border-radius: 8px;
                font-size: 0.95rem;
                font-family: inherit;
                outline: none;
            }}
            select:focus {{
                border-color: var(--accent-blue);
            }}
            .spinner {{
                display: inline-block;
                width: 16px;
                height: 16px;
                border: 2px solid rgba(255,255,255,0.3);
                border-radius: 50%;
                border-top-color: #fff;
                animation: spin 0.8s linear infinite;
            }}
            @keyframes spin {{ to {{ transform: rotate(360deg); }} }}

            .footer-links {{
                text-align: center;
                margin-top: 30px;
                color: var(--text-secondary);
                font-size: 0.9rem;
            }}
            .footer-links a {{ color: var(--accent-blue); text-decoration: none; margin: 0 10px; }}
            .footer-links a:hover {{ text-decoration: underline; }}
        </style>
    </head>
    <body>
        <div class="container">
            <!-- NOTIFICATION TOAST BANNER -->
            <div id="toast-banner" class="toast-container">
                <div id="toast-content" class="toast">
                    <span id="toast-message"></span>
                    <button type="button" onclick="hideToast()" style="background:none; border:none; color:inherit; font-size:1.2rem; cursor:pointer; line-height:1;">&times;</button>
                </div>
            </div>

            <header>
                <div class="badge-header">Unified Integration Hub</div>
                <h1>🔌 Connector Settings & Project Discovery Hub</h1>
                <p class="subtitle">Configure credentials and fetch every project detail from Jira, Microsoft Teams, and SharePoint.</p>
            </header>

            <div class="tabs-nav">
                <button class="tab-btn active" onclick="showTab('jira')">📋 Atlassian Jira</button>
                <button class="tab-btn" onclick="showTab('teams')">💬 Microsoft Teams</button>
                <button class="tab-btn" onclick="showTab('sharepoint')">📁 SharePoint</button>
                <button class="tab-btn" onclick="showTab('overview')">📊 Overview & JSON</button>
            </div>

            <!-- JIRA TAB -->
            <div id="tab-jira" class="tab-content active">
                
                <!-- JIRA OAUTH 2.0 INTEGRATION SECTION -->
                <div class="jira-oauth-card">
                    
                    <!-- DISCONNECTED STATE -->
                    <div id="jira-oauth-disconnected" style="display: {'none' if is_oauth_connected else 'block'};">
                        <div class="jira-header">
                            <svg class="jira-logo" viewBox="0 0 24 24" fill="none">
                                <path d="M11.53 2c0 2.4 1.97 4.35 4.39 4.35h2.93V2h-7.32z" fill="#0052CC"/>
                                <path d="M7.14 6.35C7.14 8.75 9.1 10.7 11.53 10.7h2.93V6.35H7.14z" fill="#2684FF"/>
                                <path d="M2.75 10.7c0 2.4 1.96 4.35 4.39 4.35h2.93V10.7H2.75z" fill="#0052CC"/>
                                <path d="M7.14 15.05c0 2.4 1.96 4.35 4.39 4.35h2.93v-4.35H7.14z" fill="#2684FF"/>
                                <path d="M11.53 19.4c0 2.4 1.97 4.35 4.39 4.35h2.93V19.4h-7.32z" fill="#0052CC"/>
                            </svg>
                            <div>
                                <h2 class="jira-title">Jira</h2>
                                <span class="badge-header" style="background: rgba(59,130,246,0.1); margin-top: 4px;">OAuth 2.0 (3LO)</span>
                            </div>
                        </div>
                        <p class="jira-description">Connect your Jira account to import activity and create issues from generated user stories.</p>
                        <div class="actions" style="justify-content: flex-start;">
                            <button id="connect-jira-btn" type="button" class="btn-jira-connect" onclick="startJiraOAuth()">
                                <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M11.53 2c0 2.4 1.97 4.35 4.39 4.35h2.93V2h-7.32z"/><path d="M7.14 6.35C7.14 8.75 9.1 10.7 11.53 10.7h2.93V6.35H7.14z"/><path d="M2.75 10.7c0 2.4 1.96 4.35 4.39 4.35h2.93V10.7H2.75z"/><path d="M7.14 15.05c0 2.4 1.96 4.35 4.39 4.35h2.93v-4.35H7.14z"/><path d="M11.53 19.4c0 2.4 1.97 4.35 4.39 4.35h2.93V19.4h-7.32z"/></svg>
                                Connect Jira
                            </button>
                        </div>
                    </div>

                    <!-- CONNECTED STATE -->
                    <div id="jira-oauth-connected" style="display: {'block' if is_oauth_connected else 'none'};">
                        <div class="card-header" style="margin-bottom: 8px;">
                            <div class="jira-header" style="margin-bottom: 0;">
                                <svg class="jira-logo" viewBox="0 0 24 24" fill="none">
                                    <path d="M11.53 2c0 2.4 1.97 4.35 4.39 4.35h2.93V2h-7.32z" fill="#0052CC"/>
                                    <path d="M7.14 6.35C7.14 8.75 9.1 10.7 11.53 10.7h2.93V6.35H7.14z" fill="#2684FF"/>
                                    <path d="M2.75 10.7c0 2.4 1.96 4.35 4.39 4.35h2.93V10.7H2.75z" fill="#0052CC"/>
                                    <path d="M7.14 15.05c0 2.4 1.96 4.35 4.39 4.35h2.93v-4.35H7.14z" fill="#2684FF"/>
                                    <path d="M11.53 19.4c0 2.4 1.97 4.35 4.39 4.35h2.93V19.4h-7.32z" fill="#0052CC"/>
                                </svg>
                                <div>
                                    <h2 class="jira-title">Jira Connected</h2>
                                    <p style="font-size: 0.85rem; color: #9ca3af;">Authorized via OAuth 2.0 (3LO) with automatic token refresh</p>
                                </div>
                            </div>
                            <span class="status-pill status-configured">Connected</span>
                        </div>

                        <div class="jira-connected-meta">
                            <div class="meta-group">
                                <label>Jira Site / Workspace</label>
                                <div id="oauth-site-name" class="meta-val">{oauth_site_name}</div>
                            </div>
                            <div class="meta-group">
                                <label>Site URL</label>
                                <div class="meta-val"><a id="oauth-site-url" href="{oauth_site_url}" target="_blank" style="color: var(--accent-blue); text-decoration: none;">{oauth_site_url or 'N/A'}</a></div>
                            </div>
                            <div class="meta-group">
                                <label>Connected Account</label>
                                <div id="oauth-account" class="meta-val">{oauth_name}{f' ({oauth_email})' if oauth_email else ''}</div>
                            </div>
                            <div class="meta-group">
                                <label>Cloud ID</label>
                                <div id="oauth-cloud-id" class="meta-val" style="font-family: 'JetBrains Mono', monospace; font-size: 0.85rem; color: #cbd5e1;">{oauth_cloud_id or 'N/A'}</div>
                            </div>
                        </div>

                        <div class="actions" style="justify-content: flex-start; margin-bottom: 24px;">
                            <button type="button" class="btn btn-purple" onclick="fetchJiraProjectsOnly()">📂 Fetch Available Projects</button>
                            <button id="disconnect-jira-btn" type="button" class="btn btn-danger" onclick="disconnectJira()">Disconnect Jira</button>
                        </div>

                        <!-- CREATE JIRA STORY WIDGET -->
                        <div class="story-creator-box">
                            <div class="story-creator-title">
                                <span>📝</span>
                                <span>Create Jira Story / User Story</span>
                            </div>
                            <p style="font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 16px;">
                                Export generated user stories and tickets directly to the connected Jira workspace.
                            </p>
                            <form id="create-story-form" onsubmit="event.preventDefault(); createStoryInJira();">
                                <div class="form-grid">
                                    <div class="form-group">
                                        <label for="story_project_key">Target Project</label>
                                        <select id="story_project_key">
                                            <option value="">-- Select a Project --</option>
                                        </select>
                                    </div>
                                    <div class="form-group">
                                        <label for="story_issue_type">Issue Type</label>
                                        <select id="story_issue_type">
                                            <option value="Story" selected>Story</option>
                                            <option value="Task">Task</option>
                                            <option value="Bug">Bug</option>
                                        </select>
                                    </div>
                                    <div class="form-group full">
                                        <label for="story_summary">Story Summary / Headline</label>
                                        <input type="text" id="story_summary" placeholder="e.g. Add password reset functionality via email link" required>
                                    </div>
                                    <div class="form-group full">
                                        <label for="story_description">Story Description / Acceptance Criteria</label>
                                        <textarea id="story_description" rows="4" placeholder="As a registered user,&#10;I want to request a password reset email&#10;So that I can regain access if forgotten.&#10;&#10;Acceptance Criteria:&#10;- Send secure reset token link&#10;- 15-minute expiration" required></textarea>
                                    </div>
                                </div>
                                <div class="actions">
                                    <button id="create-story-btn" type="submit" class="btn btn-success">🚀 Create Issue in Jira</button>
                                </div>
                            </form>
                            <div id="story-result" class="result-box"></div>
                        </div>

                    </div>
                </div>

                <!-- DISCOVERED PROJECTS DISPLAY -->
                <div id="jira-projects-container" class="projects-container">
                    <div class="projects-header">
                        <h3 style="color: #fff; font-size: 1.15rem;">Discovered Projects in Workspace</h3>
                        <span id="jira-projects-count" class="projects-count">0 Projects</span>
                    </div>
                    <div id="jira-projects-list"></div>
                </div>

                <!-- ADVANCED / LEGACY API TOKEN SETTINGS -->
                <details style="margin-top: 24px; background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: 12px; padding: 18px;">
                    <summary style="cursor: pointer; font-weight: 600; color: var(--text-secondary); outline: none;">
                        ⚙️ Advanced / Legacy: Manual Jira API Token Settings
                    </summary>
                    <div style="margin-top: 18px;">
                        <form id="jira-form" onsubmit="event.preventDefault(); saveAndTest('jira');">
                            <div class="form-grid">
                                <div class="form-group full">
                                    <label for="jira_server_url">Jira Server URL</label>
                                    <input type="url" id="jira_server_url" value="{jira.get('server_url') or ''}" placeholder="https://your-company.atlassian.net">
                                </div>
                                <div class="form-group">
                                    <label for="jira_user_email">User Email (Atlassian ID)</label>
                                    <input type="email" id="jira_user_email" value="{jira.get('user_email') or ''}" placeholder="name@company.com">
                                </div>
                                <div class="form-group">
                                    <label for="jira_api_token">API Token</label>
                                    <input type="password" id="jira_api_token" value="{jira.get('api_token') or ''}" placeholder="••••••••••••••••">
                                </div>
                                <div class="form-group full">
                                    <label for="jira_project_key">Default Project Key (Optional filter)</label>
                                    <input type="text" id="jira_project_key" value="{jira.get('project_key') or ''}" placeholder="PROJ">
                                </div>
                            </div>
                            <div class="actions">
                                <button type="button" class="btn btn-secondary" onclick="testOnly('jira')">⚡ Test Connection</button>
                                <button type="submit" class="btn btn-primary">💾 Save & Fetch All Projects</button>
                            </div>
                        </form>
                        <div id="jira-result" class="result-box"></div>
                    </div>
                </details>

            </div>

            <!-- TEAMS TAB -->
            <div id="tab-teams" class="tab-content">
                <div class="card">
                    <div class="card-header">
                        <div class="card-title">Microsoft Teams Configuration</div>
                        <span id="teams-badge" class="status-pill {'status-configured' if teams.get('is_configured') else 'status-unconfigured'}">
                            {'CONNECTED / READY' if teams.get('is_configured') else 'NOT CONFIGURED'}
                        </span>
                    </div>
                    <form id="teams-form" onsubmit="event.preventDefault(); saveAndTest('teams');">
                        <div class="form-grid">
                            <div class="form-group full">
                                <label for="teams_webhook">Incoming Webhook URL (For Channel Notifications)</label>
                                <input type="url" id="teams_webhook" value="{teams.get('webhook_url') or ''}" placeholder="https://outlook.office.com/webhook/...">
                            </div>
                            <div class="form-group">
                                <label for="teams_client_id">Azure AD Client ID (Optional for Graph API)</label>
                                <input type="text" id="teams_client_id" value="{teams.get('client_id') or ''}" placeholder="00000000-0000-0000-0000-000000000000">
                            </div>
                            <div class="form-group">
                                <label for="teams_client_secret">Azure AD Client Secret</label>
                                <input type="password" id="teams_client_secret" value="{teams.get('client_secret') or ''}" placeholder="••••••••••••••••">
                            </div>
                            <div class="form-group full">
                                <label for="teams_tenant_id">Azure AD Tenant ID</label>
                                <input type="text" id="teams_tenant_id" value="{teams.get('tenant_id') or ''}" placeholder="00000000-0000-0000-0000-000000000000">
                            </div>
                        </div>
                        <div class="actions">
                            <button type="button" class="btn btn-secondary" onclick="testOnly('teams')">⚡ Test Connection</button>
                            <button type="submit" class="btn btn-primary">💾 Save & Test Connection</button>
                        </div>
                    </form>
                    <div id="teams-result" class="result-box"></div>
                </div>
            </div>

            <!-- SHAREPOINT TAB -->
            <div id="tab-sharepoint" class="tab-content">
                <div class="card">
                    <div class="card-header">
                        <div class="card-title">Microsoft SharePoint Configuration</div>
                        <span id="sharepoint-badge" class="status-pill {'status-configured' if sp.get('is_configured') else 'status-unconfigured'}">
                            {'CONNECTED / READY' if sp.get('is_configured') else 'NOT CONFIGURED'}
                        </span>
                    </div>
                    <form id="sharepoint-form" onsubmit="event.preventDefault(); saveAndTest('sharepoint');">
                        <div class="form-grid">
                            <div class="form-group full">
                                <label for="sp_site_url">SharePoint Site URL</label>
                                <input type="url" id="sp_site_url" value="{sp.get('site_url') or ''}" placeholder="https://yourtenant.sharepoint.com/sites/Development">
                            </div>
                            <div class="form-group">
                                <label for="sp_tenant_id">Tenant ID</label>
                                <input type="text" id="sp_tenant_id" value="{sp.get('tenant_id') or ''}" placeholder="00000000-0000-0000-0000-000000000000">
                            </div>
                            <div class="form-group">
                                <label for="sp_client_id">Client ID (App Registration)</label>
                                <input type="text" id="sp_client_id" value="{sp.get('client_id') or ''}" placeholder="00000000-0000-0000-0000-000000000000">
                            </div>
                            <div class="form-group">
                                <label for="sp_client_secret">Client Secret</label>
                                <input type="password" id="sp_client_secret" value="{sp.get('client_secret') or ''}" placeholder="••••••••••••••••">
                            </div>
                            <div class="form-group">
                                <label for="sp_document_library">Document Library</label>
                                <input type="text" id="sp_document_library" value="{sp.get('document_library') or 'Shared Documents'}" placeholder="Shared Documents">
                            </div>
                        </div>
                        <div class="actions">
                            <button type="button" class="btn btn-secondary" onclick="testOnly('sharepoint')">⚡ Test Connection</button>
                            <button type="submit" class="btn btn-primary">💾 Save & Test Connection</button>
                        </div>
                    </form>
                    <div id="sharepoint-result" class="result-box"></div>
                </div>
            </div>

            <!-- OVERVIEW TAB -->
            <div id="tab-overview" class="tab-content">
                <div class="card">
                    <div class="card-header">
                        <div class="card-title">Full Configuration & Status Tree</div>
                        <button class="btn btn-success" onclick="testAll()">🚀 Run All Connection Tests</button>
                    </div>
                    <div id="all-tests-result" class="result-box" style="margin-bottom: 20px;"></div>
                    <pre id="json-preview" style="background: var(--bg-input); padding: 18px; border-radius: 8px; font-family: 'JetBrains Mono', monospace; font-size: 0.85rem; border: 1px solid var(--border-color); color: #7dd3fc; overflow-x: auto;">{json.dumps(settings.to_dict(mask_secrets=True), indent=2)}</pre>
                </div>
            </div>

            <div class="footer-links">
                <a href="/docs" target="_blank">📖 Swagger API Docs</a> |
                <a href="/api/connectors/jira/projects" target="_blank">📂 Jira Projects API</a> |
                <a href="/api/settings" target="_blank">🔍 Masked Config JSON</a> |
                <a href="/api/status" target="_blank">📊 Status API</a>
            </div>
        </div>

        <script>
            function showTab(name) {{
                document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
                document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
                
                const btnIndex = ['jira', 'teams', 'sharepoint', 'overview'].indexOf(name);
                if (btnIndex >= 0) {{
                    document.querySelectorAll('.tab-btn')[btnIndex].classList.add('active');
                }}
                document.getElementById('tab-' + name).classList.add('active');
            }}

            async function refreshOverview() {{
                try {{
                    const res = await fetch('/api/settings');
                    const data = await res.json();
                    document.getElementById('json-preview').innerText = JSON.stringify(data, null, 2);
                }} catch (e) {{}}
            }}

            function updateBadge(connector, isConfigured) {{
                const badge = document.getElementById(connector + '-badge');
                if (!badge) return;
                if (isConfigured) {{
                    badge.className = 'status-pill status-configured';
                    badge.innerText = 'CONNECTED / READY';
                }} else {{
                    badge.className = 'status-pill status-unconfigured';
                    badge.innerText = 'NOT CONFIGURED';
                }}
            }}

            function renderJiraProjects(projects) {{
                const container = document.getElementById('jira-projects-container');
                const list = document.getElementById('jira-projects-list');
                const countBadge = document.getElementById('jira-projects-count');

                populateProjectSelect(projects);

                if (!projects || projects.length === 0) {{
                    if (container) container.style.display = 'none';
                    return;
                }}

                if (container) container.style.display = 'block';
                if (countBadge) countBadge.innerText = projects.length + (projects.length === 1 ? ' Project Found' : ' Projects Found');

                if (list) {{
                    list.innerHTML = projects.map(p => {{
                        const leadName = p.lead ? (p.lead.displayName || 'Unassigned') : 'Unassigned';
                        const leadEmail = p.lead && p.lead.emailAddress ? ` (${{p.lead.emailAddress}})` : '';
                        const issueBadges = (p.issueTypes || []).slice(0, 8).map(it => `<span class="type-badge">${{it.name}}</span>`).join('');
                        const moreTypes = (p.issueTypes || []).length > 8 ? `<span class="type-badge">+${{(p.issueTypes.length - 8)}} more</span>` : '';

                        return `
                        <div class="project-card">
                            <div class="project-card-header">
                                <div>
                                    <span class="project-key">${{p.key || 'N/A'}}</span>
                                    <span class="project-name" style="margin-left: 10px;">${{p.name}}</span>
                                </div>
                                ${{p.url ? `<a href="${{p.url}}" target="_blank" style="color: var(--accent-blue); font-size: 0.85rem; text-decoration: none;">🔗 Open in Jira</a>` : ''}}
                            </div>
                            ${{p.description ? `<p style="font-size: 0.9rem; color: #cbd5e1; margin-top: 6px;">${{p.description}}</p>` : ''}}
                            <div class="project-meta">
                                <span><strong>ID:</strong> ${{p.id}}</span>
                                <span><strong>Type:</strong> ${{p.projectTypeKey || 'software'}} (${{p.style || 'classic'}})</span>
                                <span><strong>Lead:</strong> ${{leadName}}${{leadEmail}}</span>
                                ${{p.category ? `<span><strong>Category:</strong> ${{p.category}}</span>` : ''}}
                            </div>
                            ${{issueBadges ? `<div class="project-types"><span style="font-size: 0.75rem; color: var(--text-secondary); margin-right: 4px; align-self: center;">Issue Types:</span>${{issueBadges}}${{moreTypes}}</div>` : ''}}
                        </div>
                        `;
                    }}).join('');
                }}
            }}

            async function fetchJiraProjectsOnly() {{
                const resultBox = document.getElementById('jira-result');
                if (resultBox) {{
                    resultBox.style.display = 'block';
                    resultBox.className = 'result-box';
                    resultBox.innerText = '⏳ Querying Jira API for all project details...';
                }}

                try {{
                    const res = await fetch('/api/jira/projects');
                    const data = await res.json();
                    if (data.success) {{
                        if (resultBox) {{
                            resultBox.className = 'result-box success';
                            resultBox.innerText = `✅ Successfully fetched ${{data.total}} project(s)!`;
                        }}
                        renderJiraProjects(data.projects);
                        updateBadge('jira', true);
                    }} else {{
                        if (resultBox) {{
                            resultBox.className = 'result-box error';
                            resultBox.innerText = '❌ FAILED TO FETCH PROJECTS:\\n' + (data.error || JSON.stringify(data, null, 2));
                        }}
                    }}
                }} catch (e) {{
                    if (resultBox) {{
                        resultBox.className = 'result-box error';
                        resultBox.innerText = '❌ Error: ' + e.message;
                    }}
                }}
            }}

            async function saveAndTest(service) {{
                const resultBox = document.getElementById(service + '-result');
                resultBox.style.display = 'block';
                resultBox.className = 'result-box';
                resultBox.innerText = '⏳ Saving configuration and connecting to ' + service + '...';

                let payload = {{ persist_to_env: true, test_now: true }};

                if (service === 'teams') {{
                    payload.webhook_url = document.getElementById('teams_webhook').value;
                    payload.client_id = document.getElementById('teams_client_id').value;
                    payload.client_secret = document.getElementById('teams_client_secret').value;
                    payload.tenant_id = document.getElementById('teams_tenant_id').value;
                }} else if (service === 'jira') {{
                    payload.server_url = document.getElementById('jira_server_url').value;
                    payload.user_email = document.getElementById('jira_user_email').value;
                    payload.api_token = document.getElementById('jira_api_token').value;
                    payload.project_key = document.getElementById('jira_project_key').value;
                }} else if (service === 'sharepoint') {{
                    payload.site_url = document.getElementById('sp_site_url').value;
                    payload.tenant_id = document.getElementById('sp_tenant_id').value;
                    payload.client_id = document.getElementById('sp_client_id').value;
                    payload.client_secret = document.getElementById('sp_client_secret').value;
                    payload.document_library = document.getElementById('sp_document_library').value;
                }}

                try {{
                    const res = await fetch('/api/connectors/' + service, {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify(payload)
                    }});
                    const data = await res.json();

                    if (data.test_result && data.test_result.success) {{
                        resultBox.className = 'result-box success';
                        const extraMsg = service === 'jira' && data.test_result.total_projects !== undefined
                            ? ` (${{data.test_result.total_projects}} projects fetched)`
                            : '';
                        resultBox.innerText = `✅ SUCCESS: Saved to .env and connected successfully!${{extraMsg}}\\n` + JSON.stringify(data.test_result, null, 2);
                        updateBadge(service, true);

                        if (service === 'jira' && data.test_result.projects) {{
                            renderJiraProjects(data.test_result.projects);
                        }}
                    }} else {{
                        resultBox.className = 'result-box error';
                        const errMsg = data.test_result ? data.test_result.error : (data.detail || 'Connection failed');
                        resultBox.innerText = '⚠️ SAVED, BUT CONNECTION FAILED:\\n' + errMsg + '\\n' + JSON.stringify(data.test_result || data, null, 2);
                        updateBadge(service, data.configured);
                    }}
                    refreshOverview();
                }} catch (err) {{
                    resultBox.className = 'result-box error';
                    resultBox.innerText = '❌ Error sending request: ' + err.message;
                }}
            }}

            async function testOnly(service) {{
                const resultBox = document.getElementById(service + '-result');
                resultBox.style.display = 'block';
                resultBox.className = 'result-box';
                resultBox.innerText = '⏳ Testing connection to ' + service + '...';

                try {{
                    const res = await fetch('/api/connectors/' + service + '/test', {{ method: 'POST' }});
                    const data = await res.json();
                    if (data.success) {{
                        resultBox.className = 'result-box success';
                        resultBox.innerText = '✅ CONNECTED:\\n' + JSON.stringify(data, null, 2);
                        updateBadge(service, true);

                        if (service === 'jira' && data.projects) {{
                            renderJiraProjects(data.projects);
                        }}
                    }} else {{
                        resultBox.className = 'result-box error';
                        resultBox.innerText = '❌ CONNECTION FAILED:\\n' + (data.error || JSON.stringify(data, null, 2));
                    }}
                }} catch (err) {{
                    resultBox.className = 'result-box error';
                    resultBox.innerText = '❌ Error testing connection: ' + err.message;
                }}
            }}

            async function testAll() {{
                const resBox = document.getElementById('all-tests-result');
                resBox.style.display = 'block';
                resBox.className = 'result-box';
                resBox.innerText = '⏳ Testing all connectors simultaneously...';

                try {{
                    const res = await fetch('/api/connectors/test-all', {{ method: 'POST' }});
                    const data = await res.json();
                    resBox.className = 'result-box success';
                    resBox.innerText = '📊 All Tests Completed:\\n' + JSON.stringify(data, null, 2);
                    refreshOverview();
                }} catch (e) {{
                    resBox.className = 'result-box error';
                    resBox.innerText = '❌ Error running tests: ' + e.message;
                }}
            }}

            // Toast handler
            let toastTimer = null;
            function showToast(type, message) {{
                const banner = document.getElementById('toast-banner');
                const content = document.getElementById('toast-content');
                const msgSpan = document.getElementById('toast-message');
                if (!banner || !content || !msgSpan) return;

                content.className = 'toast ' + (type === 'error' ? 'error' : 'success');
                msgSpan.innerText = message;
                banner.style.display = 'block';

                if (toastTimer) clearTimeout(toastTimer);
                toastTimer = setTimeout(() => hideToast(), 8000);
            }}

            function hideToast() {{
                const banner = document.getElementById('toast-banner');
                if (banner) banner.style.display = 'none';
            }}

            // Jira OAuth (3LO) Handlers
            function startJiraOAuth() {{
                const btn = document.getElementById('connect-jira-btn');
                if (btn) {{
                    btn.disabled = true;
                    btn.innerHTML = '<span class="spinner"></span> Connecting Jira...';
                }}
                window.location.href = '/auth/jira';
            }}

            async function disconnectJira() {{
                const btn = document.getElementById('disconnect-jira-btn');
                if (btn) {{
                    btn.disabled = true;
                    btn.innerHTML = '<span class="spinner"></span> Disconnecting...';
                }}

                try {{
                    const res = await fetch('/api/jira/disconnect', {{ method: 'POST' }});
                    const data = await res.json();
                    if (data.success) {{
                        const connectedEl = document.getElementById('jira-oauth-connected');
                        const disconnectedEl = document.getElementById('jira-oauth-disconnected');
                        const projectsEl = document.getElementById('jira-projects-container');
                        if (connectedEl) connectedEl.style.display = 'none';
                        if (disconnectedEl) disconnectedEl.style.display = 'block';
                        if (projectsEl) projectsEl.style.display = 'none';
                        updateBadge('jira', false);
                        showToast('success', 'Jira account disconnected successfully.');
                        refreshOverview();
                    }} else {{
                        showToast('error', 'Failed to disconnect: ' + (data.error || 'Unknown error'));
                    }}
                }} catch (e) {{
                    showToast('error', 'Disconnect error: ' + e.message);
                }} finally {{
                    if (btn) {{
                        btn.disabled = false;
                        btn.innerText = 'Disconnect Jira';
                    }}
                }}
            }}

            function populateProjectSelect(projects) {{
                const sel = document.getElementById('story_project_key');
                if (!sel) return;
                const currentVal = sel.value;
                sel.innerHTML = '<option value="">-- Select a Project --</option>';
                if (!projects || projects.length === 0) return;
                projects.forEach(p => {{
                    const opt = document.createElement('option');
                    opt.value = p.key;
                    opt.textContent = `${{p.key}} - ${{p.name}}`;
                    if (p.key === currentVal) opt.selected = true;
                    sel.appendChild(opt);
                }});
            }}

            async function createStoryInJira() {{
                const btn = document.getElementById('create-story-btn');
                const resultBox = document.getElementById('story-result');
                const projectKey = document.getElementById('story_project_key').value;
                const summary = document.getElementById('story_summary').value;
                const description = document.getElementById('story_description').value;
                const issueType = document.getElementById('story_issue_type').value;

                if (!projectKey) {{
                    showToast('error', 'Please select or enter a Target Project.');
                    return;
                }}
                if (!summary.trim()) {{
                    showToast('error', 'Please enter a Story Summary headline.');
                    return;
                }}

                if (btn) {{
                    btn.disabled = true;
                    btn.innerHTML = '<span class="spinner"></span> Creating Story...';
                }}
                resultBox.style.display = 'block';
                resultBox.className = 'result-box';
                resultBox.innerText = '⏳ Calling Jira API to create ' + issueType + '...';

                try {{
                    const res = await fetch('/api/jira/issues', {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify({{
                            project_key: projectKey,
                            summary: summary,
                            description: description,
                            issue_type: issueType
                        }})
                    }});
                    const data = await res.json();
                    if (res.ok && data.success) {{
                        resultBox.className = 'result-box success';
                        resultBox.innerHTML = `✅ <strong>Successfully Created ${{data.issue_type || 'Story'}} in Jira!</strong><br><br>` +
                            `<strong>Issue Key:</strong> <a href="${{data.url}}" target="_blank" style="color:#60a5fa; font-weight:700; text-decoration:underline;">${{data.key}}</a><br>` +
                            `<strong>Summary:</strong> ${{data.summary}}<br>` +
                            `<strong>Direct Link:</strong> <a href="${{data.url}}" target="_blank" style="color:#60a5fa;">${{data.url}}</a>`;
                        showToast('success', `Jira issue ${{data.key}} created successfully!`);
                        document.getElementById('story_summary').value = '';
                        document.getElementById('story_description').value = '';
                    }} else {{
                        resultBox.className = 'result-box error';
                        resultBox.innerText = '❌ Failed to create issue: ' + (data.detail || data.error || JSON.stringify(data, null, 2));
                        showToast('error', 'Failed to create Jira issue: ' + (data.detail || ''));
                    }}
                }} catch (e) {{
                    resultBox.className = 'result-box error';
                    resultBox.innerText = '❌ Request exception: ' + e.message;
                    showToast('error', 'Error: ' + e.message);
                }} finally {{
                    if (btn) {{
                        btn.disabled = false;
                        btn.innerHTML = '🚀 Create Issue in Jira';
                    }}
                }}
            }}

            async function syncJiraConnectionStatus() {{
                try {{
                    const res = await fetch('/api/jira/connection');
                    const data = await res.json();
                    const disc = document.getElementById('jira-oauth-disconnected');
                    const conn = document.getElementById('jira-oauth-connected');
                    if (data.connected) {{
                        if (disc) disc.style.display = 'none';
                        if (conn) conn.style.display = 'block';
                        if (data.site_name) document.getElementById('oauth-site-name').innerText = data.site_name;
                        if (data.site_url) {{
                            const link = document.getElementById('oauth-site-url');
                            if (link) {{
                                link.innerText = data.site_url;
                                link.href = data.site_url;
                            }}
                        }}
                        const accEl = document.getElementById('oauth-account');
                        if (accEl) {{
                            accEl.innerText = (data.display_name || '') + (data.account_email ? ` (${{data.account_email}})` : '');
                        }}
                        if (data.cloud_id) document.getElementById('oauth-cloud-id').innerText = data.cloud_id;
                        updateBadge('jira', true);

                        // Auto-fetch projects to populate dropdown
                        fetchJiraProjectsOnly();
                    }} else {{
                        if (conn) conn.style.display = 'none';
                        if (disc) disc.style.display = 'block';
                    }}
                }} catch (e) {{}}
            }}

            // Handle URL Parameters and Initial Sync
            document.addEventListener('DOMContentLoaded', () => {{
                const params = new URLSearchParams(window.location.search);
                if (params.get('tab')) {{
                    showTab(params.get('tab'));
                }}

                if (params.get('status') === 'connected') {{
                    showToast('success', 'Jira connected successfully!');
                    syncJiraConnectionStatus();
                    history.replaceState(null, '', window.location.pathname + (params.get('tab') ? '?tab=' + params.get('tab') : ''));
                }} else if (params.get('error')) {{
                    showToast('error', 'Jira Connection Error: ' + params.get('error'));
                    history.replaceState(null, '', window.location.pathname + (params.get('tab') ? '?tab=' + params.get('tab') : ''));
                }} else {{
                    syncJiraConnectionStatus();
                }}
            }});
        </script>
    </body>
    </html>
    """
    return html


# ---------------------------------------------------------
# Jira OAuth 2.0 (3LO) Endpoints
# ---------------------------------------------------------

@app.get("/auth/jira")
async def auth_jira_endpoint(request: Request):
    """
    Start Atlassian Jira Cloud OAuth 2.0 (3LO) authorization flow.
    Generates secure state to prevent CSRF and redirects browser to Atlassian.
    """
    if not jira_oauth.is_configured():
        return RedirectResponse(
            url="/?tab=jira&error=Jira+OAuth+is+not+configured.+Please+set+JIRA_CLIENT_ID,+JIRA_CLIENT_SECRET,+and+JIRA_REDIRECT_URI+in+.env"
        )

    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        user_id = secrets.token_urlsafe(24)
        request.state.user_id = user_id

    state = secrets.token_urlsafe(32)
    oauth_store.save_state(state=state, user_id=user_id)
    auth_url = jira_oauth.get_authorization_url(state=state)
    return RedirectResponse(url=auth_url)


@app.get("/auth/jira/callback")
async def auth_jira_callback(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    error_description: Optional[str] = None,
):
    """
    Receive Atlassian OAuth authorization code, validate CSRF state,
    exchange for access & refresh tokens, retrieve cloud ID and user info,
    and associate connection with the authenticated application user.
    """
    if error:
        err_msg = error_description or error
        return RedirectResponse(url=f"/?tab=jira&error={urllib.parse.quote(err_msg)}")

    if not code or not state:
        return RedirectResponse(url="/?tab=jira&error=Missing+authorization+code+or+state+parameter")

    state_user_id = oauth_store.validate_and_consume_state(state)
    if not state_user_id:
        return RedirectResponse(url="/?tab=jira&error=Invalid+or+expired+OAuth+state+(CSRF+validation+failed)")

    user_id = getattr(request.state, "user_id", None) or state_user_id

    try:
        token_data = await jira_oauth.exchange_code(code)
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in", 3600)

        resources = await jira_oauth.get_accessible_resources(access_token)
        if not resources:
            return RedirectResponse(url="/?tab=jira&error=No+accessible+Jira+Cloud+sites+found+for+this+account")

        primary = resources[0]
        cloud_id = primary.get("id")
        site_name = primary.get("name")
        site_url = primary.get("url")

        user_info = await jira_oauth.get_myself(access_token, cloud_id)
        account_email = user_info.get("emailAddress")
        display_name = user_info.get("displayName") or user_info.get("name")
        avatar_url = (user_info.get("avatarUrls") or {}).get("48x48")

        oauth_store.save_connection(
            user_id=user_id,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expires_in,
            cloud_id=cloud_id,
            site_name=site_name,
            site_url=site_url,
            account_email=account_email,
            display_name=display_name,
            avatar_url=avatar_url,
        )

        return RedirectResponse(url="/?tab=jira&status=connected")
    except Exception as e:
        return RedirectResponse(url=f"/?tab=jira&error={urllib.parse.quote(str(e))}")


@app.get("/api/jira/connection")
async def get_jira_connection_status(request: Request):
    """
    Return current user's Jira connection status and site details.
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return {"connected": False}

    conn = oauth_store.get_connection(user_id)
    if not conn or not conn.cloud_id:
        return {"connected": False}

    return {
        "connected": True,
        "site_name": conn.site_name,
        "site_url": conn.site_url,
        "cloud_id": conn.cloud_id,
        "account_email": conn.account_email,
        "display_name": conn.display_name,
    }


@app.post("/api/jira/disconnect")
async def disconnect_jira_endpoint(request: Request):
    """
    Revoke and remove current user's stored Jira connection and tokens.
    Isolated per application user.
    """
    user_id = getattr(request.state, "user_id", None)
    if user_id:
        oauth_store.delete_connection(user_id)

    return {"success": True, "message": "Jira connection revoked and removed successfully."}


@app.get("/api/jira/projects")
async def get_jira_projects_api(request: Request):
    """
    Retrieve projects available to the connected Jira user (via OAuth or configured credentials).
    """
    user_id = getattr(request.state, "user_id", None)
    conn = oauth_store.get_connection(user_id) if user_id else None

    if conn and conn.cloud_id:
        return await jira_oauth.fetch_projects(user_id)

    # Fallback to API token projects if configured
    if settings.jira.is_configured():
        return await settings.jira.fetch_all_projects()

    raise HTTPException(
        status_code=400,
        detail="Jira is not connected. Please connect Jira via OAuth 2.0 in Settings."
    )


@app.post("/api/jira/issues")
async def create_jira_issue_endpoint(req: JiraCreateIssueRequest, request: Request):
    """
    Create a Jira Story / Issue using the connected user's Jira credentials.
    """
    user_id = getattr(request.state, "user_id", None)
    conn = oauth_store.get_connection(user_id) if user_id else None

    if not conn or not conn.cloud_id:
        raise HTTPException(
            status_code=400,
            detail="Jira is not connected. Please connect your Jira Cloud account in Settings first."
        )

    try:
        return await jira_oauth.create_story(
            user_id=user_id,
            project_key=req.project_key,
            summary=req.summary,
            description=req.description,
            issue_type=req.issue_type,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------
# REST API Endpoints (Update & Test)
# ---------------------------------------------------------

@app.get("/api/status")
def get_status() -> Dict[str, bool]:
    """Get configuration status of all registered connectors."""
    return settings.status_summary()


@app.get("/api/settings")
def get_settings() -> Dict[str, Any]:
    """Get full configuration tree (with secrets masked)."""
    return settings.to_dict(mask_secrets=True)


@app.get("/api/connectors/jira/projects")
async def get_jira_projects_endpoint(request: Request):
    """
    Fetch every project's details from the connected Jira workspace
    (Key, Name, ID, Lead, Issue Types, URL, etc.).
    """
    return await get_jira_projects_api(request)


@app.post("/api/connectors/teams")
async def update_teams_endpoint(req: TeamsUpdateRequest):
    """
    Update Teams configuration settings, persist to .env, and optionally test connection.
    """
    settings.update_teams(
        webhook_url=req.webhook_url,
        client_id=req.client_id,
        client_secret=req.client_secret,
        tenant_id=req.tenant_id,
    )

    if req.persist_to_env:
        settings.save_to_env(".env")

    test_res = None
    if req.test_now and settings.teams.is_configured():
        test_res = await settings.teams.test_connection()

    return {
        "message": "Microsoft Teams settings updated successfully.",
        "configured": settings.teams.is_configured(),
        "test_result": test_res,
        "settings": settings.teams.to_dict(mask_secrets=True),
    }


@app.post("/api/connectors/teams/test")
async def test_teams_endpoint():
    """Run live connection test for Microsoft Teams."""
    return await settings.teams.test_connection()


@app.post("/api/connectors/jira")
async def update_jira_endpoint(req: JiraUpdateRequest):
    """
    Update Jira configuration settings, persist to .env, and optionally test connection & fetch all projects.
    """
    settings.update_jira(
        server_url=req.server_url,
        user_email=req.user_email,
        api_token=req.api_token,
        project_key=req.project_key,
    )

    if req.persist_to_env:
        settings.save_to_env(".env")

    test_res = None
    if req.test_now and settings.jira.is_configured():
        test_res = await settings.jira.test_connection()

    return {
        "message": "Atlassian Jira settings updated successfully.",
        "configured": settings.jira.is_configured(),
        "test_result": test_res,
        "settings": settings.jira.to_dict(mask_secrets=True),
    }


@app.post("/api/connectors/jira/test")
async def test_jira_endpoint():
    """Run live connection test for Atlassian Jira and fetch all project details."""
    return await settings.jira.test_connection()


@app.post("/api/connectors/sharepoint")
async def update_sharepoint_endpoint(req: SharePointUpdateRequest):
    """
    Update SharePoint configuration settings, persist to .env, and optionally test connection.
    """
    settings.update_sharepoint(
        site_url=req.site_url,
        tenant_id=req.tenant_id,
        client_id=req.client_id,
        client_secret=req.client_secret,
        document_library=req.document_library,
    )

    if req.persist_to_env:
        settings.save_to_env(".env")

    test_res = None
    if req.test_now and settings.sharepoint.is_configured():
        test_res = await settings.sharepoint.test_connection()

    return {
        "message": "Microsoft SharePoint settings updated successfully.",
        "configured": settings.sharepoint.is_configured(),
        "test_result": test_res,
        "settings": settings.sharepoint.to_dict(mask_secrets=True),
    }


@app.post("/api/connectors/sharepoint/test")
async def test_sharepoint_endpoint():
    """Run live connection test for Microsoft SharePoint."""
    return await settings.sharepoint.test_connection()


@app.post("/api/connectors/test-all")
async def test_all_connectors_endpoint():
    """Run live connection tests across all connectors simultaneously."""
    return await settings.test_all()


@app.post("/api/settings/save")
def persist_settings_endpoint():
    """Persist current in-memory settings to the .env file."""
    settings.save_to_env(".env")
    return {"message": "Settings successfully persisted to .env"}


def cli_main():
    """CLI launcher for local testing and server start."""
    if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print("=" * 65)
    print(" 🔌 Connector Settings & Project Discovery - Server Starting")
    print("=" * 65)
    print(f"[+] Environment : {settings.environment}")
    print(f"[+] Log Level   : {settings.log_level}")
    print("\n--- Connector Configuration Status ---")

    for connector_name, is_active in settings.status_summary().items():
        status_str = "[OK] CONFIGURED" if is_active else "[X] NOT CONFIGURED"
        print(f" - {connector_name.capitalize():<12}: {status_str}")

    print("\n--- Starting FastAPI Server on http://127.0.0.1:8000 ---")
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)


if __name__ == "__main__":
    cli_main()
