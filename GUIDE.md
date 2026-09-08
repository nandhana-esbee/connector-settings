# 📘 Connector Module User & Integration Guide

Welcome to the comprehensive guide for **Connector Settings Module** (`connector`). This guide explains what this tool is, the problems it solves, how it works under the hood, how to input values via the interactive UI/API, and how it actively connects and verifies **Microsoft Teams**, **Atlassian Jira**, **Microsoft SharePoint**, and custom connectors into any Python application.

---

## 🎯 What Does This Tool Do?

In modern multi-service software development, enterprise software often needs to interact with multiple external platforms:
- Sending alert cards or notifications to **Microsoft Teams**.
- Creating, tracking, or updating tickets in **Atlassian Jira**.
- Uploading, reading, or managing files in **Microsoft SharePoint**.
- Communicating with internal tools or custom REST APIs.

### The Problem
Without a centralized module, developers usually:
1. Duplicate `.env` parsing logic across different microservices.
2. Hardcode configuration keys and authentication schemas in multiple places.
3. Risk accidentally exposing raw secrets in log outputs.
4. Struggle to validate whether all required credentials for an integration are present before making API calls.
5. Have no easy way to live-test if credentials actually work.

### The Solution
The **Connector Settings Module** (`connector`) provides a unified, reusable Python package that acts as a single source of truth for integration settings. It:
- **Collects Settings Interactively**: Accepts inputs from users via Web UI, REST API, or `.env` files.
- **Validates & Tests Connections Live**: Performs real authentication and ping tests against Microsoft Teams, Atlassian Jira, and SharePoint APIs.
- **Normalizes Configuration**: Loads environment variables into type-annotated data structures.
- **Protects Secrets**: Offers built-in secret masking for safe logging and debugging.
- **Plugs into Any Project**: Can be imported as a dependency or module into any Python repository.

---

## 🏗️ Architecture & Component Overview

```text
               +----------------------------------------+
               |     User Input (Web Dashboard / API)   |
               |        or .env Configuration File      |
               +----------------------------------------+
                                   |
                                   v
               +----------------------------------------+
               |          ConnectorSettings             |
               |     (base.py & FastAPI in main.py)     |
               +----------------------------------------+
                   /               |                \
                  /                |                 \
                 v                 v                  v
    +--------------------+  +---------------+  +--------------------+
    |   TeamsSettings    |  | JiraSettings  |  | SharePointSettings |
    |  - Webhook POST    |  | - /myself API |  | - OAuth2 v2.0 token|
    |  - Graph API OAuth |  | - Project API |  | - Graph Site API   |
    +--------------------+  +---------------+  +--------------------+
```

---

## 🖥️ Using the Interactive Web Dashboard

Start the server:
```bash
uvicorn main:app --reload
```
Open **`http://127.0.0.1:8000`** in your browser.

### Key Capabilities in the Dashboard:
1. **Interactive Forms**: Enter credentials for Microsoft Teams, Jira, and SharePoint with visual feedback.
2. **⚡ Test Connection**: Pings the remote API with the provided credentials and returns connection latency, user profiles, or error details.
3. **💾 Save & Test Connection**: Writes valid credentials to `.env` and confirms live connectivity.
4. **🚀 Run All Connection Tests**: Tests all configured connectors simultaneously in parallel.
5. **📖 Swagger Docs**: Access interactive API documentation at `http://127.0.0.1:8000/docs`.

---

## 🚀 How to Connect Each Service

### 1. Microsoft Teams (`TEAMS_*`)

Teams integrations support two access modes:

#### Mode A: Incoming Webhook (Simplest for sending messages)
- **Use Case**: Sending channel notifications, automated alerts, build reports.
- **Setup in Teams**:
  1. Open a Channel in Microsoft Teams.
  2. Click `...` (More options) -> **Connectors** (or **Workflows**).
  3. Select **Incoming Webhook**, name it, and copy the Webhook URL.
- **Configuration**:
  ```env
  TEAMS_WEBHOOK_URL=https://outlook.office.com/webhook/your-unique-id
  ```

#### Mode B: Azure AD / Microsoft Graph (For full Graph API capabilities)
- **Setup in Azure Portal**:
  1. Go to Azure Active Directory (Entra ID) -> **App registrations**.
  2. Register a new application.
  3. Under **Certificates & secrets**, generate a Client Secret.
- **Configuration**:
  ```env
  TEAMS_CLIENT_ID=your-azure-app-client-id
  TEAMS_CLIENT_SECRET=your-azure-app-client-secret
  TEAMS_TENANT_ID=your-azure-tenant-id
  ```

---

### 2. Atlassian Jira (`JIRA_*`)

The Jira connector configures authentication for Atlassian Jira Cloud or Data Center.

#### Setup Instructions:
1. Log in to [id.atlassian.com/manage-profile/security/api-tokens](https://id.atlassian.com/manage-profile/security/api-tokens).
2. Click **Create API token**, label it (e.g., `connector-integration`), and copy the generated token.
3. Obtain your Atlassian domain URL (e.g., `https://your-company.atlassian.net`).
4. Note down your target Jira Project Key (e.g., `PROJ`, `KAN`, `SUP`).

#### Configuration:
```env
JIRA_SERVER_URL=https://your-company.atlassian.net
JIRA_USER_EMAIL=developer@yourcompany.com
JIRA_API_TOKEN=your_jira_api_token
JIRA_DEFAULT_PROJECT_KEY=PROJ
```

---

### 3. Microsoft SharePoint (`SHAREPOINT_*`)

SharePoint integrations use Azure AD App-Only Client Credentials to access site libraries securely without user prompts.

#### Setup Instructions:
1. In Azure Active Directory (Entra ID), register an Application for SharePoint access.
2. Grant API Permissions (e.g., `Sites.FullControl.All` or `Sites.ReadWrite.All` under Microsoft Graph or SharePoint).
3. Create a **Client Secret**.
4. Obtain your SharePoint Site URL (e.g., `https://yourtenant.sharepoint.com/sites/Development`).

#### Configuration:
```env
SHAREPOINT_SITE_URL=https://yourtenant.sharepoint.com/sites/YourSite
SHAREPOINT_TENANT_ID=your-tenant-id
SHAREPOINT_CLIENT_ID=your-client-id
SHAREPOINT_CLIENT_SECRET=your-client-secret
SHAREPOINT_DOCUMENT_LIBRARY=Shared Documents
```

---

## 💻 How to Use `connector` in Your Project (Python Code)

### 1. Load Settings and Test Connections in Python

```python
import asyncio
from connector import ConnectorSettings

async def main():
    # 1. Load settings (automatically reads .env file)
    settings = ConnectorSettings.load(env_file=".env")

    # 2. Check configuration status
    print("Status:", settings.status_summary())

    # 3. Live-test Jira connection
    if settings.jira.is_configured():
        jira_result = await settings.jira.test_connection()
        print("Jira Connection Test:", jira_result)

    # 4. Live-test Teams connection
    if settings.teams.is_configured():
        teams_result = await settings.teams.test_connection()
        print("Teams Connection Test:", teams_result)

    # 5. Live-test SharePoint connection
    if settings.sharepoint.is_configured():
        sp_result = await settings.sharepoint.test_connection()
        print("SharePoint Connection Test:", sp_result)

    # 6. Test all simultaneously
    all_results = await settings.test_all()
    print("All Results:", all_results)

if __name__ == "__main__":
    asyncio.run(main())
```

### 2. Updating Settings Programmatically

```python
from connector import ConnectorSettings

settings = ConnectorSettings.load()

# Update settings dynamically
settings.update_jira(
    server_url="https://myorg.atlassian.net",
    user_email="dev@myorg.com",
    api_token="secret-token-here",
    project_key="DEV"
)

# Persist to .env file
settings.save_to_env(".env")
```

---

## 📡 REST API Reference

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/` | `GET` | Interactive Web Configuration Dashboard |
| `/docs` | `GET` | Swagger Interactive API Documentation |
| `/api/status` | `GET` | Returns boolean status for all connectors |
| `/api/settings` | `GET` | Returns full settings tree (secrets masked) |
| `/api/connectors/teams` | `POST` | Update Teams settings & test connection |
| `/api/connectors/teams/test` | `POST` | Run live connection test for Teams |
| `/api/connectors/jira` | `POST` | Update Jira settings & test connection |
| `/api/connectors/jira/test` | `POST` | Run live connection test for Jira |
| `/api/connectors/sharepoint` | `POST` | Update SharePoint settings & test connection |
| `/api/connectors/sharepoint/test` | `POST` | Run live connection test for SharePoint |
| `/api/connectors/test-all` | `POST` | Run live connection tests across all connectors |
