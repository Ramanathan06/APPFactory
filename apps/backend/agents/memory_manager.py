"""
Memory Management for Agent System
===================================

Handles session memory storage using dual-layer approach:
- PRIMARY: Graphiti (when enabled) - semantic search, cross-session context
- FALLBACK: File-based memory - zero dependencies, always available

Includes:
- Circuit breaker protection for Graphiti calls
- LRU caching for query results
- Metrics tracking for memory operations
"""

import logging
from pathlib import Path

from debug import (
    debug,
    debug_detailed,
    debug_error,
    debug_section,
    debug_success,
    debug_warning,
    is_debug_enabled,
)
from graphiti_config import get_graphiti_status, is_graphiti_enabled

# Import from parent memory package
# Now safe since this module is named memory_manager (not memory)
from memory import save_session_insights as save_file_based_memory

# Import circuit breaker for resilient Graphiti calls
from core.exceptions import graphiti_circuit, MemoryConnectionError, MemoryQueryError

logger = logging.getLogger(__name__)

# Cache for CachedGraphitiMemory instances (avoid recreating)
_memory_cache: dict[str, "CachedGraphitiMemory"] = {}


def _get_or_create_memory(
    spec_dir: Path,
    project_dir: Path,
) -> "CachedGraphitiMemory | None":
    """
    Get or create a cached GraphitiMemory instance.

    Uses a global cache to avoid recreating memory instances for the same spec.
    Returns None if Graphiti is not available.
    """
    if not is_graphiti_enabled():
        return None

    cache_key = str(spec_dir)

    if cache_key in _memory_cache:
        cached = _memory_cache[cache_key]
        if cached.is_enabled:
            return cached

    try:
        from integrations.graphiti import create_cached_memory

        memory = create_cached_memory(
            spec_dir=spec_dir,
            project_dir=project_dir,
            cache_size=100,
            ttl_seconds=300,  # 5 minute cache
            enable_batching=True,
        )

        if memory.is_enabled:
            _memory_cache[cache_key] = memory
            return memory

        return None

    except ImportError:
        logger.debug("Graphiti packages not installed")
        return None
    except Exception as e:
        logger.warning(f"Failed to create cached memory: {e}")
        return None


def debug_memory_system_status() -> None:
    """
    Print memory system status for debugging.

    Called at startup when DEBUG=true to show memory configuration.
    """
    if not is_debug_enabled():
        return

    debug_section("memory", "Memory System Status")

    # Get Graphiti status
    graphiti_status = get_graphiti_status()

    debug(
        "memory",
        "Memory system configuration",
        primary_system="Graphiti"
        if graphiti_status.get("available")
        else "File-based (fallback)",
        graphiti_enabled=graphiti_status.get("enabled"),
        graphiti_available=graphiti_status.get("available"),
    )

    if graphiti_status.get("enabled"):
        debug_detailed(
            "memory",
            "Graphiti configuration",
            host=graphiti_status.get("host"),
            port=graphiti_status.get("port"),
            database=graphiti_status.get("database"),
            llm_provider=graphiti_status.get("llm_provider"),
            embedder_provider=graphiti_status.get("embedder_provider"),
        )

        if not graphiti_status.get("available"):
            debug_warning(
                "memory",
                "Graphiti not available",
                reason=graphiti_status.get("reason"),
                errors=graphiti_status.get("errors"),
            )
            debug("memory", "Will use file-based memory as fallback")
        else:
            debug_success("memory", "Graphiti ready as PRIMARY memory system")
    else:
        debug(
            "memory",
            "Graphiti disabled, using file-based memory only",
            note="Set GRAPHITI_ENABLED=true to enable Graphiti",
        )


async def get_graphiti_context(
    spec_dir: Path,
    project_dir: Path,
    subtask: dict,
) -> str | None:
    """
    Retrieve relevant context from Graphiti for the current subtask.

    This searches the knowledge graph for context relevant to the subtask's
    task description, returning past insights, patterns, and gotchas.

    Uses circuit breaker protection and caching for improved reliability.

    Args:
        spec_dir: Spec directory
        project_dir: Project root directory
        subtask: The current subtask being worked on

    Returns:
        Formatted context string or None if unavailable
    """
    if is_debug_enabled():
        debug(
            "memory",
            "Retrieving Graphiti context for subtask",
            subtask_id=subtask.get("id", "unknown"),
            subtask_desc=subtask.get("description", "")[:100],
        )

    # Get cached memory instance
    memory = _get_or_create_memory(spec_dir, project_dir)
    if memory is None:
        if is_debug_enabled():
            debug("memory", "Graphiti not available, skipping context retrieval")
        return None

    # Build search query from subtask description
    subtask_desc = subtask.get("description", "")
    subtask_id = subtask.get("id", "")
    query = f"{subtask_desc} {subtask_id}".strip()

    if not query:
        if is_debug_enabled():
            debug_warning("memory", "Empty query, skipping context retrieval")
        return None

    if is_debug_enabled():
        debug_detailed(
            "memory",
            "Searching Graphiti knowledge graph",
            query=query[:200],
            num_results=5,
        )

    try:
        # Use circuit breaker for resilient Graphiti calls
        @graphiti_circuit
        async def _fetch_context():
            context_items = await memory.get_relevant_context(query, num_results=5)
            session_history = await memory.get_session_history(limit=3)
            return context_items, session_history

        context_items, session_history = await _fetch_context()

        if is_debug_enabled():
            cache_stats = memory.get_cache_stats()
            debug(
                "memory",
                "Graphiti context retrieval complete",
                context_items_found=len(context_items) if context_items else 0,
                session_history_found=len(session_history) if session_history else 0,
                cache_hit_rate=f"{cache_stats.hit_rate:.1%}",
            )

        if not context_items and not session_history:
            if is_debug_enabled():
                debug("memory", "No relevant context found in Graphiti")
            return None

        # Format the context
        sections = ["## Graphiti Memory Context\n"]
        sections.append("_Retrieved from knowledge graph for this subtask:_\n")

        if context_items:
            sections.append("### Relevant Knowledge\n")
            for item in context_items:
                content = item.get("content", "")[:500]  # Truncate
                item_type = item.get("type", "unknown")
                sections.append(f"- **[{item_type}]** {content}\n")

        if session_history:
            sections.append("### Recent Session Insights\n")
            for session in session_history[:2]:  # Only show last 2
                session_num = session.get("session_number", "?")
                recommendations = session.get("recommendations_for_next_session", [])
                if recommendations:
                    sections.append(f"**Session {session_num} recommendations:**")
                    for rec in recommendations[:3]:  # Limit to 3
                        sections.append(f"- {rec}")
                    sections.append("")

        if is_debug_enabled():
            debug_success(
                "memory", "Graphiti context formatted", total_sections=len(sections)
            )

        return "\n".join(sections)

    except MemoryQueryError as e:
        logger.warning(f"Memory query failed: {e}")
        if is_debug_enabled():
            debug_warning("memory", "Memory query failed", error=str(e))
        return None
    except MemoryConnectionError as e:
        logger.warning(f"Memory connection failed: {e}")
        if is_debug_enabled():
            debug_error("memory", "Memory connection failed", error=str(e))
        return None
    except Exception as e:
        logger.warning(f"Failed to get Graphiti context: {e}")
        if is_debug_enabled():
            debug_error("memory", "Unexpected error in context retrieval", error=str(e))
        return None


async def save_session_memory(
    spec_dir: Path,
    project_dir: Path,
    subtask_id: str,
    session_num: int,
    success: bool,
    subtasks_completed: list[str],
    discoveries: dict | None = None,
) -> tuple[bool, str]:
    """
    Save session insights to memory.

    Memory Strategy:
    - PRIMARY: Graphiti (when enabled) - provides semantic search, cross-session context
    - FALLBACK: File-based (when Graphiti is disabled) - zero dependencies, always works

    Uses circuit breaker protection and caching for improved reliability.

    Args:
        spec_dir: Spec directory
        project_dir: Project root directory
        subtask_id: The subtask that was worked on
        session_num: Current session number
        success: Whether the subtask was completed successfully
        subtasks_completed: List of subtask IDs completed this session
        discoveries: Optional dict with file discoveries, patterns, gotchas

    Returns:
        Tuple of (success, storage_type) where storage_type is "graphiti" or "file"
    """
    # Debug: Log memory save start
    if is_debug_enabled():
        debug_section("memory", f"Saving Session {session_num} Memory")
        debug(
            "memory",
            "Memory save initiated",
            subtask_id=subtask_id,
            session_num=session_num,
            success=success,
            subtasks_completed=subtasks_completed,
            spec_dir=str(spec_dir),
        )

    # Build insights structure (same format for both storage systems)
    insights = {
        "subtasks_completed": subtasks_completed,
        "discoveries": discoveries
        or {
            "files_understood": {},
            "patterns_found": [],
            "gotchas_encountered": [],
        },
        "what_worked": [f"Implemented subtask: {subtask_id}"] if success else [],
        "what_failed": [] if success else [f"Failed to complete subtask: {subtask_id}"],
        "recommendations_for_next_session": [],
    }

    if is_debug_enabled():
        debug_detailed("memory", "Insights structure built", insights=insights)

    # Check Graphiti status for debugging
    if is_debug_enabled():
        graphiti_status = get_graphiti_status()
        debug(
            "memory",
            "Graphiti status check",
            enabled=graphiti_status.get("enabled"),
            available=graphiti_status.get("available"),
            host=graphiti_status.get("host"),
            port=graphiti_status.get("port"),
            database=graphiti_status.get("database"),
            llm_provider=graphiti_status.get("llm_provider"),
            embedder_provider=graphiti_status.get("embedder_provider"),
            reason=graphiti_status.get("reason") or "OK",
        )

    # PRIMARY: Try cached Graphiti memory with circuit breaker
    memory = _get_or_create_memory(spec_dir, project_dir)
    if memory is not None:
        if is_debug_enabled():
            debug("memory", "Attempting PRIMARY storage: Graphiti (cached)")

        try:
            # Use circuit breaker for resilient Graphiti calls
            @graphiti_circuit
            async def _save_to_graphiti():
                # Use structured insights if we have rich extracted data
                if discoveries and discoveries.get("file_insights"):
                    if is_debug_enabled():
                        debug(
                            "memory",
                            "Using save_structured_insights (rich data available)",
                        )
                    return await memory.save_structured_insights(discoveries)
                else:
                    return await memory.save_session_insights(session_num, insights)

            result = await _save_to_graphiti()

            if result:
                logger.info(
                    f"Session {session_num} insights saved to Graphiti (primary)"
                )
                if is_debug_enabled():
                    cache_stats = memory.get_cache_stats()
                    debug_success(
                        "memory",
                        f"Session {session_num} saved to Graphiti (PRIMARY)",
                        storage_type="graphiti",
                        subtasks_saved=len(subtasks_completed),
                        cache_hit_rate=f"{cache_stats.hit_rate:.1%}",
                    )
                return True, "graphiti"
            else:
                logger.warning(
                    "Graphiti save returned False, falling back to file-based"
                )
                if is_debug_enabled():
                    debug_warning(
                        "memory", "Graphiti save returned False, using FALLBACK"
                    )

        except MemoryConnectionError as e:
            logger.warning(f"Memory connection failed: {e}, falling back to file-based")
            if is_debug_enabled():
                debug_error("memory", "Memory connection failed", error=str(e))
        except MemoryQueryError as e:
            logger.warning(f"Memory save failed: {e}, falling back to file-based")
            if is_debug_enabled():
                debug_error("memory", "Memory save failed", error=str(e))
        except Exception as e:
            logger.warning(f"Graphiti save failed: {e}, falling back to file-based")
            if is_debug_enabled():
                debug_error("memory", "Graphiti save failed", error=str(e))
    else:
        if is_debug_enabled():
            debug("memory", "Graphiti not available, skipping to FALLBACK")

    # FALLBACK: File-based memory (when Graphiti is disabled or fails)
    if is_debug_enabled():
        debug("memory", "Attempting FALLBACK storage: File-based")

    try:
        memory_dir = spec_dir / "memory" / "session_insights"
        if is_debug_enabled():
            debug_detailed(
                "memory",
                "File-based memory path",
                memory_dir=str(memory_dir),
                session_file=f"session_{session_num:03d}.json",
            )

        save_file_based_memory(spec_dir, session_num, insights)
        logger.info(
            f"Session {session_num} insights saved to file-based memory (fallback)"
        )

        if is_debug_enabled():
            debug_success(
                "memory",
                f"Session {session_num} saved to file-based (FALLBACK)",
                storage_type="file",
                file_path=str(memory_dir / f"session_{session_num:03d}.json"),
                subtasks_saved=len(subtasks_completed),
            )
        return True, "file"
    except Exception as e:
        logger.error(f"File-based memory save also failed: {e}")
        if is_debug_enabled():
            debug_error("memory", "File-based memory save FAILED", error=str(e))
        return False, "none"


# Keep the old function name as an alias for backwards compatibility
async def save_session_to_graphiti(
    spec_dir: Path,
    project_dir: Path,
    subtask_id: str,
    session_num: int,
    success: bool,
    subtasks_completed: list[str],
    discoveries: dict | None = None,
) -> bool:
    """Backwards compatibility wrapper for save_session_memory."""
    result, _ = await save_session_memory(
        spec_dir,
        project_dir,
        subtask_id,
        session_num,
        success,
        subtasks_completed,
        discoveries,
    )
    return result
