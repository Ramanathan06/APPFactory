"""
Alphhaspace Exception Hierarchy
================================

Centralized exception system providing:
- Typed exception hierarchy for all error scenarios
- Rich context preservation for debugging
- Serialization support for IPC/frontend display
- Automatic categorization and recovery hints
- Circuit breaker integration for resilient external calls

Usage:
    from core.exceptions import (
        AgentError,
        SessionError,
        SpecError,
        MemoryError,
        capture_error,
        Result,
    )

    try:
        await run_agent_session(...)
    except AgentError as e:
        structured = e.to_structured_error()
        # Send to frontend or log
"""

from __future__ import annotations

import asyncio
import functools
import logging
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


# =============================================================================
# Error Categories and Severity
# =============================================================================


class ErrorCategory(str, Enum):
    """Categories of errors for classification and UI display."""

    # Agent & Session Errors
    AGENT_SESSION = "agent_session"
    AGENT_TIMEOUT = "agent_timeout"
    AGENT_STUCK = "agent_stuck"
    AGENT_RECOVERY = "agent_recovery"

    # Spec Errors
    SPEC_CREATION = "spec_creation"
    SPEC_VALIDATION = "spec_validation"
    SPEC_NOT_FOUND = "spec_not_found"
    SPEC_INVALID = "spec_invalid"

    # Memory Errors
    MEMORY_CONNECTION = "memory_connection"
    MEMORY_QUERY = "memory_query"
    MEMORY_WRITE = "memory_write"
    MEMORY_PROVIDER = "memory_provider"

    # Authentication Errors
    AUTHENTICATION = "authentication"
    TOKEN_EXPIRED = "token_expired"
    TOKEN_MISSING = "token_missing"

    # External Service Errors
    RATE_LIMITED = "rate_limited"
    SERVICE_UNAVAILABLE = "service_unavailable"
    NETWORK = "network"
    TIMEOUT = "timeout"

    # Security Errors
    SECURITY_BLOCKED = "security_blocked"
    PERMISSION_DENIED = "permission_denied"

    # Build/Workspace Errors
    BUILD_FAILED = "build_failed"
    WORKSPACE_ERROR = "workspace_error"
    GIT_ERROR = "git_error"
    MERGE_CONFLICT = "merge_conflict"

    # QA Errors
    QA_FAILED = "qa_failed"
    QA_TIMEOUT = "qa_timeout"

    # Configuration Errors
    CONFIGURATION = "configuration"
    VALIDATION = "validation"

    # Internal Errors
    INTERNAL = "internal"
    NOT_IMPLEMENTED = "not_implemented"


class ErrorSeverity(str, Enum):
    """Severity levels for error classification."""

    DEBUG = "debug"  # Developer-only info
    INFO = "info"  # Informational, not critical
    WARNING = "warning"  # Something went wrong but recoverable
    ERROR = "error"  # Operation failed
    CRITICAL = "critical"  # System-level failure, needs attention


class RecoveryAction(str, Enum):
    """Suggested recovery actions for errors."""

    RETRY = "retry"  # Simple retry may work
    RETRY_WITH_BACKOFF = "retry_with_backoff"  # Exponential backoff needed
    REFRESH_TOKEN = "refresh_token"  # Re-authenticate
    MANUAL_INTERVENTION = "manual_intervention"  # Human needs to look at this
    SKIP = "skip"  # Skip this item and continue
    ABORT = "abort"  # Stop the operation entirely
    RECONFIGURE = "reconfigure"  # Fix configuration
    WAIT = "wait"  # Wait and retry later (rate limiting)


# =============================================================================
# Structured Error Dataclass
# =============================================================================


@dataclass
class StructuredError:
    """
    Structured error object for IPC, logging, and UI display.

    Provides:
    - Serialization for sending errors to frontend
    - Stack trace preservation
    - Actionable recovery hints
    - Context for debugging
    """

    # Core error info
    message: str
    category: ErrorCategory
    severity: ErrorSeverity = ErrorSeverity.ERROR

    # Identification
    code: str | None = None  # Machine-readable error code (e.g., "AGENT_STUCK_001")
    correlation_id: str | None = None  # For tracing across systems
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    # Context
    details: dict[str, Any] = field(default_factory=dict)
    stack_trace: str | None = None

    # Agent/Session context
    agent_type: str | None = None
    session_num: int | None = None
    subtask_id: str | None = None
    phase: str | None = None

    # Spec/Project context
    spec_id: str | None = None
    spec_dir: str | None = None
    project_dir: str | None = None

    # Recovery information
    retryable: bool = False
    retry_count: int = 0
    max_retries: int = 3
    retry_after_seconds: int | None = None
    recovery_action: RecoveryAction | None = None
    action_hint: str | None = None
    help_url: str | None = None

    # Chain of errors
    cause: StructuredError | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "message": self.message,
            "category": self.category.value,
            "severity": self.severity.value,
            "code": self.code,
            "correlation_id": self.correlation_id,
            "timestamp": self.timestamp,
            "details": self.details,
            "stack_trace": self.stack_trace,
            "agent_type": self.agent_type,
            "session_num": self.session_num,
            "subtask_id": self.subtask_id,
            "phase": self.phase,
            "spec_id": self.spec_id,
            "spec_dir": self.spec_dir,
            "project_dir": self.project_dir,
            "retryable": self.retryable,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "retry_after_seconds": self.retry_after_seconds,
            "recovery_action": self.recovery_action.value if self.recovery_action else None,
            "action_hint": self.action_hint,
            "help_url": self.help_url,
            "cause": self.cause.to_dict() if self.cause else None,
        }

    @classmethod
    def from_exception(
        cls,
        exc: Exception,
        category: ErrorCategory = ErrorCategory.INTERNAL,
        severity: ErrorSeverity = ErrorSeverity.ERROR,
        **kwargs,
    ) -> StructuredError:
        """Create a StructuredError from any exception."""
        return cls(
            message=str(exc),
            category=category,
            severity=severity,
            code=exc.__class__.__name__,
            stack_trace=traceback.format_exc(),
            **kwargs,
        )

    def with_context(
        self,
        agent_type: str | None = None,
        session_num: int | None = None,
        subtask_id: str | None = None,
        phase: str | None = None,
        spec_id: str | None = None,
        spec_dir: Path | None = None,
        project_dir: Path | None = None,
    ) -> StructuredError:
        """Add context to the error (returns self for chaining)."""
        if agent_type:
            self.agent_type = agent_type
        if session_num is not None:
            self.session_num = session_num
        if subtask_id:
            self.subtask_id = subtask_id
        if phase:
            self.phase = phase
        if spec_id:
            self.spec_id = spec_id
        if spec_dir:
            self.spec_dir = str(spec_dir)
        if project_dir:
            self.project_dir = str(project_dir)
        return self

    def can_retry(self) -> bool:
        """Check if this error can be retried."""
        return self.retryable and self.retry_count < self.max_retries


# =============================================================================
# Base Exception Classes
# =============================================================================


class AlphhaspaceError(Exception):
    """
    Base exception for all Alphhaspace errors.

    Provides:
    - Automatic category and severity assignment
    - Context preservation
    - Conversion to StructuredError for IPC
    """

    category: ErrorCategory = ErrorCategory.INTERNAL
    severity: ErrorSeverity = ErrorSeverity.ERROR
    retryable: bool = False
    recovery_action: RecoveryAction | None = None
    action_hint: str | None = None

    def __init__(
        self,
        message: str,
        details: dict[str, Any] | None = None,
        cause: Exception | None = None,
        **kwargs,
    ):
        super().__init__(message)
        self.message = message
        self.details = details or {}
        self.cause = cause
        self.context = kwargs

    def to_structured_error(self) -> StructuredError:
        """Convert to StructuredError for IPC/logging."""
        cause_error = None
        if self.cause:
            if isinstance(self.cause, AlphhaspaceError):
                cause_error = self.cause.to_structured_error()
            else:
                cause_error = StructuredError.from_exception(self.cause)

        return StructuredError(
            message=self.message,
            category=self.category,
            severity=self.severity,
            code=self.__class__.__name__,
            details=self.details,
            stack_trace=traceback.format_exc(),
            retryable=self.retryable,
            recovery_action=self.recovery_action,
            action_hint=self.action_hint,
            cause=cause_error,
            **self.context,
        )


# =============================================================================
# Agent & Session Errors
# =============================================================================


class AgentError(AlphhaspaceError):
    """Base exception for agent-related errors."""

    category = ErrorCategory.AGENT_SESSION

    def __init__(
        self,
        message: str,
        agent_type: str | None = None,
        session_num: int | None = None,
        subtask_id: str | None = None,
        **kwargs,
    ):
        super().__init__(message, **kwargs)
        self.context["agent_type"] = agent_type
        self.context["session_num"] = session_num
        self.context["subtask_id"] = subtask_id


class SessionTimeoutError(AgentError):
    """Agent session timed out."""

    category = ErrorCategory.AGENT_TIMEOUT
    retryable = True
    recovery_action = RecoveryAction.RETRY
    action_hint = "Session timed out. Will retry with fresh context."


class SessionStuckError(AgentError):
    """Agent is stuck and not making progress."""

    category = ErrorCategory.AGENT_STUCK
    retryable = True
    max_retries = 3
    recovery_action = RecoveryAction.RETRY_WITH_BACKOFF
    action_hint = "Agent stuck. Trying alternative approach."


class SessionRecoveryError(AgentError):
    """Failed to recover agent session."""

    category = ErrorCategory.AGENT_RECOVERY
    recovery_action = RecoveryAction.MANUAL_INTERVENTION
    action_hint = "Recovery failed. Manual intervention may be needed."


class MaxRetriesExceededError(AgentError):
    """Maximum retry attempts exceeded for a subtask."""

    category = ErrorCategory.AGENT_STUCK
    recovery_action = RecoveryAction.SKIP
    action_hint = "Max retries exceeded. Consider skipping this subtask."


# =============================================================================
# Spec Errors
# =============================================================================


class SpecError(AlphhaspaceError):
    """Base exception for spec-related errors."""

    category = ErrorCategory.SPEC_CREATION

    def __init__(self, message: str, spec_id: str | None = None, **kwargs):
        super().__init__(message, **kwargs)
        self.context["spec_id"] = spec_id


class SpecNotFoundError(SpecError):
    """Spec not found."""

    category = ErrorCategory.SPEC_NOT_FOUND
    action_hint = "Spec not found. Run spec creation first."


class SpecValidationError(SpecError):
    """Spec validation failed."""

    category = ErrorCategory.SPEC_VALIDATION
    action_hint = "Spec validation failed. Check spec.md for required sections."


class SpecInvalidError(SpecError):
    """Spec is malformed or corrupted."""

    category = ErrorCategory.SPEC_INVALID
    action_hint = "Spec file is invalid. Regenerate the spec."


class ImplementationPlanError(SpecError):
    """Implementation plan error."""

    action_hint = "Implementation plan is invalid or missing."


# =============================================================================
# Memory Errors
# =============================================================================


class MemoryError(AlphhaspaceError):
    """Base exception for memory system errors."""

    category = ErrorCategory.MEMORY_CONNECTION


class MemoryConnectionError(MemoryError):
    """Failed to connect to memory system."""

    category = ErrorCategory.MEMORY_CONNECTION
    retryable = True
    recovery_action = RecoveryAction.RETRY
    action_hint = "Memory system unavailable. Falling back to file-based storage."


class MemoryQueryError(MemoryError):
    """Memory query failed."""

    category = ErrorCategory.MEMORY_QUERY
    retryable = True
    action_hint = "Memory query failed. Results may be incomplete."


class MemoryWriteError(MemoryError):
    """Failed to write to memory."""

    category = ErrorCategory.MEMORY_WRITE
    retryable = True
    action_hint = "Memory write failed. Session insights may not persist."


class MemoryProviderError(MemoryError):
    """Memory provider configuration error."""

    category = ErrorCategory.MEMORY_PROVIDER
    recovery_action = RecoveryAction.RECONFIGURE
    action_hint = "Check GRAPHITI_* environment variables."


# =============================================================================
# Authentication Errors
# =============================================================================


class AuthenticationError(AlphhaspaceError):
    """Base exception for authentication errors."""

    category = ErrorCategory.AUTHENTICATION
    recovery_action = RecoveryAction.REFRESH_TOKEN


class TokenMissingError(AuthenticationError):
    """OAuth token not found."""

    category = ErrorCategory.TOKEN_MISSING
    action_hint = "Run 'claude setup-token' to configure authentication."


class TokenExpiredError(AuthenticationError):
    """OAuth token has expired."""

    category = ErrorCategory.TOKEN_EXPIRED
    action_hint = "Token expired. Re-authenticate with 'claude setup-token'."


# =============================================================================
# External Service Errors
# =============================================================================


class ExternalServiceError(AlphhaspaceError):
    """Base exception for external service errors."""

    category = ErrorCategory.SERVICE_UNAVAILABLE
    retryable = True


class RateLimitError(ExternalServiceError):
    """Rate limit exceeded."""

    category = ErrorCategory.RATE_LIMITED
    severity = ErrorSeverity.WARNING
    retryable = True
    recovery_action = RecoveryAction.WAIT

    def __init__(self, message: str, retry_after_seconds: int = 60, **kwargs):
        super().__init__(message, **kwargs)
        self.retry_after_seconds = retry_after_seconds
        self.action_hint = f"Rate limited. Retry in {retry_after_seconds}s."

    def to_structured_error(self) -> StructuredError:
        error = super().to_structured_error()
        error.retry_after_seconds = self.retry_after_seconds
        return error


class NetworkError(ExternalServiceError):
    """Network connection error."""

    category = ErrorCategory.NETWORK
    recovery_action = RecoveryAction.RETRY
    action_hint = "Network error. Check connection and retry."


class TimeoutError(ExternalServiceError):
    """Operation timed out."""

    category = ErrorCategory.TIMEOUT
    recovery_action = RecoveryAction.RETRY
    action_hint = "Operation timed out. Will retry."


class ServiceUnavailableError(ExternalServiceError):
    """External service unavailable."""

    recovery_action = RecoveryAction.RETRY_WITH_BACKOFF
    action_hint = "Service temporarily unavailable. Retrying..."


# =============================================================================
# Security Errors
# =============================================================================


class SecurityError(AlphhaspaceError):
    """Base exception for security-related errors."""

    category = ErrorCategory.SECURITY_BLOCKED
    severity = ErrorSeverity.WARNING


class CommandBlockedError(SecurityError):
    """Command blocked by security policy."""

    action_hint = "Command blocked by security policy. Operation aborted."


class PermissionDeniedError(SecurityError):
    """Permission denied for operation."""

    category = ErrorCategory.PERMISSION_DENIED
    action_hint = "Permission denied. Check file/directory permissions."


# =============================================================================
# Build/Workspace Errors
# =============================================================================


class WorkspaceError(AlphhaspaceError):
    """Base exception for workspace errors."""

    category = ErrorCategory.WORKSPACE_ERROR


class GitError(WorkspaceError):
    """Git operation failed."""

    category = ErrorCategory.GIT_ERROR
    action_hint = "Git operation failed. Check repository state."


class MergeConflictError(WorkspaceError):
    """Merge conflict detected."""

    category = ErrorCategory.MERGE_CONFLICT
    recovery_action = RecoveryAction.MANUAL_INTERVENTION
    action_hint = "Merge conflict detected. Resolve manually."


class WorktreeError(WorkspaceError):
    """Worktree operation failed."""

    action_hint = "Worktree operation failed. Check worktree state."


# =============================================================================
# QA Errors
# =============================================================================


class QAError(AlphhaspaceError):
    """Base exception for QA errors."""

    category = ErrorCategory.QA_FAILED


class QAValidationError(QAError):
    """QA validation failed."""

    retryable = True
    recovery_action = RecoveryAction.RETRY
    action_hint = "QA validation failed. Running QA fixer."


class QATimeoutError(QAError):
    """QA loop timed out."""

    category = ErrorCategory.QA_TIMEOUT
    action_hint = "QA loop timed out. Check for infinite loop."


# =============================================================================
# Configuration Errors
# =============================================================================


class ConfigurationError(AlphhaspaceError):
    """Configuration error."""

    category = ErrorCategory.CONFIGURATION
    recovery_action = RecoveryAction.RECONFIGURE
    action_hint = "Check configuration settings."


class ValidationError(AlphhaspaceError):
    """Input validation error."""

    category = ErrorCategory.VALIDATION


# =============================================================================
# Error Capture and Utility Functions
# =============================================================================


def capture_error(
    exc: Exception,
    correlation_id: str | None = None,
    agent_type: str | None = None,
    session_num: int | None = None,
    subtask_id: str | None = None,
    phase: str | None = None,
    spec_id: str | None = None,
    spec_dir: Path | None = None,
    project_dir: Path | None = None,
) -> StructuredError:
    """
    Capture any exception as a StructuredError.

    Handles both AlphhaspaceError subclasses and generic exceptions.
    """
    if isinstance(exc, AlphhaspaceError):
        error = exc.to_structured_error()
    else:
        # Map known exception types to categories
        category = ErrorCategory.INTERNAL
        retryable = False
        recovery_action = None

        if isinstance(exc, asyncio.TimeoutError):
            category = ErrorCategory.TIMEOUT
            retryable = True
            recovery_action = RecoveryAction.RETRY
        elif isinstance(exc, ConnectionError):
            category = ErrorCategory.NETWORK
            retryable = True
            recovery_action = RecoveryAction.RETRY
        elif isinstance(exc, PermissionError):
            category = ErrorCategory.PERMISSION_DENIED
        elif isinstance(exc, FileNotFoundError):
            category = ErrorCategory.SPEC_NOT_FOUND
        elif isinstance(exc, ValueError):
            category = ErrorCategory.VALIDATION

        error = StructuredError.from_exception(
            exc,
            category=category,
            retryable=retryable,
            recovery_action=recovery_action,
        )

    # Add context
    return error.with_context(
        agent_type=agent_type,
        session_num=session_num,
        subtask_id=subtask_id,
        phase=phase,
        spec_id=spec_id,
        spec_dir=spec_dir,
        project_dir=project_dir,
    )


# =============================================================================
# Result Type for Error-aware Operations
# =============================================================================


@dataclass
class Result:
    """
    Result type for operations that may succeed or fail.

    Usage:
        result = Result.success(data={"insights": [...]})
        result = Result.failure(error=structured_error)

        if result.ok:
            process(result.data)
        else:
            handle_error(result.error)
    """

    ok: bool
    data: dict[str, Any] | None = None
    error: StructuredError | None = None

    @classmethod
    def success(cls, data: dict[str, Any] | None = None) -> Result:
        """Create a success result."""
        return cls(ok=True, data=data)

    @classmethod
    def failure(cls, error: StructuredError) -> Result:
        """Create a failure result."""
        return cls(ok=False, error=error)

    @classmethod
    def from_exception(
        cls,
        exc: Exception,
        **context,
    ) -> Result:
        """Create a failure result from an exception."""
        return cls.failure(capture_error(exc, **context))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "ok": self.ok,
            "data": self.data,
            "error": self.error.to_dict() if self.error else None,
        }


# =============================================================================
# Circuit Breaker for Resilient External Calls
# =============================================================================


class CircuitState(str, Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject calls
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreaker:
    """
    Circuit breaker for resilient external service calls.

    Prevents cascading failures by short-circuiting calls to failing services.

    Usage:
        graphiti_circuit = CircuitBreaker(
            name="graphiti",
            failure_threshold=5,
            recovery_timeout=60,
        )

        async def query_memory():
            if not graphiti_circuit.can_execute():
                return []  # Fallback

            try:
                result = await graphiti.search(...)
                graphiti_circuit.record_success()
                return result
            except Exception as e:
                graphiti_circuit.record_failure(e)
                raise
    """

    name: str
    failure_threshold: int = 5
    recovery_timeout: int = 60  # seconds
    half_open_max_calls: int = 3

    # Internal state
    state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    failure_count: int = field(default=0, init=False)
    success_count: int = field(default=0, init=False)
    last_failure_time: float | None = field(default=None, init=False)
    half_open_calls: int = field(default=0, init=False)

    def can_execute(self) -> bool:
        """Check if a call should be allowed."""
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            # Check if recovery timeout has passed
            if self.last_failure_time:
                elapsed = time.time() - self.last_failure_time
                if elapsed >= self.recovery_timeout:
                    self._transition_to_half_open()
                    return True
            return False

        if self.state == CircuitState.HALF_OPEN:
            if self.half_open_calls < self.half_open_max_calls:
                self.half_open_calls += 1
                return True
            return False

        return False

    def record_success(self) -> None:
        """Record a successful call."""
        self.success_count += 1

        if self.state == CircuitState.HALF_OPEN:
            # If enough successes in half-open, close circuit
            if self.success_count >= self.half_open_max_calls:
                self._transition_to_closed()
        elif self.state == CircuitState.CLOSED:
            # Reset failure count on success
            self.failure_count = 0

    def record_failure(self, exc: Exception | None = None) -> None:
        """Record a failed call."""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.state == CircuitState.HALF_OPEN:
            # Any failure in half-open opens circuit again
            self._transition_to_open()
        elif self.state == CircuitState.CLOSED:
            if self.failure_count >= self.failure_threshold:
                self._transition_to_open()
                logger.warning(
                    f"Circuit breaker '{self.name}' opened after {self.failure_count} failures"
                )

    def _transition_to_open(self) -> None:
        """Transition to open state."""
        self.state = CircuitState.OPEN
        self.half_open_calls = 0
        self.success_count = 0

    def _transition_to_half_open(self) -> None:
        """Transition to half-open state."""
        self.state = CircuitState.HALF_OPEN
        self.half_open_calls = 0
        self.success_count = 0
        logger.info(f"Circuit breaker '{self.name}' half-open, testing recovery...")

    def _transition_to_closed(self) -> None:
        """Transition to closed state."""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.half_open_calls = 0
        logger.info(f"Circuit breaker '{self.name}' closed, service recovered")

    def get_status(self) -> dict[str, Any]:
        """Get circuit breaker status."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout,
            "last_failure_time": self.last_failure_time,
        }


# =============================================================================
# Retry Decorator with Exponential Backoff
# =============================================================================


def with_retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    retryable_exceptions: tuple = (Exception,),
    on_retry: Callable[[Exception, int], None] | None = None,
):
    """
    Decorator for retrying async functions with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay between retries in seconds
        max_delay: Maximum delay between retries
        exponential_base: Base for exponential backoff
        retryable_exceptions: Tuple of exception types to retry
        on_retry: Optional callback called on each retry

    Usage:
        @with_retry(max_retries=3, base_delay=1.0)
        async def fetch_data():
            ...
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exception = e

                    if attempt == max_retries:
                        raise

                    # Calculate delay with exponential backoff
                    delay = min(
                        base_delay * (exponential_base**attempt),
                        max_delay,
                    )

                    if on_retry:
                        on_retry(e, attempt + 1)

                    logger.warning(
                        f"Retry {attempt + 1}/{max_retries} for {func.__name__} "
                        f"after {delay:.1f}s: {e}"
                    )
                    await asyncio.sleep(delay)

            # Should never reach here, but just in case
            if last_exception:
                raise last_exception

        return wrapper

    return decorator


# =============================================================================
# Global Circuit Breakers
# =============================================================================

# Pre-configured circuit breakers for common services
graphiti_circuit = CircuitBreaker(
    name="graphiti",
    failure_threshold=5,
    recovery_timeout=60,
)

linear_circuit = CircuitBreaker(
    name="linear",
    failure_threshold=3,
    recovery_timeout=120,
)

claude_api_circuit = CircuitBreaker(
    name="claude_api",
    failure_threshold=10,
    recovery_timeout=30,
)


# =============================================================================
# Export All Public APIs
# =============================================================================

__all__ = [
    # Categories and enums
    "ErrorCategory",
    "ErrorSeverity",
    "RecoveryAction",
    # Structured error
    "StructuredError",
    # Base exceptions
    "AlphhaspaceError",
    # Agent errors
    "AgentError",
    "SessionTimeoutError",
    "SessionStuckError",
    "SessionRecoveryError",
    "MaxRetriesExceededError",
    # Spec errors
    "SpecError",
    "SpecNotFoundError",
    "SpecValidationError",
    "SpecInvalidError",
    "ImplementationPlanError",
    # Memory errors
    "MemoryError",
    "MemoryConnectionError",
    "MemoryQueryError",
    "MemoryWriteError",
    "MemoryProviderError",
    # Auth errors
    "AuthenticationError",
    "TokenMissingError",
    "TokenExpiredError",
    # External service errors
    "ExternalServiceError",
    "RateLimitError",
    "NetworkError",
    "TimeoutError",
    "ServiceUnavailableError",
    # Security errors
    "SecurityError",
    "CommandBlockedError",
    "PermissionDeniedError",
    # Workspace errors
    "WorkspaceError",
    "GitError",
    "MergeConflictError",
    "WorktreeError",
    # QA errors
    "QAError",
    "QAValidationError",
    "QATimeoutError",
    # Config errors
    "ConfigurationError",
    "ValidationError",
    # Utilities
    "capture_error",
    "Result",
    # Circuit breaker
    "CircuitState",
    "CircuitBreaker",
    "with_retry",
    # Global circuit breakers
    "graphiti_circuit",
    "linear_circuit",
    "claude_api_circuit",
]
