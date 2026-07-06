"""
agents/parallel_agent.py
---------------------------
The specialist sub-agent that runs the PARALLEL reservation workflow:
membership validity and book availability are checked simultaneously,
merged, then the rest of the flow (eligibility, due date, confirmation,
submit/cancel) proceeds.

Same singleton pattern as sequential_agent.py, for the same reason: its
own conversation history must persist across turns within a session so
it correctly remembers a pending YES/NO confirmation.
"""

from strands import Agent, tool
from strands.tools.executors import ConcurrentToolExecutor

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

PARALLEL_TOOLS = [
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

PARALLEL_SYSTEM_PROMPT = """
You are a helpful Library Reservation Assistant. Your job is to help members
reserve books from the library.

PARALLEL WORKFLOW — some checks can be done at the same time to save time:

PHASE 1 (PARALLEL): Run these two checks simultaneously:
  - check_membership_status (is the member's membership valid?)
  - check_book_availability (is the book available?)

PHASE 2: After getting both results above, if either check failed, STOP and inform the user.

PHASE 3 (SEQUENTIAL): If both checks passed:
  - Run check_reservation_eligibility
  - Run calculate_reservation_due_date

PHASE 4: Present a RESERVATION SUMMARY to the user showing:
        - Member name and ID
        - Book title and author
        - Reservation date (today)
        - Due date
        - Current active reservations count
        Then ask: "Would you like to confirm this reservation? (YES / NO)"
        WAIT for the user's response before doing anything else.

PHASE 5: If the user says YES → call submit_reservation with confirmed=True to save to DynamoDB.
         If the user says NO  → cancel and inform the user politely. Do NOT call submit_reservation.

If the incoming message includes a line like
"[System note: classified as CONFIRMED]" or "[System note: classified as
REJECTED]" appended by the orchestrator, treat that as a strong signal of
the user's intent for PHASE 5 — CONFIRMED means proceed as if they said
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
- In PHASE 1, actually issue both tool calls together in the same turn so they run
  concurrently — do not call one, wait for its result, then call the other.
- NEVER call submit_reservation with confirmed=True unless the user just replied
  with a clear affirmative (e.g. "YES", "yes", "confirm") to the summary you presented,
  or the message carries a "[System note: classified as CONFIRMED]" tag.
- NEVER call cancel_book_reservation with confirmed=True unless the user has clearly
  asked to cancel that specific reservation. Never claim a reservation doesn't exist
  without actually calling a tool to check.
- If any check fails, explain the issue clearly and stop.
"""

_parallel_agent_instance: Agent | None = None
_debug_enabled = False


def set_debug(enabled: bool) -> None:
    """
    Must be called (if at all) BEFORE the first message is handled, since
    the underlying Agent singleton is created lazily on first use and its
    debug hooks can't be changed after that.
    """
    global _debug_enabled
    _debug_enabled = enabled


def get_parallel_agent() -> Agent:
    """
    Returns the singleton parallel workflow agent, creating it on first
    call. tool_executor=ConcurrentToolExecutor() makes concurrent tool
    execution a guaranteed runtime property, not just a request in the
    system prompt.
    """
    global _parallel_agent_instance
    if _parallel_agent_instance is None:
        _parallel_agent_instance = Agent(
            model=bedrock_model,
            system_prompt=PARALLEL_SYSTEM_PROMPT,
            tools=PARALLEL_TOOLS,
            tool_executor=ConcurrentToolExecutor(),
            hooks=[DebugTraceHooks()] if _debug_enabled else None,
        )
    return _parallel_agent_instance


@tool
def run_parallel_workflow(user_message: str) -> str:
    """
    Delegate a message to the parallel library-reservation workflow
    specialist, which checks membership validity and book availability
    concurrently, then proceeds through eligibility, due-date
    calculation, confirmation, and submission/cancellation.

    Always pass the user's message through as close to verbatim as
    possible. You may append a "[System note: classified as ...]" line
    if you've already classified the message via review_human_response,
    but never rewrite or summarize the user's actual words.

    Args:
        user_message: The user's message, optionally with an appended
            classification note.
    """
    agent = get_parallel_agent()
    return str(agent(user_message))