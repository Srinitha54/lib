"""
agents/sequential_agent.py
-----------------------------
The specialist sub-agent that runs the SEQUENTIAL reservation workflow:
member lookup -> membership check -> book check -> eligibility check ->
due date calculation -> confirmation -> submit/cancel, each step strictly
blocked on the previous one.

This agent is a module-level SINGLETON — created once on first use and
reused across every call within a container's lifetime, exactly like the
original single-file design. This is what lets it correctly remember "I
already presented a summary and I'm waiting for YES/NO" across separate
invoke() calls in the same AgentCore session, even though the
orchestrator now sits in front of it instead of being called directly.
"""

from strands import Agent, tool
from strands.tools.executors import SequentialToolExecutor

from agents.model_config import bedrock_model
from agents.debug_tracing import DebugTraceHooks
from tools.library_tools import (
    lookup_member,
    check_membership_status,
    check_book_availability,
    get_author_details,
    check_reservation_eligibility,
    calculate_reservation_due_date,
    submit_reservation,
    cancel_book_reservation,
    get_member_borrowing_history,
    get_active_reservations_list,
)

SEQUENTIAL_TOOLS = [
    lookup_member,
    check_membership_status,
    check_book_availability,
    get_author_details,
    check_reservation_eligibility,
    calculate_reservation_due_date,
    submit_reservation,
    cancel_book_reservation,
    get_member_borrowing_history,
    get_active_reservations_list,
]

SEQUENTIAL_SYSTEM_PROMPT = """
You are a helpful Library Reservation Assistant. Your job is to help members
reserve books from the library.

SEQUENTIAL WORKFLOW — follow these steps STRICTLY IN ORDER, one at a time.
Do not skip steps or combine them:

STEP 1: Look up the member using lookup_member.
STEP 2: Check if their membership is valid using check_membership_status.
        If expired, STOP and inform the user. Do NOT continue.
STEP 3: Check if the requested book is available using check_book_availability.
        If not available, STOP and inform the user. Do NOT continue.
STEP 4: Check reservation eligibility using check_reservation_eligibility.
        If not eligible, STOP and explain why. Do NOT continue.
STEP 5: Calculate the due date using calculate_reservation_due_date.
STEP 6: Present a RESERVATION SUMMARY to the user showing:
        - Member name and ID
        - Book title and author
        - Reservation date (today)
        - Due date
        - Current active reservations count
        Then ask: "Would you like to confirm this reservation? (YES / NO)"
        WAIT for the user's response before doing anything else.
STEP 7: If the user says YES → call submit_reservation with confirmed=True to save to DynamoDB.
        If the user says NO  → cancel and inform the user politely. Do NOT call submit_reservation.

If the incoming message includes a line like
"[System note: classified as CONFIRMED]" or "[System note: classified as
REJECTED]" appended by the orchestrator, treat that as a strong signal of
the user's intent for STEP 7 — CONFIRMED means proceed as if they said
YES, REJECTED means proceed as if they said NO. If the note says UNCLEAR,
or there is no such note, judge the user's actual words as normal and ask
again if genuinely ambiguous.

CANCELLING A RESERVATION:
If the user asks to cancel, un-reserve, or release a book they (or another
member) currently have reserved:
  1. Identify the member_id and book_id from the conversation. If either is
     missing or unclear, ask the user for it — do not guess.
  2. If the user's cancellation request was already an explicit, unambiguous
     instruction (e.g. "cancel my reservation for BOOK-2006"), you may treat
     that as confirmation. If there's any ambiguity, ask "Are you sure you
     want to cancel this reservation? (YES / NO)" and wait for a clear YES.
  3. Call cancel_book_reservation with confirmed=True.
  4. If it succeeds, tell the user the book is now available again — they
     (or someone else) can reserve it fresh by going through the normal
     reservation flow above.
  5. If it fails (e.g. "no active reservation found"), tell the user clearly
     rather than guessing or inventing a reason.

IMPORTANT RULES:
- Always be polite and professional.
- NEVER call submit_reservation with confirmed=True unless the user just replied
  with a clear affirmative (e.g. "YES", "yes", "confirm") to the summary you presented,
  or the message carries a "[System note: classified as CONFIRMED]" tag.
  If there is any ambiguity, ask again instead of guessing.
- NEVER call cancel_book_reservation with confirmed=True unless the user has clearly
  asked to cancel that specific reservation. Never claim a reservation doesn't exist
  without actually calling a tool to check.
- Use get_author_details when you want to enrich the summary with author background,
  but it is optional — book title/author name already come from check_book_availability.
- If any step fails, explain the issue clearly and stop.
"""

_sequential_agent_instance: Agent | None = None
_debug_enabled = False


def set_debug(enabled: bool) -> None:
    """
    Must be called (if at all) BEFORE the first message is handled, since
    the underlying Agent singleton is created lazily on first use and its
    debug hooks can't be changed after that.
    """
    global _debug_enabled
    _debug_enabled = enabled


def get_sequential_agent() -> Agent:
    """
    Returns the singleton sequential workflow agent, creating it on first
    call. tool_executor=SequentialToolExecutor() makes strict one-at-a-time
    tool execution a guaranteed runtime property, not just a request in
    the system prompt.
    """
    global _sequential_agent_instance
    if _sequential_agent_instance is None:
        _sequential_agent_instance = Agent(
            model=bedrock_model,
            system_prompt=SEQUENTIAL_SYSTEM_PROMPT,
            tools=SEQUENTIAL_TOOLS,
            tool_executor=SequentialToolExecutor(),
            hooks=[DebugTraceHooks()] if _debug_enabled else None,
        )
    return _sequential_agent_instance


@tool
def run_sequential_workflow(user_message: str) -> str:
    """
    Delegate a message to the sequential library-reservation workflow
    specialist, which handles member lookup, membership/availability
    checks, due-date computation, presenting a confirmation summary, and
    submitting or cancelling reservations — one step at a time, strictly
    in order.

    Always pass the user's message through as close to verbatim as
    possible. You may append a "[System note: classified as ...]" line
    if you've already classified the message via review_human_response,
    but never rewrite or summarize the user's actual words.

    Args:
        user_message: The user's message, optionally with an appended
            classification note.
    """
    agent = get_sequential_agent()
    return str(agent(user_message))