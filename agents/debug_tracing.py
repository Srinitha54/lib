"""
agents/debug_tracing.py
-------------------------
Shared debug tracing used by every agent (orchestrator + sub-agents) so
that --debug shows a single unified timeline across the whole multi-agent
call chain — the orchestrator's delegation call AND the sub-agent's
internal tool calls all share the same clock, started fresh each turn.
"""

import time
from strands.hooks import HookProvider, HookRegistry, BeforeToolCallEvent, AfterToolCallEvent

_trace_start_time: float | None = None


def reset_trace_clock() -> None:
    """
    Reset the per-turn stopwatch. Call this once right before each
    top-level agent(user_input) call (main.py's --debug flag does this),
    so timestamps restart at 0 for every new turn instead of accumulating
    across the whole session.
    """
    global _trace_start_time
    _trace_start_time = time.monotonic()


def _elapsed_ms() -> float:
    if _trace_start_time is None:
        return 0.0
    return (time.monotonic() - _trace_start_time) * 1000


class DebugTraceHooks(HookProvider):
    """Registers Before/AfterToolCallEvent callbacks that print timestamped
    START/END lines for every tool invocation on whichever agent this is
    attached to."""

    def register_hooks(self, registry: HookRegistry) -> None:
        registry.add_callback(BeforeToolCallEvent, self._on_before)
        registry.add_callback(AfterToolCallEvent, self._on_after)

    def _on_before(self, event: BeforeToolCallEvent) -> None:
        name = event.tool_use.get("name", "unknown_tool")
        print(f"  [t+{_elapsed_ms():7.1f}ms] START {name}")

    def _on_after(self, event: AfterToolCallEvent) -> None:
        name = event.tool_use.get("name", "unknown_tool")
        print(f"  [t+{_elapsed_ms():7.1f}ms] END   {name}")