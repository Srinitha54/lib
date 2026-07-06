"""
deployment/invoke_agent.py
----------------------------
Invokes an already-deployed AgentCore Runtime agent. Simpler than the raw
`aws bedrock-agentcore invoke-agent-runtime` CLI command, which requires
base64-encoding the payload yourself — the starter toolkit's Runtime.invoke()
handles that for you.

USAGE:
    python deployment/invoke_agent.py --mode sequential --prompt "I want to reserve book BOOK-2001 for member MEM-1001"

This re-runs configure() against the same agent_name (cheap, no rebuild)
so the toolkit knows which deployed runtime to talk to, then calls invoke().
"""

import argparse
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

AWS_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
RUNTIME_ROLE_ARN = os.getenv("AGENTCORE_ROLE_ARN")


def main():
    parser = argparse.ArgumentParser(description="Invoke a deployed AgentCore Runtime agent")
    parser.add_argument("--mode", choices=["sequential", "parallel"], default="sequential")
    parser.add_argument("--prompt", required=True, help="The message to send to the agent")
    args = parser.parse_args()

    if not RUNTIME_ROLE_ARN:
        print("  [ERROR] AGENTCORE_ROLE_ARN environment variable is not set.")
        print("  Set it to the same role ARN you used to deploy, e.g.:")
        print("    $env:AGENTCORE_ROLE_ARN = \"arn:aws:iam::YOUR_ACCOUNT_ID:role/BedrockAgentCoreRole\"")
        sys.exit(1)

    try:
        from bedrock_agentcore_starter_toolkit import Runtime
    except ImportError:
        print("  [ERROR] bedrock-agentcore-starter-toolkit is not installed.")
        print("  Run: pip install bedrock-agentcore-starter-toolkit --break-system-packages")
        sys.exit(1)

    agent_name = f"library_reservation_{args.mode}"
    runtime = Runtime()

    # Re-attaches to the already-deployed agent by name/region — this does
    # NOT redeploy or rebuild anything, it just loads the existing
    # .bedrock_agentcore.yaml config so invoke() knows the target ARN.
    # execution_role must match what was used at deploy time (the toolkit
    # requires it be passed even when just reattaching to existing config).
    runtime.configure(
        entrypoint="agentcore_entrypoint.py",
        agent_name=agent_name,
        region=AWS_REGION,
        execution_role=RUNTIME_ROLE_ARN,
    )

    print(f"Invoking '{agent_name}'...")
    response = runtime.invoke({"prompt": args.prompt})
    print()
    print("Response:")
    print(response)


if __name__ == "__main__":
    main()