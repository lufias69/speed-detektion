import json
import logging
import os
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger("speedmonitor")


def check_for_update(current_version: str, repo_dir: str = ".") -> bool:
    """Check if a newer version is available on the remote git repository."""
    try:
        result = subprocess.run(
            ["git", "-C", repo_dir, "ls-remote", "origin", "HEAD"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return False
        remote_hash = result.stdout.strip().split()[0]
        local_result = subprocess.run(
            ["git", "-C", repo_dir, "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if local_result.returncode != 0:
            return False
        local_hash = local_result.stdout.strip()
        return remote_hash != local_hash
    except Exception as exc:
        logger.warning("update check failed: %s", exc)
        return False


def perform_update(repo_dir: str = ".") -> bool:
    """Pull the latest code from the remote repository."""
    try:
        logger.info("performing update...")
        result = subprocess.run(
            ["git", "-C", repo_dir, "pull", "origin", "master"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        success = result.returncode == 0
        if success:
            logger.info("update complete: %s", result.stdout.strip())
        else:
            logger.warning("update failed: %s", result.stderr.strip())
        return success
    except Exception as exc:
        logger.warning("update error: %s", exc)
        return False
