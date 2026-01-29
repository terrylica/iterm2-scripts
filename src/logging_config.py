# ruff: noqa: F821
# ADR: docs/adr/2026-01-26-modular-source-concatenation.md
# This module is concatenated with _header.py - imports come from there

# =============================================================================
# Structured Logging Setup (JSONL format)
# =============================================================================

# Correlation ID for async operations
trace_id_var: ContextVar[str] = ContextVar('trace_id', default=None)

T = TypeVar('T')


def json_sink(message):
    """JSONL sink for Claude Code analysis - writes to stderr."""
    record = message.record
    log_entry = {
        "timestamp": record["time"].strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        "level": record["level"].name.lower(),
        "component": record["function"],
        "operation": record["extra"].get("operation", "unknown"),
        "operation_status": record["extra"].get("status", None),
        "trace_id": record["extra"].get("trace_id") or trace_id_var.get(),
        "message": record["message"],
        "context": {k: v for k, v in record["extra"].items()
                   if k not in ("operation", "status", "trace_id", "metrics")},
        "metrics": record["extra"].get("metrics", {}),
        "error": None
    }

    if record["exception"]:
        exc_type, exc_value, exc_tb = record["exception"]
        tb_lines = []
        if exc_tb:
            tb_lines = traceback.format_tb(exc_tb)

        log_entry["error"] = {
            "type": exc_type.__name__ if exc_type else "Unknown",
            "message": str(exc_value) if exc_value else "Unknown error",
            "traceback_lines": tb_lines
        }

    sys.stderr.write(json.dumps(log_entry) + "\n")


def setup_logger():
    """Configure Loguru for machine-readable JSONL output."""
    logger.remove()

    # Console output (JSONL to stderr via custom sink)
    logger.add(
        json_sink,
        level="INFO"
    )

    # File output with rotation (using platformdirs for cross-platform support)
    # macOS: ~/Library/Logs/iterm2-layout/
    # Linux: ~/.local/state/iterm2-layout/log/
    log_dir = Path(platformdirs.user_log_dir(
        appname="iterm2-layout",
        ensure_exists=True
    ))

    logger.add(
        str(log_dir / "layout.jsonl"),
        format="{message}",
        serialize=True,
        rotation="10 MB",
        retention="7 days",
        compression="gz",
        level="DEBUG"
    )

    return logger
