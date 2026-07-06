"""
agents/human_review.py
------------------------
A small, focused agent whose ONLY job is to classify whether a user's
message is a clear confirmation, a clear rejection, or something
ambiguous — used by the orchestrator to disambiguate short replies like
"yes" before delegating to the sequential/parallel workflow agent.

WHY THIS IS ITS OWN AGENT (not just a regex check):
Real user replies aren't always a bare "yes" — "sure, go ahead", "nah I
changed my mind", "wait actually no" all need to be understood, not
pattern-matched. Keeping this as a small, separately-defined agent with a
narrow responsibility is a genuine multi-agent decomposition: the
reservation-logic agent (sequential/parallel) stays focused purely on
library business rules, and this agent's only expertise is intent
classification of confirmation replies.

This agent has NO tools and NO persistent memory of its own — it's a
pure, stateless classifier created fresh each call with just the text it
needs to judge, so it can never itself book or cancel anything. The
actual confirmed=True gate still lives entirely in library_tools.py,
completely unchanged by this agent's existence.
"""

from strands import Agent, tool
from agents.model_config import bedrock_model

REVIEW_SYSTEM_PROMPT = """
You are a confirmation-intent classifier for a library reservation system.

You will be given a single user message that was sent in reply to a
yes/no confirmation question (e.g. "Would you like to confirm this
reservation? (YES / NO)" or "Are you sure you want to cancel? (YES / NO)").

Classify the message as EXACTLY ONE of these three words, and output
NOTHING else — no punctuation, no explanation, just the single word:

CONFIRMED   - the message is a clear affirmative (e.g. "yes", "YES",
              "confirm", "go ahead", "sure, do it", "yep that's right")
REJECTED    - the message is a clear negative (e.g. "no", "cancel that",
              "don't", "actually no", "nevermind")
UNCLEAR     - anything else: a new unrelated request, a question, a
              partial answer, or genuine ambiguity. When in doubt,
              choose UNCLEAR rather than guessing.
"""


def _create_review_agent() -> Agent:
    """
    A stateless, tool-less classifier agent — created fresh on every
    call (unlike the workflow agents, which are singletons) since it
    must never carry memory of past confirmations between unrelated
    reservation requests.
    """
    return Agent(
        model=bedrock_model,
        system_prompt=REVIEW_SYSTEM_PROMPT,
        tools=[],
    )


@tool
def review_human_response(user_message: str) -> dict:
    """
    Classify a user's reply to a pending YES/NO confirmation question.

    Use this when the user's message is short and could plausibly be a
    reply to a confirmation that was just asked for — e.g. "yes", "no",
    "yeah do it", "wait no". Do NOT use this for a user's first, original
    request (e.g. "I want to reserve BOOK-2001") — only for replies to a
    confirmation prompt.

    Args:
        user_message: The user's raw reply text.

    Returns a dict: {"verdict": "CONFIRMED" | "REJECTED" | "UNCLEAR"}
    """
    agent = _create_review_agent()
    raw = str(agent(user_message)).strip().upper()

    if "CONFIRMED" in raw:
        verdict = "CONFIRMED"
    elif "REJECTED" in raw:
        verdict = "REJECTED"
    else:
        # Safe default: never auto-confirm on an unparseable response.
        verdict = "UNCLEAR"

    return {"verdict": verdict}