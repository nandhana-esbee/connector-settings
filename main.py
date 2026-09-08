import sys
import json
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
import uvicorn

from connector import ConnectorSettings

# Initialize FastAPI App
app = FastAPI(
    title="Connector Settings & Integration API",
    description="Centralized settings management and live connection testing service for Microsoft Teams, Jira, SharePoint, and custom connectors.",
    version="0.2.0",
)

# Load global Connector Settings instance
settings = ConnectorSettings.load(env_file=".env")


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
    test_now: bool = Field(True, description="Immediately test connection after saving")
    persist_to_env: bool = Field(True, description="Save changes to .env file")


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
def get_dashboard():
    """Renders the modern interactive connector configuration and testing dashboard."""
    raw_config = settings.to_dict(mask_secrets=False)
    
    teams = raw_config["connectors"]["teams"]
    jira = raw_config["connectors"]["jira"]
    sp = raw_config["connectors"]["sharepoint"]

    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Connector Settings & Integration Hub</title>
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
            <header>
                <div class="badge-header">Unified Integration Hub</div>
                <h1>🔌 Connector Settings & Integration Module</h1>
                <p class="subtitle">Configure and live-test credentials for Microsoft Teams, Atlassian Jira, SharePoint, and custom connectors.</p>
            </header>

            <div class="tabs-nav">
                <button class="tab-btn active" onclick="showTab('teams')">💬 Microsoft Teams</button>
                <button class="tab-btn" onclick="showTab('jira')">📋 Atlassian Jira</button>
                <button class="tab-btn" onclick="showTab('sharepoint')">📁 SharePoint</button>
                <button class="tab-btn" onclick="showTab('overview')">📊 Overview & JSON</button>
            </div>

            <!-- TEAMS TAB -->
            <div id="tab-teams" class="tab-content active">
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

            <!-- JIRA TAB -->
            <div id="tab-jira" class="tab-content">
                <div class="card">
                    <div class="card-header">
                        <div class="card-title">Atlassian Jira Configuration</div>
                        <span id="jira-badge" class="status-pill {'status-configured' if jira.get('is_configured') else 'status-unconfigured'}">
                            {'CONNECTED / READY' if jira.get('is_configured') else 'NOT CONFIGURED'}
                        </span>
                    </div>
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
                                <label for="jira_project_key">Default Project Key (Optional)</label>
                                <input type="text" id="jira_project_key" value="{jira.get('project_key') or ''}" placeholder="PROJ">
                            </div>
                        </div>
                        <div class="actions">
                            <button type="button" class="btn btn-secondary" onclick="testOnly('jira')">⚡ Test Connection</button>
                            <button type="submit" class="btn btn-primary">💾 Save & Test Connection</button>
                        </div>
                    </form>
                    <div id="jira-result" class="result-box"></div>
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
                <a href="/api/settings" target="_blank">🔍 Raw Masked JSON</a> |
                <a href="/api/status" target="_blank">📊 Status API</a>
            </div>
        </div>

        <script>
            function showTab(name) {{
                document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
                document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
                
                const btnIndex = ['teams', 'jira', 'sharepoint', 'overview'].indexOf(name);
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

            async function saveAndTest(service) {{
                const resultBox = document.getElementById(service + '-result');
                resultBox.style.display = 'block';
                resultBox.className = 'result-box';
                resultBox.innerText = '⏳ Saving configuration and testing connection to ' + service + '...';

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
                        resultBox.innerText = '✅ SUCCESS: Saved to .env and connected successfully!\\n' + JSON.stringify(data.test_result, null, 2);
                        updateBadge(service, true);
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
        </script>
    </body>
    </html>
    """
    return html


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
    Update Jira configuration settings, persist to .env, and optionally test connection.
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
    """Run live connection test for Atlassian Jira."""
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
    print(" 🔌 Connector Settings & Integration Module - Server Starting")
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
