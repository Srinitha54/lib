"""
agents/orchestrator_agent.py
-----------------------------
The top-level orchestrator agent. This is the ONLY agent main.py and
agentcore_entrypoint.py talk to directly — but it is no longer a single
agent doing everything itself. It is itself a Strands Agent whose own
tools are two OTHER agents (wrapped as @tool functions), not raw library
functions. This is the genuine multi-agent structure:

    agents/
    ├── orchestrator_agent.py  <- routes each message to the right specialist
    ├── sequential_agent.py    <- specialist: sequential reservation workflow
    ├── parallel_agent.py      <- specialist: parallel reservation workflow
    └── human_review.py        <- specialist: classifies YES/NO/unclear replies

WHY THE ORCHESTRATOR DOESN'T CHOOSE SEQUENTIAL VS PARALLEL ITSELF:
Each deployed AgentCore Runtime is already mode-specific — WORKFLOW_MODE
(an env var) picks sequential or parallel at DEPLOY time, matching how
the assessment demonstrates each pattern as a separate, distinct run. So
the orchestrator for a given deployment only ever has ONE workflow
specialist wired in — there's no ambiguity for it to get wrong. Its real
job is: decide whether the incoming message looks like a reply to a
pending confirmation (and if so, consult the human_review specialist for
a clean CONFIRMED/REJECTED/UNCLEAR verdict), then delegate to the single
workflow specialist with that context attached, and relay its response
back unchanged.

This was a deliberate choice to avoid adding a SECOND LLM routing
decision (sequential vs parallel) on top of a conversation flow that
already has to track pending confirmations precisely — an unforced extra
routing choice would be pure added risk with no benefit here, especially
given how much tuning it took to get bare "yes"/"no" replies handled
reliably with a small/fast model.

HOW STRANDS AGENTS WORK (recap):
  1. You create an Agent with a system prompt and a list of tools.
  2. You call the agent with a user message: agent("user message here")
  3. The LLM reads your message + system prompt, then decides which
     tools to call and in what order.
  4. Here, the orchestrator's "tools" are themselves other agents —
     Strands supports this natively since a @tool function can do
     anything inside it, including calling another Agent.
"""

from strands import Agent

from agents.model_config import bedrock_model
from agents.debug_tracing import DebugTraceHooks, reset_trace_clock as _reset_trace_clock  # noqa: F401 (re-exported for main.py)
from agents.human_review import review_human_response
import agents.sequential_agent as sequential_agent
import agents.parallel_agent as parallel_agent

ORCHESTRATOR_SYSTEM_PROMPT_TEMPLATE = """
You are the top-level orchestrator for a library reservation system. You
do NOT perform any library business logic yourself — you have exactly
two tools, and your entire job is deciding how to use them and relaying
the result back to the user:

1. review_human_response — classifies whether the user's message is a
   clear confirmation (CONFIRMED), a clear rejection (REJECTED), or
   something else (UNCLEAR). Use this ONLY when the user's message looks
   like a short reply to a yes/no question that was just asked (e.g.
   "yes", "no", "yeah go ahead", "actually cancel that") — never use it
   on the user's first, original request.

2. {workflow_tool_name} — delegates the actual reservation work (member
   lookup, membership/availability checks, due-date calculation,
   presenting a summary, submitting or cancelling a reservation) to the
   specialist workflow agent. This tool does ALL the real work; you
   never call library tools directly because you don't have any.

HOW TO HANDLE EACH TURN:
- If the message is clearly a new, original request (e.g. mentions a
  book ID, member ID, or a clear new ask), just call {workflow_tool_name}
  with the user's message passed through essentially verbatim.
- If the message looks like a short reply to a confirmation question
  (e.g. just "yes", "no", "yep", "nah", "confirm", "cancel that"), FIRST
  call review_human_response on it, THEN call {workflow_tool_name} with
  the original message plus an appended note in exactly this format:
  "<original user message>

  [System note: classified as <VERDICT>]"
  where <VERDICT> is exactly what review_human_response returned.
- After {workflow_tool_name} returns its response, relay it back to the
  user as-is — do not rewrite, summarize, or add your own commentary.
  The workflow specialist already wrote the complete, correct reply.
- You never fabricate confirmation yourself and you never decide
  reservation outcomes yourself — that logic belongs entirely to
  {workflow_tool_name} and the tools underneath it.
"""


def _build_orchestrator(workflow_mode: str, debug: bool = False) -> Agent:
    mode = workflow_mode.lower().strip()

    if mode == "parallel":
        parallel_agent.set_debug(debug)
        workflow_tool = parallel_agent.run_parallel_workflow
        tool_name = "run_parallel_workflow"
    else:
        sequential_agent.set_debug(debug)
        workflow_tool = sequential_agent.run_sequential_workflow
        tool_name = "run_sequential_workflow"

    system_prompt = ORCHESTRATOR_SYSTEM_PROMPT_TEMPLATE.format(workflow_tool_name=tool_name)

    return Agent(
        model=bedrock_model,
        system_prompt=system_prompt,
        tools=[workflow_tool, review_human_response],
        hooks=[DebugTraceHooks()] if debug else None,
    )


def get_agent(workflow_mode: str = "sequential", debug: bool = False) -> Agent:
    """
    Factory function: returns the top-level orchestrator agent, wired to
    delegate to the correct workflow specialist (sequential or parallel)
    based on workflow_mode. This is the ONLY function main.py and
    agentcore_entrypoint.py call — the multi-agent structure underneath
    (orchestrator -> workflow specialist -> library tools, plus the
    human_review specialist) is fully encapsulated here.

    workflow_mode: 'sequential' or 'parallel'
    debug: if True, attaches DebugTraceHooks to both the orchestrator and
           the relevant workflow specialist, so tool calls at both levels
           print timestamped START/END lines on one shared clock (used by
           main.py's --debug flag).
    """
    return _build_orchestrator(workflow_mode, debug=debug)