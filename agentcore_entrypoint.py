"""
agentcore_entrypoint.py
-------------------------
Entry point used when the agent is deployed to Amazon Bedrock AgentCore
Runtime. This is DIFFERENT from main.py (which is for local terminal
testing) — AgentCore Runtime expects an HTTP service built with the
bedrock_agentcore SDK's BedrockAgentCoreApp + @app.entrypoint pattern.

This file is what deployment/agentcore_deploy.py points the AgentCore
starter toolkit at (`agentcore configure --entrypoint agentcore_entrypoint.py`).

WORKFLOW_MODE (sequential | parallel) is read from an environment variable
so the same container image can serve either workflow depending on how
it's configured/deployed.
"""

import os
import re
import sys

print("[DEBUG] agentcore_entrypoint.py starting...", flush=True)

sys.path.insert(0, os.path.dirname(__file__))

print("[DEBUG] importing bedrock_agentcore...", flush=True)
from bedrock_agentcore import BedrockAgentCoreApp
print("[DEBUG] importing agents.orchestrator_agent...", flush=True)
from agents.orchestrator_agent import get_agent
print("[DEBUG] imports OK", flush=True)

app = BedrockAgentCoreApp()
print("[DEBUG] BedrockAgentCoreApp() created", flush=True)

WORKFLOW_MODE = os.getenv("WORKFLOW_MODE", "sequential")
print(f"[DEBUG] WORKFLOW_MODE={WORKFLOW_MODE}", flush=True)

# Created once at import time and reused across warm invocations within
# the same AgentCore Runtime session, same as a normal long-lived service.
agent = get_agent(WORKFLOW_MODE)
print("[DEBUG] agent created OK", flush=True)

# Some models (e.g. Amazon Nova) include their internal reasoning inline
# in the response text, wrapped in <thinking>...</thinking> tags. That's
# useful for debugging but not something an end user should see — strip
# it out before returning the response to the caller.
_THINKING_TAG_RE = re.compile(r"<thinking>.*?</thinking>\s*", re.DOTALL | re.IGNORECASE)


def _strip_thinking(text: str) -> str:
    return _THINKING_TAG_RE.sub("", text).strip()


@app.entrypoint
def invoke(payload: dict) -> dict:
    """
    AgentCore Runtime calls this function for every InvokeAgentRuntime
    request. `payload` is the JSON body the caller sent, e.g.:
        {"prompt": "I want to reserve book BOOK-2001 for member MEM-1001"}

    Returns a JSON-serializable dict; AgentCore streams it back to the caller.
    """
    print(f"[DEBUG] invoke() called with payload={payload}", flush=True)
    user_message = payload.get("prompt", "")
    if not user_message:
        return {"result": "Please provide a 'prompt' field with your message."}

    response = agent(user_message)
    clean_result = _strip_thinking(str(response))
    return {"result": clean_result, "workflow_mode": WORKFLOW_MODE}


if __name__ == "__main__":
    # Lets you run `python agentcore_entrypoint.py` locally to smoke-test
    # the HTTP service the same way AgentCore Runtime will invoke it,
    # before deploying.
    print("[DEBUG] calling app.run() now — should block and start a server...", flush=True)
    try:
        app.run()
    except Exception:
        import traceback
        print("[DEBUG] app.run() raised an exception:", flush=True)
        traceback.print_exc()
        raise
    print("[DEBUG] app.run() returned — this should NOT normally happen while the server is up", flush=True)