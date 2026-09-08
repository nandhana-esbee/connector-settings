# Connector Settings Module

A flexible, lightweight, and modular Python settings package designed to centralize and streamline configurations for connecting external services—such as **Microsoft Teams**, **Atlassian Jira**, **Microsoft SharePoint**, and custom integrations—into any Python application or project.

---

## 🚀 Overview

The **Connector Settings Module** (`connector`) simplifies credentials and configuration management for multi-service enterprise workflows. Instead of duplicating connector setup code across different microservices or projects, this package provides a clean, unified configuration layer with validation support, secure environment handling, and easy extensibility.

---

## ✨ Key Features

- ⚙️ **Centralized Settings**: Store and manage configuration schemas for all your integrations in one reusable module.
- 💬 **Microsoft Teams Integration**: Pre-configured support for incoming webhooks, Microsoft Graph API credentials, and Bot Framework settings.
- 📋 **Jira Connector**: Configurations for Atlassian Jira Cloud/Data Center API tokens, OAuth 2.0, server URLs, and project/issue defaults.
- 📁 **SharePoint Integration**: Ready-to-use authentication schemas for Azure AD / Entra ID Client ID/Secret, Tenant ID, Site URLs, and Document Library targets.
- 🔌 **Extensible Design**: Seamlessly add custom connectors (e.g., Slack, GitHub, Confluence, AWS S3, or custom REST webhooks).
- 🛡️ **Environment & Validation Ready**: Built to work smoothly with standard environment variables (`.env`), Python `dataclasses`, or `pydantic-settings`.

---

## 🛠️ Requirements & Installation

### Requirements
- **Python**: `>= 3.12`
- Project management with [`uv`](https://github.com/astral-sh/uv) or standard `pip` / `venv`.

### Quick Setup

```bash
# Clone the repository
git clone https://github.com/nandhana-esbee/connector-settings.git
cd connector

# Create and activate virtual environment (Windows PowerShell example)
python -m venv venv
.\venv\Scripts\activate

# Install dependencies (or sync with uv)
uv sync
```

---

## 📖 Quickstart Guide

### 1. Environment Configuration (`.env`)

Create a `.env` file in your root project directory:

```env
# General Settings
ENVIRONMENT=development
LOG_LEVEL=INFO

# Microsoft Teams Configuration
TEAMS_WEBHOOK_URL=https://outlook.office.com/webhook/your-webhook-id
TEAMS_CLIENT_ID=your-azure-client-id
TEAMS_CLIENT_SECRET=your-azure-client-secret

# Atlassian Jira Configuration
JIRA_SERVER_URL=https://your-domain.atlassian.net
JIRA_API_TOKEN=your-jira-api-token
JIRA_USER_EMAIL=user@company.com
JIRA_DEFAULT_PROJECT_KEY=PROJ

# Microsoft SharePoint Configuration
SHAREPOINT_SITE_URL=https://yourtenant.sharepoint.com/sites/YourSite
SHAREPOINT_TENANT_ID=your-tenant-id
SHAREPOINT_CLIENT_ID=your-app-client-id
SHAREPOINT_CLIENT_SECRET=your-app-client-secret
```

### 2. Using in Your Project

Import and utilize the connector settings module within any project module:

```python
from connector import ConnectorSettings

# Load configuration from environment or settings file
settings = ConnectorSettings.load()

# Access Teams credentials
print(f"Teams Webhook: {settings.teams.webhook_url}")

# Access Jira credentials
print(f"Jira Server: {settings.jira.server_url}")

# Access SharePoint credentials
print(f"SharePoint Site: {settings.sharepoint.site_url}")
```

---

## 📂 Project Structure

```text
connector/
├── connector/               # Main package module
│   ├── __init__.py          # Module exports
│   ├── base.py              # Core settings loader & validation
│   └── integrations/        # Service-specific configurations
│       ├── teams.py         # MS Teams settings schema
│       ├── jira.py          # Jira settings schema
│       └── sharepoint.py    # SharePoint settings schema
├── pyproject.toml           # Project dependencies and packaging configuration
├── README.md                # Project documentation
└── .env.example             # Template for required environment variables
```

---

## 🔌 Supported Connectors

| Connector | Supported Authentication / Features |
| :--- | :--- |
| **Microsoft Teams** | Incoming Webhooks, Azure AD App Registration (OAuth2 / Client Credentials), Graph API |
| **Atlassian Jira** | API Tokens, Basic Auth, OAuth 2.0, Custom Field Mappings |
| **SharePoint** | Graph API, App-Only Authentication (Client Credentials), Document Library REST APIs |
| *(Custom Connectors)* | Easily subclass base settings to register new service integrations |

---

## 📝 License

This module is maintained by **nandhana-esbee**. Distributed under the MIT License. See `LICENSE` for more information.
