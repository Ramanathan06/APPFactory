"""
Core Framework Module
=====================

Core components for the Alphhaspace autonomous coding framework.

Includes:
- Agent execution (run_autonomous_agent, run_followup_planner)
- Workspace management (WorkspaceManager, WorktreeManager)
- Progress tracking (ProgressTracker)
- Exception hierarchy (exceptions module)
- Session observability (observability module)
"""

# Note: We use lazy imports here because the full agent module has many dependencies
# that may not be needed for basic operations like workspace management.

__all__ = [
    # Agent execution
    "run_autonomous_agent",
    "run_followup_planner",
    # Workspace management
    "WorkspaceManager",
    "WorktreeManager",
    "ProgressTracker",
    # Exceptions
    "AlphhaspaceError",
    "AgentError",
    "SessionTimeoutError",
    "SessionStuckError",
    "SpecError",
    "MemoryError",
    "capture_error",
    "Result",
    "CircuitBreaker",
    "with_retry",
    # Observability
    "SessionMetrics",
    "MetricsCollector",
    "get_metrics_collector",
]


def __getattr__(name):
    """Lazy imports to avoid circular dependencies and heavy imports."""
    if name in ("run_autonomous_agent", "run_followup_planner"):
        from .agent import run_autonomous_agent, run_followup_planner

        return locals()[name]
    elif name == "WorkspaceManager":
        from .workspace import WorkspaceManager

        return WorkspaceManager
    elif name == "WorktreeManager":
        from .worktree import WorktreeManager

        return WorktreeManager
    elif name == "ProgressTracker":
        from .progress import ProgressTracker

        return ProgressTracker
    elif name in ("create_claude_client", "ClaudeClient"):
        from . import client as _client

        return getattr(_client, name)
    # Exception classes
    elif name in (
        "AlphhaspaceError",
        "AgentError",
        "SessionTimeoutError",
        "SessionStuckError",
        "SpecError",
        "MemoryError",
        "capture_error",
        "Result",
        "CircuitBreaker",
        "with_retry",
    ):
        from . import exceptions as _exceptions

        return getattr(_exceptions, name)
    # Observability
    elif name in (
        "SessionMetrics",
        "MetricsCollector",
        "get_metrics_collector",
    ):
        from . import observability as _observability

        return getattr(_observability, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
