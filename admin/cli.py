import sys
import json
import argparse
import asyncio
from pathlib import Path

# Add project root directory to sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from admin.jira_provisioner import JiraAdminProvisioner


def parse_args():
    parser = argparse.ArgumentParser(
        description="Admin CLI: Provision Jira Projects, Components, Versions, and User Stories from JSON files in the data/ directory."
    )
    parser.add_argument(
        "--file",
        type=str,
        default="jira_projects.json",
        help="Name of the JSON specification file inside the data/ directory (default: jira_projects.json)",
    )
    return parser.parse_args()


async def run_cli():
    if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    args = parse_args()
    print("=" * 65)
    print(" Admin Jira Project Provisioner Engine")
    print("=" * 65)

    provisioner = JiraAdminProvisioner()
    file_name = args.file

    print(f"[+] Server URL : {provisioner.settings.jira.server_url}")
    print(f"[+] User Email : {provisioner.settings.jira.user_email}")
    print(f"[+] Target File: data/{file_name}")
    print("\n⏳ Provisioning Jira projects and related items...")

    try:
        res = await provisioner.provision_from_data_file(file_name)
        print("\n✅ PROVISIONING COMPLETE!")
        print("-" * 45)
        print(json.dumps(res, indent=2))
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run_cli())
