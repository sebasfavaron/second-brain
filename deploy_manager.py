"""Deployment helper for pushing changes and restarting remote service via SSH."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Dict, Optional

from config import BASE_DIR

DEPLOY_FILE = BASE_DIR / ".deploy"


def _load_deploy_config() -> Dict[str, str]:
    config: Dict[str, str] = {}
    if not DEPLOY_FILE.exists():
        return config
    for line in DEPLOY_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        config[key.strip()] = value.strip()
    return config


def deploy_remote(commit_message: Optional[str] = None) -> Dict:
    """Commit/push locally and then pull+restart on remote via SSH."""
    config = _load_deploy_config()
    ssh_host = config.get("SSH_HOST")
    remote_dir = config.get("REMOTE_DIR")
    service_name = config.get("SERVICE_NAME", "second-brain-bot.service")

    if not ssh_host or not remote_dir:
        return {"success": False, "error": "Missing SSH_HOST or REMOTE_DIR in .deploy"}

    try:
        subprocess.run(["git", "add", "-A"], cwd=str(BASE_DIR), check=False)

        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            check=False,
        )
        if status.stdout.strip():
            message = commit_message or "Update via Telegram admin"
            commit = subprocess.run(
                ["git", "commit", "-m", message],
                cwd=str(BASE_DIR),
                capture_output=True,
                text=True,
                check=False,
            )
            if commit.returncode != 0:
                return {"success": False, "error": commit.stderr.strip() or commit.stdout.strip()}

            push = subprocess.run(
                ["git", "push"],
                cwd=str(BASE_DIR),
                capture_output=True,
                text=True,
                check=False,
            )
            if push.returncode != 0:
                return {"success": False, "error": push.stderr.strip() or push.stdout.strip()}

        remote_cmd = (
            f"cd {remote_dir} && git pull && "
            f"sudo systemctl restart {service_name} && "
            f"sudo systemctl status {service_name} --no-pager -l | sed -n '1,12p'"
        )

        ssh = subprocess.run(
            ["ssh", ssh_host, remote_cmd],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            check=False,
        )
        if ssh.returncode != 0:
            return {"success": False, "error": ssh.stderr.strip() or ssh.stdout.strip()}

        return {
            "success": True,
            "remote": ssh_host,
            "service": service_name,
            "output": ssh.stdout.strip(),
        }

    except Exception as exc:
        return {"success": False, "error": str(exc)}
