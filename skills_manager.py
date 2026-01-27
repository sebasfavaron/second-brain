"""Skill management utilities for the Telegram agent."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from config import BASE_DIR

SKILLS_DIR = BASE_DIR / "skills"
DISABLED_MARKER = "DISABLED"
SKILL_FILE = "SKILL.md"


def _ensure_skills_dir() -> None:
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)


def _skill_dir(name: str) -> Path:
    # Restrict to simple folder names to avoid path traversal.
    safe_name = name.strip().replace("..", "").replace("/", "").replace("\\", "")
    return SKILLS_DIR / safe_name


def list_skills() -> List[Dict]:
    """List skills and their status."""
    _ensure_skills_dir()
    results: List[Dict] = []

    for item in sorted(SKILLS_DIR.iterdir()):
        if not item.is_dir():
            continue
        skill_path = item
        disabled = (skill_path / DISABLED_MARKER).exists()
        skill_file = skill_path / SKILL_FILE
        results.append({
            "name": skill_path.name,
            "path": str(skill_path),
            "enabled": not disabled,
            "has_skill_file": skill_file.exists(),
        })

    return results


def enable_skill(name: str) -> Dict:
    """Enable a skill by removing the DISABLED marker."""
    skill_path = _skill_dir(name)
    if not skill_path.exists():
        return {"success": False, "error": "Skill not found"}

    marker = skill_path / DISABLED_MARKER
    if marker.exists():
        marker.unlink()

    return {"success": True, "name": skill_path.name, "enabled": True}


def disable_skill(name: str) -> Dict:
    """Disable a skill by creating the DISABLED marker."""
    skill_path = _skill_dir(name)
    if not skill_path.exists():
        return {"success": False, "error": "Skill not found"}

    marker = skill_path / DISABLED_MARKER
    marker.write_text("disabled", encoding="utf-8")

    return {"success": True, "name": skill_path.name, "enabled": False}


def load_skills_prompt() -> str:
    """Load enabled skills into a single prompt block."""
    _ensure_skills_dir()
    parts: List[str] = []

    for skill in list_skills():
        if not skill["enabled"]:
            continue
        skill_path = Path(skill["path"])
        skill_file = skill_path / SKILL_FILE
        if not skill_file.exists():
            continue
        try:
            content = skill_file.read_text(encoding="utf-8")
        except Exception:
            continue

        parts.append(f"SKILL: {skill['name']}\n{content.strip()}")

    if not parts:
        return ""

    return "\n\n".join(parts)


def install_skill_from_git(name: str, repo_url: str) -> Dict:
    """Install a skill by cloning a git repo into the skills directory."""
    import subprocess

    _ensure_skills_dir()
    target_dir = _skill_dir(name)

    if target_dir.exists():
        return {"success": False, "error": "Skill already exists"}

    try:
        result = subprocess.run(
            ["git", "clone", repo_url, str(target_dir)],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            return {
                "success": False,
                "error": result.stderr.strip() or "git clone failed",
            }

        return {
            "success": True,
            "name": target_dir.name,
            "path": str(target_dir),
        }

    except Exception as exc:
        return {"success": False, "error": str(exc)}


def remove_skill(name: str) -> Dict:
    """Remove a skill directory."""
    import shutil

    skill_path = _skill_dir(name)
    if not skill_path.exists():
        return {"success": False, "error": "Skill not found"}

    try:
        shutil.rmtree(skill_path)
        return {"success": True, "name": skill_path.name, "removed": True}
    except Exception as exc:
        return {"success": False, "error": str(exc)}
