"""
version_check.py - Non-blocking dependency version checker

Usage:
    from version_check import warn_if_outdated
    warn_if_outdated("iterm2-scripts", __version__)

Features:
- Background thread (no startup delay)
- XDG-compliant caching (2-week fetch, 1-week warn intervals)
- Environment variable to disable (ITERM2_SCRIPTS_NO_UPDATE_CHECK=1)
- Fail-silent on all errors
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.request
from pathlib import Path

try:
    from platformdirs import user_cache_dir
    from packaging.version import parse as parse_version
except ImportError:
    # Fail silently if deps missing
    def warn_if_outdated(*args, **kwargs): pass
else:
    CACHE_FILE = Path(user_cache_dir("iterm2-scripts")) / "version_cache.json"
    FETCH_INTERVAL = 14 * 24 * 60 * 60  # 2 weeks
    WARN_INTERVAL = 7 * 24 * 60 * 60    # 1 week
    ENV_DISABLE = "ITERM2_SCRIPTS_NO_UPDATE_CHECK"

    def _fetch_latest(package: str) -> str | None:
        try:
            url = f"https://api.github.com/repos/terrylica/{package}/releases/latest"
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
                return data.get("tag_name", "").lstrip("v")
        except Exception:
            return None

    def _read_cache() -> dict:
        try:
            return json.loads(CACHE_FILE.read_text()) if CACHE_FILE.exists() else {}
        except Exception:
            return {}

    def _write_cache(data: dict) -> None:
        try:
            CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            CACHE_FILE.write_text(json.dumps(data))
        except Exception:
            pass

    def warn_if_outdated(package: str, current: str, background: bool = True) -> None:
        if os.environ.get(ENV_DISABLE):
            return

        def _check():
            try:
                now = time.time()
                cache = _read_cache()
                if now - cache.get("last_warned", 0) < WARN_INTERVAL:
                    return
                if now - cache.get("last_fetched", 0) > FETCH_INTERVAL:
                    latest = _fetch_latest(package)
                    if latest:
                        cache["latest"] = latest
                        cache["last_fetched"] = now
                        _write_cache(cache)
                latest = cache.get("latest")
                if latest and parse_version(current) < parse_version(latest):
                    print(f"\n[Update] {package} {latest} available (you have {current})\n", file=sys.stderr)
                    cache["last_warned"] = now
                    _write_cache(cache)
            except Exception:
                pass

        if background:
            threading.Thread(target=_check, daemon=True).start()
        else:
            _check()
