"""
Alphhaspace Session Observability System
=========================================

Comprehensive observability for agent sessions providing:
- Structured metrics collection (tokens, duration, tool calls)
- Tool usage analytics
- Success/failure rate tracking
- Performance trend analysis
- Persistent metrics storage for analysis

Usage:
    from core.observability import (
        SessionMetrics,
        MetricsCollector,
        get_metrics_collector,
    )

    # In agent session
    collector = get_metrics_collector(spec_dir)

    with collector.track_session("coder", session_num=1, subtask_id="1.1") as session:
        session.record_tool_call("Bash", duration_ms=150, success=True)
        session.record_tool_call("Read", duration_ms=50, success=True)
        session.set_tokens(input=1500, output=800, thinking=2000)

    # Get insights
    insights = collector.get_insights()
    print(f"Avg session duration: {insights.avg_session_duration_ms}ms")
    print(f"Tool success rate: {insights.tool_success_rate:.1%}")
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Generator

logger = logging.getLogger(__name__)


# =============================================================================
# Metrics Data Structures
# =============================================================================


class SessionOutcome(str, Enum):
    """Possible outcomes for a session."""

    SUCCESS = "success"  # Subtask completed
    PARTIAL = "partial"  # Made progress but not complete
    FAILED = "failed"  # Session ended in error
    TIMEOUT = "timeout"  # Session timed out
    STUCK = "stuck"  # Agent got stuck
    CANCELLED = "cancelled"  # User cancelled


@dataclass
class ToolCallMetric:
    """Metrics for a single tool call."""

    tool_name: str
    started_at: str
    duration_ms: int
    success: bool
    error: str | None = None
    input_preview: str | None = None  # Truncated input for debugging
    output_size_bytes: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "started_at": self.started_at,
            "duration_ms": self.duration_ms,
            "success": self.success,
            "error": self.error,
            "input_preview": self.input_preview,
            "output_size_bytes": self.output_size_bytes,
        }


@dataclass
class SessionMetrics:
    """
    Comprehensive metrics for a single agent session.

    Captures everything needed to understand session behavior:
    - Token usage (input, output, thinking)
    - Tool calls with timing
    - Overall timing and outcome
    - Context for debugging
    """

    # Identification
    session_id: str
    agent_type: str
    phase: str
    session_num: int
    subtask_id: str | None = None

    # Timing
    started_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    ended_at: str | None = None
    duration_ms: int = 0

    # Token usage
    tokens_input: int = 0
    tokens_output: int = 0
    tokens_thinking: int = 0

    @property
    def tokens_total(self) -> int:
        return self.tokens_input + self.tokens_output + self.tokens_thinking

    # Tool calls
    tool_calls: list[ToolCallMetric] = field(default_factory=list)

    @property
    def tool_call_count(self) -> int:
        return len(self.tool_calls)

    @property
    def tool_success_count(self) -> int:
        return sum(1 for tc in self.tool_calls if tc.success)

    @property
    def tool_failure_count(self) -> int:
        return sum(1 for tc in self.tool_calls if not tc.success)

    @property
    def tool_success_rate(self) -> float:
        if not self.tool_calls:
            return 1.0
        return self.tool_success_count / len(self.tool_calls)

    # Outcome
    outcome: SessionOutcome = SessionOutcome.PARTIAL
    error_message: str | None = None
    error_category: str | None = None

    # Context
    spec_id: str | None = None
    project_name: str | None = None
    model: str | None = None
    thinking_budget: int | None = None

    # Git context
    commits_before: int = 0
    commits_after: int = 0

    @property
    def commits_made(self) -> int:
        return max(0, self.commits_after - self.commits_before)

    def finish(
        self,
        outcome: SessionOutcome = SessionOutcome.SUCCESS,
        error_message: str | None = None,
        error_category: str | None = None,
    ) -> None:
        """Mark session as finished."""
        self.ended_at = datetime.now(timezone.utc).isoformat()
        self.outcome = outcome
        self.error_message = error_message
        self.error_category = error_category

        # Calculate duration
        start = datetime.fromisoformat(self.started_at.replace("Z", "+00:00"))
        end = datetime.fromisoformat(self.ended_at.replace("Z", "+00:00"))
        self.duration_ms = int((end - start).total_seconds() * 1000)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "session_id": self.session_id,
            "agent_type": self.agent_type,
            "phase": self.phase,
            "session_num": self.session_num,
            "subtask_id": self.subtask_id,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_ms": self.duration_ms,
            "tokens_input": self.tokens_input,
            "tokens_output": self.tokens_output,
            "tokens_thinking": self.tokens_thinking,
            "tokens_total": self.tokens_total,
            "tool_calls": [tc.to_dict() for tc in self.tool_calls],
            "tool_call_count": self.tool_call_count,
            "tool_success_count": self.tool_success_count,
            "tool_failure_count": self.tool_failure_count,
            "tool_success_rate": self.tool_success_rate,
            "outcome": self.outcome.value,
            "error_message": self.error_message,
            "error_category": self.error_category,
            "spec_id": self.spec_id,
            "project_name": self.project_name,
            "model": self.model,
            "thinking_budget": self.thinking_budget,
            "commits_before": self.commits_before,
            "commits_after": self.commits_after,
            "commits_made": self.commits_made,
        }


@dataclass
class ToolUsageInsights:
    """Aggregated insights about tool usage patterns."""

    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0

    # Per-tool breakdown
    calls_by_tool: dict[str, int] = field(default_factory=dict)
    failures_by_tool: dict[str, int] = field(default_factory=dict)
    avg_duration_by_tool: dict[str, float] = field(default_factory=dict)

    # Unused tools (in agent config but never called)
    unused_tools: list[str] = field(default_factory=list)

    # Slow tools (avg > threshold)
    slow_tools: list[tuple[str, float]] = field(default_factory=list)

    # High-failure tools (failure rate > threshold)
    unreliable_tools: list[tuple[str, float]] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        if self.total_calls == 0:
            return 1.0
        return self.successful_calls / self.total_calls

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_calls": self.total_calls,
            "successful_calls": self.successful_calls,
            "failed_calls": self.failed_calls,
            "success_rate": self.success_rate,
            "calls_by_tool": self.calls_by_tool,
            "failures_by_tool": self.failures_by_tool,
            "avg_duration_by_tool": self.avg_duration_by_tool,
            "unused_tools": self.unused_tools,
            "slow_tools": self.slow_tools,
            "unreliable_tools": self.unreliable_tools,
        }


@dataclass
class SessionInsights:
    """Aggregated insights from all sessions."""

    total_sessions: int = 0
    successful_sessions: int = 0
    failed_sessions: int = 0
    stuck_sessions: int = 0

    # Timing
    total_duration_ms: int = 0
    avg_session_duration_ms: float = 0.0
    min_session_duration_ms: int = 0
    max_session_duration_ms: int = 0

    # Tokens
    total_tokens_input: int = 0
    total_tokens_output: int = 0
    total_tokens_thinking: int = 0
    avg_tokens_per_session: float = 0.0

    # By agent type
    sessions_by_agent: dict[str, int] = field(default_factory=dict)
    success_rate_by_agent: dict[str, float] = field(default_factory=dict)

    # Tool insights
    tool_insights: ToolUsageInsights = field(default_factory=ToolUsageInsights)

    # Recent errors
    recent_errors: list[dict[str, Any]] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        if self.total_sessions == 0:
            return 1.0
        return self.successful_sessions / self.total_sessions

    @property
    def total_tokens(self) -> int:
        return (
            self.total_tokens_input
            + self.total_tokens_output
            + self.total_tokens_thinking
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_sessions": self.total_sessions,
            "successful_sessions": self.successful_sessions,
            "failed_sessions": self.failed_sessions,
            "stuck_sessions": self.stuck_sessions,
            "success_rate": self.success_rate,
            "total_duration_ms": self.total_duration_ms,
            "avg_session_duration_ms": self.avg_session_duration_ms,
            "min_session_duration_ms": self.min_session_duration_ms,
            "max_session_duration_ms": self.max_session_duration_ms,
            "total_tokens_input": self.total_tokens_input,
            "total_tokens_output": self.total_tokens_output,
            "total_tokens_thinking": self.total_tokens_thinking,
            "total_tokens": self.total_tokens,
            "avg_tokens_per_session": self.avg_tokens_per_session,
            "sessions_by_agent": self.sessions_by_agent,
            "success_rate_by_agent": self.success_rate_by_agent,
            "tool_insights": self.tool_insights.to_dict(),
            "recent_errors": self.recent_errors,
        }


# =============================================================================
# Session Tracker (Context Manager)
# =============================================================================


class SessionTracker:
    """
    Context manager for tracking a single session.

    Usage:
        with collector.track_session("coder", session_num=1) as tracker:
            tracker.record_tool_call("Bash", duration_ms=100, success=True)
            tracker.set_tokens(input=1000, output=500)
    """

    def __init__(
        self,
        metrics: SessionMetrics,
        collector: MetricsCollector,
    ):
        self.metrics = metrics
        self.collector = collector
        self._tool_start_times: dict[str, float] = {}

    def record_tool_call(
        self,
        tool_name: str,
        duration_ms: int,
        success: bool,
        error: str | None = None,
        input_preview: str | None = None,
        output_size_bytes: int | None = None,
    ) -> None:
        """Record a tool call with metrics."""
        self.metrics.tool_calls.append(
            ToolCallMetric(
                tool_name=tool_name,
                started_at=datetime.now(timezone.utc).isoformat(),
                duration_ms=duration_ms,
                success=success,
                error=error,
                input_preview=input_preview[:200] if input_preview else None,
                output_size_bytes=output_size_bytes,
            )
        )

    def start_tool(self, tool_name: str) -> None:
        """Mark tool call start (for calculating duration)."""
        self._tool_start_times[tool_name] = time.time()

    def end_tool(
        self,
        tool_name: str,
        success: bool,
        error: str | None = None,
        input_preview: str | None = None,
        output_size_bytes: int | None = None,
    ) -> None:
        """Mark tool call end and record metrics."""
        start_time = self._tool_start_times.pop(tool_name, time.time())
        duration_ms = int((time.time() - start_time) * 1000)
        self.record_tool_call(
            tool_name=tool_name,
            duration_ms=duration_ms,
            success=success,
            error=error,
            input_preview=input_preview,
            output_size_bytes=output_size_bytes,
        )

    def set_tokens(
        self,
        input: int = 0,
        output: int = 0,
        thinking: int = 0,
    ) -> None:
        """Set token counts for the session."""
        self.metrics.tokens_input = input
        self.metrics.tokens_output = output
        self.metrics.tokens_thinking = thinking

    def add_tokens(
        self,
        input: int = 0,
        output: int = 0,
        thinking: int = 0,
    ) -> None:
        """Add to token counts (for streaming)."""
        self.metrics.tokens_input += input
        self.metrics.tokens_output += output
        self.metrics.tokens_thinking += thinking

    def set_git_context(self, commits_before: int, commits_after: int) -> None:
        """Set git commit context."""
        self.metrics.commits_before = commits_before
        self.metrics.commits_after = commits_after

    def set_model(self, model: str, thinking_budget: int | None = None) -> None:
        """Set model information."""
        self.metrics.model = model
        self.metrics.thinking_budget = thinking_budget

    def mark_success(self) -> None:
        """Mark session as successful."""
        self.metrics.outcome = SessionOutcome.SUCCESS

    def mark_partial(self) -> None:
        """Mark session as partial progress."""
        self.metrics.outcome = SessionOutcome.PARTIAL

    def mark_failed(
        self,
        error_message: str | None = None,
        error_category: str | None = None,
    ) -> None:
        """Mark session as failed."""
        self.metrics.outcome = SessionOutcome.FAILED
        self.metrics.error_message = error_message
        self.metrics.error_category = error_category

    def mark_stuck(self) -> None:
        """Mark session as stuck."""
        self.metrics.outcome = SessionOutcome.STUCK

    def mark_timeout(self) -> None:
        """Mark session as timed out."""
        self.metrics.outcome = SessionOutcome.TIMEOUT


# =============================================================================
# Metrics Collector
# =============================================================================


class MetricsCollector:
    """
    Central collector for session and tool metrics.

    Thread-safe, persistent storage to .alphhaspace/metrics/

    Usage:
        collector = MetricsCollector(spec_dir)

        with collector.track_session("coder", 1, "1.1") as session:
            session.record_tool_call("Bash", 100, True)

        insights = collector.get_insights()
    """

    def __init__(
        self,
        spec_dir: Path,
        max_sessions: int = 1000,  # Max sessions to keep in memory
    ):
        self.spec_dir = spec_dir
        self.max_sessions = max_sessions
        self._lock = threading.Lock()

        # Metrics storage
        self._sessions: list[SessionMetrics] = []
        self._tool_durations: dict[str, list[int]] = defaultdict(list)
        self._tool_failures: dict[str, int] = defaultdict(int)
        self._tool_successes: dict[str, int] = defaultdict(int)

        # Metrics directory
        self._metrics_dir = spec_dir / "metrics"
        self._metrics_dir.mkdir(parents=True, exist_ok=True)

        # Load existing metrics
        self._load_metrics()

    def _load_metrics(self) -> None:
        """Load existing metrics from disk."""
        sessions_file = self._metrics_dir / "sessions.jsonl"
        if sessions_file.exists():
            try:
                with open(sessions_file) as f:
                    for line in f:
                        if line.strip():
                            data = json.loads(line)
                            # Convert back to SessionMetrics (simplified)
                            self._process_loaded_session(data)
            except Exception as e:
                logger.warning(f"Failed to load metrics: {e}")

    def _process_loaded_session(self, data: dict[str, Any]) -> None:
        """Process a loaded session for aggregates."""
        # Update tool stats
        for tc in data.get("tool_calls", []):
            tool_name = tc.get("tool_name", "unknown")
            if tc.get("success"):
                self._tool_successes[tool_name] += 1
            else:
                self._tool_failures[tool_name] += 1
            if tc.get("duration_ms"):
                self._tool_durations[tool_name].append(tc["duration_ms"])

    def _save_session(self, metrics: SessionMetrics) -> None:
        """Append session to persistent storage."""
        sessions_file = self._metrics_dir / "sessions.jsonl"
        try:
            with open(sessions_file, "a") as f:
                f.write(json.dumps(metrics.to_dict()) + "\n")
        except Exception as e:
            logger.warning(f"Failed to save session metrics: {e}")

    @contextmanager
    def track_session(
        self,
        agent_type: str,
        session_num: int,
        subtask_id: str | None = None,
        phase: str = "coding",
        spec_id: str | None = None,
        project_name: str | None = None,
    ) -> Generator[SessionTracker, None, None]:
        """
        Context manager for tracking a session.

        Usage:
            with collector.track_session("coder", 1, "1.1") as session:
                session.record_tool_call("Bash", 100, True)
        """
        session_id = f"{agent_type}-{session_num}-{int(time.time() * 1000)}"
        metrics = SessionMetrics(
            session_id=session_id,
            agent_type=agent_type,
            phase=phase,
            session_num=session_num,
            subtask_id=subtask_id,
            spec_id=spec_id or self.spec_dir.name,
            project_name=project_name,
        )

        tracker = SessionTracker(metrics, self)

        try:
            yield tracker
            # If no explicit outcome set, mark as success
            if metrics.outcome == SessionOutcome.PARTIAL:
                metrics.outcome = SessionOutcome.SUCCESS
        except Exception as e:
            tracker.mark_failed(str(e), type(e).__name__)
            raise
        finally:
            # Finalize metrics
            metrics.finish(metrics.outcome, metrics.error_message, metrics.error_category)

            # Record in collector
            self._record_session(metrics)

    def _record_session(self, metrics: SessionMetrics) -> None:
        """Record completed session metrics."""
        with self._lock:
            # Add to in-memory list
            self._sessions.append(metrics)

            # Trim if over limit
            if len(self._sessions) > self.max_sessions:
                self._sessions = self._sessions[-self.max_sessions :]

            # Update tool aggregates
            for tc in metrics.tool_calls:
                if tc.success:
                    self._tool_successes[tc.tool_name] += 1
                else:
                    self._tool_failures[tc.tool_name] += 1
                self._tool_durations[tc.tool_name].append(tc.duration_ms)

            # Persist
            self._save_session(metrics)

    def record_tool_call(
        self,
        tool_name: str,
        duration_ms: int,
        success: bool,
    ) -> None:
        """Record a standalone tool call (outside session context)."""
        with self._lock:
            if success:
                self._tool_successes[tool_name] += 1
            else:
                self._tool_failures[tool_name] += 1
            self._tool_durations[tool_name].append(duration_ms)

    def get_insights(
        self,
        slow_threshold_ms: int = 5000,
        unreliable_threshold: float = 0.1,
        available_tools: list[str] | None = None,
    ) -> SessionInsights:
        """
        Get aggregated insights from all recorded sessions.

        Args:
            slow_threshold_ms: Tools with avg duration above this are "slow"
            unreliable_threshold: Tools with failure rate above this are "unreliable"
            available_tools: List of tools in agent config (to find unused)

        Returns:
            SessionInsights with aggregated metrics
        """
        with self._lock:
            insights = SessionInsights()

            if not self._sessions:
                return insights

            # Basic counts
            insights.total_sessions = len(self._sessions)
            insights.successful_sessions = sum(
                1 for s in self._sessions if s.outcome == SessionOutcome.SUCCESS
            )
            insights.failed_sessions = sum(
                1
                for s in self._sessions
                if s.outcome in (SessionOutcome.FAILED, SessionOutcome.TIMEOUT)
            )
            insights.stuck_sessions = sum(
                1 for s in self._sessions if s.outcome == SessionOutcome.STUCK
            )

            # Duration stats
            durations = [s.duration_ms for s in self._sessions if s.duration_ms > 0]
            if durations:
                insights.total_duration_ms = sum(durations)
                insights.avg_session_duration_ms = sum(durations) / len(durations)
                insights.min_session_duration_ms = min(durations)
                insights.max_session_duration_ms = max(durations)

            # Token stats
            insights.total_tokens_input = sum(s.tokens_input for s in self._sessions)
            insights.total_tokens_output = sum(s.tokens_output for s in self._sessions)
            insights.total_tokens_thinking = sum(
                s.tokens_thinking for s in self._sessions
            )
            insights.avg_tokens_per_session = (
                insights.total_tokens / len(self._sessions)
            )

            # By agent type
            for session in self._sessions:
                agent = session.agent_type
                insights.sessions_by_agent[agent] = (
                    insights.sessions_by_agent.get(agent, 0) + 1
                )

            # Success rate by agent
            for agent, count in insights.sessions_by_agent.items():
                successes = sum(
                    1
                    for s in self._sessions
                    if s.agent_type == agent and s.outcome == SessionOutcome.SUCCESS
                )
                insights.success_rate_by_agent[agent] = successes / count if count else 0

            # Tool insights
            tool_insights = self._get_tool_insights(
                slow_threshold_ms,
                unreliable_threshold,
                available_tools,
            )
            insights.tool_insights = tool_insights

            # Recent errors
            errors = [
                {
                    "session_id": s.session_id,
                    "agent_type": s.agent_type,
                    "error_message": s.error_message,
                    "error_category": s.error_category,
                    "timestamp": s.ended_at,
                }
                for s in self._sessions
                if s.error_message
            ]
            insights.recent_errors = errors[-10:]  # Last 10 errors

            return insights

    def _get_tool_insights(
        self,
        slow_threshold_ms: int,
        unreliable_threshold: float,
        available_tools: list[str] | None,
    ) -> ToolUsageInsights:
        """Get detailed tool usage insights."""
        insights = ToolUsageInsights()

        # Aggregate totals
        insights.total_calls = sum(self._tool_successes.values()) + sum(
            self._tool_failures.values()
        )
        insights.successful_calls = sum(self._tool_successes.values())
        insights.failed_calls = sum(self._tool_failures.values())

        # Per-tool stats
        all_tools = set(self._tool_successes.keys()) | set(self._tool_failures.keys())

        for tool in all_tools:
            successes = self._tool_successes.get(tool, 0)
            failures = self._tool_failures.get(tool, 0)
            total = successes + failures

            insights.calls_by_tool[tool] = total
            insights.failures_by_tool[tool] = failures

            # Average duration
            if tool in self._tool_durations and self._tool_durations[tool]:
                avg = sum(self._tool_durations[tool]) / len(self._tool_durations[tool])
                insights.avg_duration_by_tool[tool] = avg

                # Check if slow
                if avg > slow_threshold_ms:
                    insights.slow_tools.append((tool, avg))

            # Check if unreliable
            if total > 0:
                failure_rate = failures / total
                if failure_rate > unreliable_threshold:
                    insights.unreliable_tools.append((tool, failure_rate))

        # Sort by severity
        insights.slow_tools.sort(key=lambda x: x[1], reverse=True)
        insights.unreliable_tools.sort(key=lambda x: x[1], reverse=True)

        # Find unused tools
        if available_tools:
            used_tools = set(insights.calls_by_tool.keys())
            insights.unused_tools = [t for t in available_tools if t not in used_tools]

        return insights

    def get_session_history(
        self,
        limit: int = 10,
        agent_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get recent session history."""
        with self._lock:
            sessions = self._sessions
            if agent_type:
                sessions = [s for s in sessions if s.agent_type == agent_type]
            return [s.to_dict() for s in sessions[-limit:]]

    def get_tool_performance(self, tool_name: str) -> dict[str, Any]:
        """Get detailed performance stats for a specific tool."""
        with self._lock:
            successes = self._tool_successes.get(tool_name, 0)
            failures = self._tool_failures.get(tool_name, 0)
            total = successes + failures
            durations = self._tool_durations.get(tool_name, [])

            return {
                "tool_name": tool_name,
                "total_calls": total,
                "successes": successes,
                "failures": failures,
                "success_rate": successes / total if total else 1.0,
                "avg_duration_ms": sum(durations) / len(durations) if durations else 0,
                "min_duration_ms": min(durations) if durations else 0,
                "max_duration_ms": max(durations) if durations else 0,
                "p50_duration_ms": self._percentile(durations, 50),
                "p95_duration_ms": self._percentile(durations, 95),
                "p99_duration_ms": self._percentile(durations, 99),
            }

    def _percentile(self, data: list[int], percentile: int) -> int:
        """Calculate percentile of a list."""
        if not data:
            return 0
        sorted_data = sorted(data)
        index = int(len(sorted_data) * percentile / 100)
        return sorted_data[min(index, len(sorted_data) - 1)]

    def export_metrics(self, output_path: Path | None = None) -> Path:
        """Export all metrics to a JSON file."""
        output_path = output_path or self._metrics_dir / "metrics_export.json"

        with self._lock:
            data = {
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "spec_dir": str(self.spec_dir),
                "sessions": [s.to_dict() for s in self._sessions],
                "insights": self.get_insights().to_dict(),
            }

            with open(output_path, "w") as f:
                json.dump(data, f, indent=2)

        return output_path

    def clear_metrics(self) -> None:
        """Clear all metrics (use with caution)."""
        with self._lock:
            self._sessions.clear()
            self._tool_durations.clear()
            self._tool_failures.clear()
            self._tool_successes.clear()

            # Clear persistent storage
            sessions_file = self._metrics_dir / "sessions.jsonl"
            if sessions_file.exists():
                sessions_file.unlink()


# =============================================================================
# Global Collector Factory
# =============================================================================

_collectors: dict[str, MetricsCollector] = {}
_collectors_lock = threading.Lock()


def get_metrics_collector(spec_dir: Path) -> MetricsCollector:
    """
    Get or create a MetricsCollector for a spec directory.

    Thread-safe singleton per spec directory.
    """
    key = str(spec_dir.resolve())

    with _collectors_lock:
        if key not in _collectors:
            _collectors[key] = MetricsCollector(spec_dir)
        return _collectors[key]


def clear_collectors() -> None:
    """Clear all cached collectors (for testing)."""
    with _collectors_lock:
        _collectors.clear()


# =============================================================================
# Convenience Decorators
# =============================================================================


def track_tool(tool_name: str):
    """
    Decorator to track tool execution metrics.

    Usage:
        @track_tool("custom_tool")
        async def my_tool():
            ...
    """

    def decorator(func):
        async def wrapper(*args, **kwargs):
            # Try to get collector from context
            spec_dir = kwargs.get("spec_dir")
            if not spec_dir and args:
                # Check if first arg has spec_dir attribute
                first_arg = args[0]
                if hasattr(first_arg, "spec_dir"):
                    spec_dir = first_arg.spec_dir

            start = time.time()
            success = True
            error = None

            try:
                return await func(*args, **kwargs)
            except Exception as e:
                success = False
                error = str(e)
                raise
            finally:
                duration_ms = int((time.time() - start) * 1000)
                if spec_dir:
                    collector = get_metrics_collector(spec_dir)
                    collector.record_tool_call(tool_name, duration_ms, success)

        return wrapper

    return decorator


# =============================================================================
# Export All Public APIs
# =============================================================================

__all__ = [
    # Enums
    "SessionOutcome",
    # Metrics classes
    "ToolCallMetric",
    "SessionMetrics",
    "ToolUsageInsights",
    "SessionInsights",
    # Tracking
    "SessionTracker",
    "MetricsCollector",
    # Factory
    "get_metrics_collector",
    "clear_collectors",
    # Decorators
    "track_tool",
]
