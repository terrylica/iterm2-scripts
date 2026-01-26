# ruff: noqa: F821
# ADR: docs/adr/2026-01-26-modular-source-concatenation.md
# This module is concatenated with _header.py - imports come from there

# =============================================================================
# Error Handling Types (Result + ErrorReport)
# =============================================================================


class ErrorType(Enum):
    FILE_NOT_FOUND = "file_not_found"
    PARSE_ERROR = "parse_error"
    VALIDATION_ERROR = "validation_error"
    ASYNC_ERROR = "async_error"
    PERMISSION_ERROR = "permission_error"
    TIMEOUT_ERROR = "timeout_error"


@dataclass
class Error:
    error_type: ErrorType
    message: str
    context: dict = field(default_factory=dict)
    original_exception: Exception = None


@dataclass
class Result(Generic[T]):
    success: bool
    value: T = None
    error: Error = None

    @staticmethod
    def ok(value: T) -> 'Result[T]':
        return Result(success=True, value=value)

    @staticmethod
    def err(error: Error) -> 'Result[T]':
        return Result(success=False, error=error)

    def is_ok(self) -> bool:
        return self.success

    def is_err(self) -> bool:
        return not self.success


@dataclass
class ErrorReport:
    errors: list[Error] = field(default_factory=list)
    warnings: list[Error] = field(default_factory=list)

    def add_error(self, error: Error):
        self.errors.append(error)
        logger.error(
            error.message,
            operation="error_report",
            status="error",
            error_type=error.error_type.value,
            **error.context
        )

    def add_warning(self, error: Error):
        self.warnings.append(error)
        logger.warning(
            error.message,
            operation="error_report",
            status="warning",
            error_type=error.error_type.value,
            **error.context
        )

    def collect_result(self, result: Result, context: str = "") -> bool:
        """Collect error from Result into report if failed."""
        if result.is_err():
            self.add_error(result.error)
            return False
        return True

    def has_errors(self) -> bool:
        return len(self.errors) > 0

    def log_summary(self, op_trace_id: str):
        """Log final summary for Claude Code analysis."""
        logger.info(
            "Operation complete",
            operation="error_report",
            status="complete",
            trace_id=op_trace_id,
            metrics={
                "total_errors": len(self.errors),
                "total_warnings": len(self.warnings)
            }
        )
