#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["iterm2", "loguru", "platformdirs"]
# ///
"""
Claude Code Orphan Process Cleanup Daemon

Automatically kills orphaned Claude Code processes when iTerm2 sessions terminate.
Orphaned processes are those with no controlling terminal (TTY = "??").

How it works:
1. Monitors all iTerm2 session terminations via SessionTerminationMonitor
2. On any session close, checks for orphaned Claude processes
3. Kills orphaned processes to reclaim memory

Installation:
1. Symlink to AutoLaunch:
   ln -s ~/scripts/iterm2/claude-orphan-cleanup.py \
   "$HOME/Library/Application Support/iTerm2/Scripts/AutoLaunch/"
2. Restart iTerm2 (or run from Scripts menu)

Requirements:
- iTerm2 Python API enabled (Preferences > General > Magic > Enable Python API)

Logs:
- Console: stderr (visible in iTerm2 Script Console)
- File: ~/Library/Logs/claude-orphan-cleanup/*.jsonl (NDJSON, rotated)

ADR: None yet - experimental
"""

from __future__ import annotations

import asyncio
import json
import os
import platform
import subprocess
import sys
import threading
import time
import traceback
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import iterm2
import platformdirs
from loguru import logger

# =============================================================================
# Constants
# =============================================================================

COMPONENT = "claude-orphan-cleanup"
VERSION = "1.0.0"

# Correlation ID for tracing async operations
trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")


# =============================================================================
# Structured Logging Setup (NDJSON format)
# =============================================================================


def get_environment() -> dict[str, Any]:
    """Get environment metadata for log context."""
    return {
        "hostname": platform.node(),
        "platform": platform.system(),
        "platform_version": platform.release(),
        "python_version": platform.python_version(),
        "component": COMPONENT,
        "component_version": VERSION,
    }


ENV_CONTEXT = get_environment()


def json_sink(message) -> None:
    """
    NDJSON sink for structured logging.

    Writes machine-readable JSON to stderr (visible in iTerm2 Script Console).
    """
    record = message.record

    # Build stable core schema
    log_entry = {
        # Core fields (stable schema)
        "timestamp": record["time"].astimezone(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S.%f"
        )[:-3] + "Z",
        "level": record["level"].name.lower(),
        "message": record["message"],
        "component": COMPONENT,
        "logger": record["name"],
        # Environment
        "environment": ENV_CONTEXT,
        # Process identification
        "pid": os.getpid(),
        "tid": threading.current_thread().ident,
        # Correlation IDs
        "trace_id": record["extra"].get("trace_id") or trace_id_var.get() or None,
        "session_id": record["extra"].get("session_id"),
        # Structured context
        "operation": record["extra"].get("operation"),
        "operation_status": record["extra"].get("status"),
        "context": {
            k: v for k, v in record["extra"].items()
            if k not in ("operation", "status", "trace_id", "session_id", "metrics")
        },
        "metrics": record["extra"].get("metrics", {}),
        # Error details (if any)
        "error": None,
    }

    # Handle exceptions
    if record["exception"]:
        exc_type, exc_value, exc_tb = record["exception"]
        tb_lines = traceback.format_tb(exc_tb) if exc_tb else []

        log_entry["error"] = {
            "type": exc_type.__name__ if exc_type else "Unknown",
            "message": str(exc_value) if exc_value else "Unknown error",
            "traceback": tb_lines,
        }

    # Write to stderr (iTerm2 Script Console)
    # Graceful degradation - logging must never crash the app
    # But we still want visibility into logging failures
    try:
        sys.stderr.write(json.dumps(log_entry, default=str) + "\n")
        sys.stderr.flush()
    except (IOError, OSError, TypeError, ValueError) as e:
        # Last-resort fallback: write plain text error to stderr
        # These are the only exceptions json.dumps/write can raise
        try:
            sys.stderr.write(f"[LOG_ERROR] Failed to write log: {e}\n")
        except (IOError, OSError):
            pass  # Truly nothing we can do if stderr itself is broken


def setup_logger() -> None:
    """
    Configure loguru for machine-readable NDJSON output.

    Outputs:
    - stderr: NDJSON for iTerm2 Script Console
    - File: NDJSON with rotation in OS-appropriate log directory
    """
    logger.remove()

    # Console output (NDJSON to stderr via custom sink)
    logger.add(
        json_sink,
        level="DEBUG",  # Capture all levels for observability
        backtrace=True,
        diagnose=True,
    )

    # File output with rotation
    # macOS: ~/Library/Logs/claude-orphan-cleanup/
    log_dir = Path(platformdirs.user_log_dir(
        appname="claude-orphan-cleanup",
        ensure_exists=True
    ))

    logger.add(
        str(log_dir / "daemon.jsonl"),
        level="DEBUG",
        format="{message}",  # Raw JSON (we serialize in json_sink)
        serialize=True,      # loguru's built-in JSON serialization
        rotation="10 MB",    # Rotate at 10MB
        retention="7 days",  # Keep 7 days
        compression="gz",    # Compress old logs
        backtrace=True,
        diagnose=True,
    )

    logger.info(
        "Logger initialized",
        operation="setup_logger",
        status="success",
        log_dir=str(log_dir),
    )


# =============================================================================
# Data Structures
# =============================================================================


@dataclass
class OrphanedProcess:
    """Represents an orphaned Claude Code process."""
    pid: int
    user: str
    cpu_percent: float
    mem_percent: float
    rss_kb: int
    command: str
    working_dir: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for logging (no PII/secrets)."""
        return {
            "pid": self.pid,
            "user": self.user,
            "cpu_percent": self.cpu_percent,
            "mem_percent": self.mem_percent,
            "rss_kb": self.rss_kb,
            "rss_mb": round(self.rss_kb / 1024, 2),
            "working_dir": self.working_dir,
            # Truncate command to avoid logging full paths with potential secrets
            "command_preview": self.command[:100] + "..." if len(self.command) > 100 else self.command,
        }


@dataclass
class CleanupResult:
    """Result of a cleanup operation."""
    trace_id: str
    session_id: str | None
    trigger: str  # "startup" | "session_terminated" | "manual"
    orphans_found: int
    orphans_killed: int
    orphans_failed: int
    memory_freed_kb: int
    duration_ms: int
    killed_processes: list[OrphanedProcess] = field(default_factory=list)
    failed_pids: list[int] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            "orphans_found": self.orphans_found,
            "orphans_killed": self.orphans_killed,
            "orphans_failed": self.orphans_failed,
            "memory_freed_kb": self.memory_freed_kb,
            "memory_freed_mb": round(self.memory_freed_kb / 1024, 2),
            "duration_ms": self.duration_ms,
        }


# =============================================================================
# Process Detection
# =============================================================================


def is_claude_code_cli(command: str) -> bool:
    """
    Check if command is a Claude Code CLI process.

    Matches:
    - "claude ..." (CLI with arguments)
    - "claude" (bare CLI)

    Excludes:
    - Claude.app (Claude Desktop)
    - .claude/shell-snapshots (temporary shell files)
    - Python/Node interpreters
    """
    # Exclude Claude Desktop
    if "Claude.app" in command:
        return False

    # Exclude shell snapshots
    if ".claude/shell-snapshots" in command:
        return False

    # Exclude Python/Node interpreters
    if command.startswith(("/usr/bin/python", "/usr/local/bin/python", "python", "node")):
        return False
    if "/.venv/" in command or "/bin/python" in command:
        return False

    # Match actual claude CLI command
    cmd_parts = command.split()
    if not cmd_parts:
        return False

    cmd_name = cmd_parts[0].split("/")[-1]  # Get basename
    return cmd_name == "claude"


def extract_working_dir(command: str) -> str | None:
    """Extract working directory from Claude command if present."""
    # Look for --add-dir argument
    parts = command.split()
    for i, part in enumerate(parts):
        if part == "--add-dir" and i + 1 < len(parts):
            # Return the directory without /tmp suffix
            dir_path = parts[i + 1]
            if dir_path.endswith("/tmp"):
                dir_path = dir_path[:-4]
            return dir_path
    return None


def get_orphaned_claude_processes(trace_id: str) -> list[OrphanedProcess]:
    """
    Find Claude Code CLI processes with no controlling terminal (orphaned).

    Returns:
        List of OrphanedProcess objects with full metadata
    """
    start_time = time.perf_counter()

    try:
        # ps aux format: USER PID %CPU %MEM VSZ RSS TTY STAT START TIME COMMAND
        result = subprocess.run(
            ["ps", "aux"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True
        )

        orphaned = []
        lines_checked = 0
        claude_processes_total = 0

        for line in result.stdout.strip().split("\n")[1:]:  # Skip header
            lines_checked += 1
            parts = line.split(None, 10)  # Split into max 11 parts
            if len(parts) < 11:
                continue

            user = parts[0]
            pid_str = parts[1]
            cpu = parts[2]
            mem = parts[3]
            rss = parts[5]
            tty = parts[6]
            command = parts[10]

            # Count all claude processes for metrics
            if is_claude_code_cli(command):
                claude_processes_total += 1

            # Check if it's an orphaned Claude Code CLI process
            if tty == "??" and is_claude_code_cli(command):
                try:
                    orphan = OrphanedProcess(
                        pid=int(pid_str),
                        user=user,
                        cpu_percent=float(cpu),
                        mem_percent=float(mem),
                        rss_kb=int(rss),
                        command=command,
                        working_dir=extract_working_dir(command),
                    )
                    orphaned.append(orphan)
                except (ValueError, IndexError) as e:
                    logger.warning(
                        "Failed to parse process info",
                        operation="get_orphaned_claude_processes",
                        status="parse_error",
                        trace_id=trace_id,
                        error=str(e),
                        line_preview=line[:100],
                    )
                    continue

        duration_ms = int((time.perf_counter() - start_time) * 1000)

        logger.debug(
            "Process scan complete",
            operation="get_orphaned_claude_processes",
            status="success",
            trace_id=trace_id,
            metrics={
                "lines_checked": lines_checked,
                "claude_processes_total": claude_processes_total,
                "orphans_found": len(orphaned),
                "duration_ms": duration_ms,
            },
        )

        return orphaned

    except subprocess.TimeoutExpired:
        logger.error(
            "Process scan timed out",
            operation="get_orphaned_claude_processes",
            status="timeout",
            trace_id=trace_id,
        )
        return []
    except subprocess.CalledProcessError as e:
        logger.error(
            "Process scan failed",
            operation="get_orphaned_claude_processes",
            status="failed",
            trace_id=trace_id,
            error=str(e),
            stderr=e.stderr[:500] if e.stderr else None,
        )
        return []
    except OSError as e:
        # OSError covers file not found, permission denied, etc.
        logger.error(
            "OS error during process scan",
            operation="get_orphaned_claude_processes",
            status="os_error",
            trace_id=trace_id,
            error=str(e),
            errno=e.errno,
        )
        return []


# =============================================================================
# Process Cleanup
# =============================================================================


def kill_process(pid: int, trace_id: str) -> bool:
    """
    Kill a single process by PID.

    Returns:
        True if killed successfully, False otherwise
    """
    try:
        result = subprocess.run(
            ["kill", str(pid)],
            capture_output=True,
            timeout=5,
            check=False  # Don't raise - process may have already exited
        )

        if result.returncode == 0:
            logger.debug(
                "Process killed",
                operation="kill_process",
                status="success",
                trace_id=trace_id,
                pid=pid,
            )
            return True
        else:
            # Check if process already exited
            check = subprocess.run(
                ["ps", "-p", str(pid)],
                capture_output=True,
                timeout=2,
                check=False
            )
            if check.returncode != 0:
                # Process doesn't exist - count as success
                logger.debug(
                    "Process already exited",
                    operation="kill_process",
                    status="already_exited",
                    trace_id=trace_id,
                    pid=pid,
                )
                return True
            else:
                logger.warning(
                    "Failed to kill process",
                    operation="kill_process",
                    status="failed",
                    trace_id=trace_id,
                    pid=pid,
                    stderr=result.stderr.decode() if result.stderr else None,
                )
                return False

    except subprocess.TimeoutExpired:
        logger.warning(
            "Timeout killing process",
            operation="kill_process",
            status="timeout",
            trace_id=trace_id,
            pid=pid,
        )
        return False
    except OSError as e:
        # OSError covers command not found, permission denied, etc.
        logger.error(
            "OS error killing process",
            operation="kill_process",
            status="os_error",
            trace_id=trace_id,
            pid=pid,
            error=str(e),
            errno=e.errno,
        )
        return False


def cleanup_orphaned_processes(
    trigger: str,
    session_id: str | None = None,
) -> CleanupResult:
    """
    Find and kill all orphaned Claude Code processes.

    Args:
        trigger: What triggered this cleanup ("startup", "session_terminated", "manual")
        session_id: iTerm2 session ID if triggered by session termination

    Returns:
        CleanupResult with full audit trail
    """
    trace_id = str(uuid4())
    trace_id_var.set(trace_id)
    start_time = time.perf_counter()

    logger.info(
        "Cleanup started",
        operation="cleanup_orphaned_processes",
        status="started",
        trace_id=trace_id,
        session_id=session_id,
        trigger=trigger,
    )

    # Find orphaned processes
    orphans = get_orphaned_claude_processes(trace_id)

    if not orphans:
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        logger.info(
            "No orphans found",
            operation="cleanup_orphaned_processes",
            status="complete",
            trace_id=trace_id,
            session_id=session_id,
            trigger=trigger,
            metrics={
                "orphans_found": 0,
                "orphans_killed": 0,
                "duration_ms": duration_ms,
            },
        )
        return CleanupResult(
            trace_id=trace_id,
            session_id=session_id,
            trigger=trigger,
            orphans_found=0,
            orphans_killed=0,
            orphans_failed=0,
            memory_freed_kb=0,
            duration_ms=duration_ms,
        )

    # Log details of each orphan found
    for orphan in orphans:
        logger.debug(
            "Orphan found",
            operation="cleanup_orphaned_processes",
            status="orphan_detected",
            trace_id=trace_id,
            **orphan.to_dict(),
        )

    # Kill each orphan
    killed = []
    failed = []
    memory_freed_kb = 0

    for orphan in orphans:
        if kill_process(orphan.pid, trace_id):
            killed.append(orphan)
            memory_freed_kb += orphan.rss_kb
        else:
            failed.append(orphan.pid)

    duration_ms = int((time.perf_counter() - start_time) * 1000)

    result = CleanupResult(
        trace_id=trace_id,
        session_id=session_id,
        trigger=trigger,
        orphans_found=len(orphans),
        orphans_killed=len(killed),
        orphans_failed=len(failed),
        memory_freed_kb=memory_freed_kb,
        duration_ms=duration_ms,
        killed_processes=killed,
        failed_pids=failed,
    )

    # Log summary with full metrics
    log_level = "info" if not failed else "warning"
    getattr(logger, log_level)(
        f"Cleanup complete: killed {len(killed)}/{len(orphans)} orphans, freed {round(memory_freed_kb/1024, 2)} MB",
        operation="cleanup_orphaned_processes",
        status="complete" if not failed else "partial",
        trace_id=trace_id,
        session_id=session_id,
        trigger=trigger,
        metrics=result.to_dict(),
        killed_pids=[p.pid for p in killed],
        killed_working_dirs=[p.working_dir for p in killed if p.working_dir],
        failed_pids=failed if failed else None,
    )

    return result


# =============================================================================
# Main Daemon
# =============================================================================


async def main(connection: iterm2.Connection) -> None:
    """
    Main daemon loop - monitors session terminations and cleans up orphans.
    """
    daemon_trace_id = str(uuid4())

    logger.info(
        "Daemon starting",
        operation="main",
        status="starting",
        trace_id=daemon_trace_id,
        metrics={
            "pid": os.getpid(),
        },
    )

    # Initial cleanup on startup
    startup_result = cleanup_orphaned_processes(trigger="startup")

    logger.info(
        "Daemon ready - monitoring session terminations",
        operation="main",
        status="ready",
        trace_id=daemon_trace_id,
        startup_cleanup=startup_result.to_dict(),
    )

    # Track session stats for periodic reporting
    sessions_monitored = 0
    total_orphans_killed = startup_result.orphans_killed
    total_memory_freed_kb = startup_result.memory_freed_kb

    # Monitor for session terminations
    try:
        async with iterm2.SessionTerminationMonitor(connection) as monitor:
            while True:
                # Wait for any session to terminate
                session_id = await monitor.async_get()
                sessions_monitored += 1

                logger.info(
                    "Session terminated - triggering cleanup",
                    operation="main",
                    status="session_terminated",
                    trace_id=daemon_trace_id,
                    session_id=session_id,
                    metrics={
                        "sessions_monitored": sessions_monitored,
                        "total_orphans_killed": total_orphans_killed,
                    },
                )

                # Small delay to let process cleanup happen naturally
                await asyncio.sleep(0.5)

                # Cleanup orphaned processes
                result = cleanup_orphaned_processes(
                    trigger="session_terminated",
                    session_id=session_id,
                )

                total_orphans_killed += result.orphans_killed
                total_memory_freed_kb += result.memory_freed_kb

                # Periodic summary every 10 sessions
                if sessions_monitored % 10 == 0:
                    logger.info(
                        "Periodic summary",
                        operation="main",
                        status="periodic_summary",
                        trace_id=daemon_trace_id,
                        metrics={
                            "sessions_monitored": sessions_monitored,
                            "total_orphans_killed": total_orphans_killed,
                            "total_memory_freed_mb": round(total_memory_freed_kb / 1024, 2),
                        },
                    )

    except asyncio.CancelledError:
        logger.info(
            "Daemon cancelled",
            operation="main",
            status="cancelled",
            trace_id=daemon_trace_id,
            metrics={
                "sessions_monitored": sessions_monitored,
                "total_orphans_killed": total_orphans_killed,
                "total_memory_freed_mb": round(total_memory_freed_kb / 1024, 2),
            },
        )
        raise
    except Exception as e:
        logger.exception(
            "Daemon error - will restart",
            operation="main",
            status="error",
            trace_id=daemon_trace_id,
        )
        raise


# =============================================================================
# Entry Point
# =============================================================================

# Initialize logger before anything else
setup_logger()

# Run as a long-running daemon
iterm2.run_forever(main)
