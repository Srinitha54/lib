"""
deployment/agentcore_deploy.py
-------------------------------
Deploys the Library Reservation Agent to Amazon Bedrock AgentCore Runtime
using the official `bedrock-agentcore-starter-toolkit`.

WHY THE STARTER TOOLKIT (and not raw boto3 create_agent_runtime calls):
  AgentCore Runtime's CreateAgentRuntime API requires an artifact that is
  either:
    (a) a container image already pushed to ECR, or
    (b) a code package already uploaded to S3 (codeConfiguration).
  It does NOT accept an arbitrary local zip file directly. The starter
  toolkit's `configure()` + `launch()` handle building/pushing the
  container (or packaging + uploading code) and calling the control-plane
  API correctly, so you don't have to hand-roll ECR/S3 plumbing here.

HOW TO RUN:
  pip install bedrock-agentcore bedrock-agentcore-starter-toolkit --break-system-packages
  python deployment/agentcore_deploy.py --mode sequential
  python deployment/agentcore_deploy.py --mode parallel

PREREQUISITES:
  - AWS CLI configured with sufficient IAM permissions
  - Bedrock model access enabled in your AWS account
  - DynamoDB tables already created (run deployment/init_dynamodb.py first)
  - Docker, Finch, or Podman installed locally (only needed if the toolkit
    falls back to container-based deploy instead of direct code deploy)

WHAT THIS DOES:
  1. Points the toolkit at agentcore_entrypoint.py (the BedrockAgentCoreApp
     HTTP service — see that file for details)
  2. Configures an agent named library-reservation-<mode>
  3. Launches it to Bedrock AgentCore Runtime (builds/pushes the artifact
     and calls CreateAgentRuntime under the hood)
  4. Prints the resulting Agent Runtime ARN you can use to invoke it
"""

import argparse
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

AWS_REGION = os.getenv("AWS_DEFAULT_REGION", "ap-south-1")
MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "apac.amazon.nova-lite-v1:0")

# The IAM role AgentCore Runtime assumes at execution time.
# It needs: DynamoDB read/write on the library_* tables, and
# bedrock:InvokeModel on whichever model BEDROCK_MODEL_ID points to.
RUNTIME_ROLE_ARN = os.getenv("AGENTCORE_ROLE_ARN")


def write_requirements_txt():
    """
    The starter toolkit needs a requirements.txt at the project root to
    build the deployment artifact — it doesn't read pyproject.toml.
    """
    req_path = os.path.join(PROJECT_ROOT, "requirements.txt")
    requirements = [
        "strands-agents>=0.1.0",
        "strands-agents-tools>=0.1.0",
        "bedrock-agentcore>=0.1.0",
        "boto3>=1.34.0",
    ]
    with open(req_path, "w") as f:
        f.write("\n".join(requirements) + "\n")
    print(f"  [OK] Wrote {req_path}")
    return req_path


def deploy(workflow_mode: str):
    try:
        from bedrock_agentcore_starter_toolkit import Runtime
    except ImportError:
        print("  [ERROR] bedrock-agentcore-starter-toolkit is not installed.")
        print("  Run: pip install bedrock-agentcore-starter-toolkit --break-system-packages")
        sys.exit(1)

    if not RUNTIME_ROLE_ARN:
        print("  [ERROR] AGENTCORE_ROLE_ARN environment variable is not set.")
        print("  Set it to the IAM role AgentCore Runtime should assume, e.g.:")
        print("    export AGENTCORE_ROLE_ARN=arn:aws:iam::<ACCOUNT_ID>:role/BedrockAgentCoreRole")
        sys.exit(1)

    agent_name = f"library_reservation_{workflow_mode}"
    req_path = write_requirements_txt()

    print()
    print(f"  Deploying '{agent_name}' to Bedrock AgentCore Runtime...")
    print(f"  Region: {AWS_REGION}")
    print(f"  Entrypoint: agentcore_entrypoint.py (WORKFLOW_MODE={workflow_mode})")
    print()

    runtime = Runtime()

    print("STEP 1: Configuring agent...")
    runtime.configure(
        entrypoint="agentcore_entrypoint.py",
        agent_name=agent_name,
        requirements_file=req_path,
        execution_role=RUNTIME_ROLE_ARN,
        region=AWS_REGION,
        auto_create_ecr=True,
    )

    # Environment variables are passed at launch time, not configure time.
    env_vars = {
        "WORKFLOW_MODE": workflow_mode,
        "AWS_DEFAULT_REGION": AWS_REGION,
        "BEDROCK_MODEL_ID": MODEL_ID,
    }

    print("\nSTEP 2: Launching to AgentCore Runtime (this builds/pushes the artifact)...")
    # auto_update_on_conflict=True: if an agent with this name already
    # exists in AWS (common after deleting the local .bedrock_agentcore.yaml,
    # or when re-deploying from a different machine/session), update it in
    # place instead of erroring out trying to create a duplicate.
    launch_result = runtime.launch(env_vars=env_vars, auto_update_on_conflict=True)

    def _extract(result, *keys):
        for key in keys:
            if isinstance(result, dict) and key in result:
                return result[key]
            if hasattr(result, key):
                return getattr(result, key)
        return None

    runtime_arn = _extract(launch_result, "agent_arn", "agent_runtime_arn")

    print()
    print("=" * 55)
    if runtime_arn:
        print("  DEPLOYMENT COMPLETE!")
        print(f"  Mode: {workflow_mode}")
        print(f"  Agent Runtime ARN: {runtime_arn}")
        print()
        print("  Invoke it with:")
        print("    aws bedrock-agentcore invoke-agent-runtime \\")
        print(f"      --agent-runtime-arn {runtime_arn} \\")
        print("      --runtime-session-id <33+ char session id> \\")
        print('      --payload \'{"prompt": "I want to reserve book BOOK-2001 for member MEM-1001"}\'')
    else:
        print("  Deployment finished but no ARN was returned — check the toolkit output above.")
    print("=" * 55)
    print()


def main():
    parser = argparse.ArgumentParser(description="Deploy to Bedrock AgentCore Runtime")
    parser.add_argument("--mode", choices=["sequential", "parallel"],
                         default="sequential", help="Workflow mode")
    args = parser.parse_args()

    print()
    print("=" * 55)
    print(f"  AgentCore Deployment — {args.mode.upper()} mode")
    print("=" * 55)

    deploy(args.mode)


if __name__ == "__main__":
    main()