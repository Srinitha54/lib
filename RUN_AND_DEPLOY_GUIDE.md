# Library Reservation System — Step-by-Step Run & Deploy Guide

Follow these in order. Each step assumes the previous one succeeded —
don't skip ahead if something errors, fix it first.

---

## Part 1 — Local Setup

### 1. Unzip and enter the project

```bash
unzip library_reservation_system.zip
cd library_reservation_system
```

### 2. Install `uv` (if you don't have it)

```bash
# Mac / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 3. Create the virtual environment and install base dependencies

```bash
uv venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
uv pip install -e .
```

This installs `strands-agents`, `strands-agents-tools`, and `boto3` — enough
to run the agent locally against real AWS.

### 4. Configure AWS credentials

```bash
aws configure
```

Enter your Access Key ID, Secret Access Key, region (e.g. `us-east-1`), and
output format `json`. (Or export `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`
/ `AWS_DEFAULT_REGION` directly if you don't want to use the CLI config file.)

### 5. Enable Bedrock model access

1. AWS Console → **Amazon Bedrock** → **Model access** (left sidebar)
2. **Manage model access** → enable **Amazon Nova Lite**
3. Save, then wait 1–2 minutes for it to activate

This project defaults to `apac.amazon.nova-lite-v1:0` in `ap-south-1`.
Two things worth understanding about that ID:

- **Nova, not Claude** — Nova is Amazon-native, so unlike Anthropic's
  Claude models it does not require a separate "use case details"
  approval step. Enabling model access in the console is normally enough.
- **The `apac.` prefix is required, not optional, in Mumbai.** Nova Lite
  is not hosted directly in `ap-south-1` as a bare on-demand model —
  Mumbai is only a supported *source* region for Nova's APAC cross-Region
  inference profile. Using the bare ID (`amazon.nova-lite-v1:0`) in this
  region fails with `ValidationException: The provided model identifier
  is invalid` — not a credentials or access problem, just the wrong ID
  shape for this region. The `apac.`-prefixed ID is what actually routes
  correctly.

Also make sure `AWS_DEFAULT_REGION` is actually set in your shell — `aws
configure` writes to a config file, but this project reads the
`AWS_DEFAULT_REGION` **environment variable** directly, so if it isn't
exported the scripts silently fall back to `ap-south-1` (the project
default) rather than whatever you set in `aws configure`. To be explicit:

```bash
export AWS_DEFAULT_REGION="ap-south-1"          # Mac/Linux
$env:AWS_DEFAULT_REGION = "ap-south-1"          # Windows PowerShell
```

---

## Part 2 — Sanity-Check the Code (no AWS needed)

Before touching real AWS, run the mocked test suite — it catches logic bugs
in seconds using an in-memory fake DynamoDB (`moto`), no credentials required.

```bash
uv pip install -e ".[dev]"
pytest -v
```

All tests should pass. If something fails here, fix it before moving on —
it'll be much harder to debug against live AWS calls.

---

## Part 3 — Set Up the Real Database

### 6. Create and seed the DynamoDB tables

```bash
python deployment/init_dynamodb.py
```

This creates 5 tables (`library_members`, `library_books`, `library_authors`,
`library_reservations`, `library_borrowing_history`) and seeds sample data.
Safe to re-run — it skips tables that already exist.

You should see `[OK] Table '...' is now ACTIVE.` for each table and
`[SEEDED] N items inserted into '...'` for the data.

---

## Part 4 — Run and Test Locally

### 7. Start the agent in the terminal

```bash
python main.py --mode sequential
```

or

```bash
python main.py --mode parallel
```

### 8. Walk through the scenarios in `prompts.md`

Try these in order (copy the sample prompts straight from `prompts.md`):

1. **Happy path** — `MEM-1001` reserves `BOOK-2001`, confirm with `YES`
2. **Expired membership** — `MEM-1003` gets stopped before any book check
3. **Book unavailable** — `MEM-1001` tries `BOOK-2003` (already reserved)
4. **Limit reached** — `MEM-1004` is stopped for being at 5/5
5. **Human rejection** — confirm with `NO`, verify nothing was written
6. **Multi-book** — reserve two books in one request (section 6a/6b)
7. **Duplicate re-run** — repeat the same reservation twice, confirm the
   second attempt is rejected cleanly (section 8)

Type `exit` to end the session.

### 9. Verify what actually got written (optional but recommended)

```bash
aws dynamodb scan --table-name library_reservations
aws dynamodb scan --table-name library_books
```

Confirm: exactly one reservation per successful confirm, book statuses
flipped to `RESERVED`, member `active_reservations` incremented correctly.

---

## Part 5 — Deploy to Bedrock AgentCore Runtime

Only do this once local testing above is clean.

### 10. Install the deploy extras

```bash
uv pip install -e ".[deploy]"
```

### 11. Make sure you have a container engine running

The starter toolkit needs Docker, Finch, or Podman locally to build the
deployment artifact (unless you switch it to `direct_code_deploy` mode).
Start Docker Desktop (or equivalent) now if it isn't already running.

### 12. Create the IAM role AgentCore Runtime will assume

AWS Console → **IAM** → **Roles** → **Create role**:
- Trusted entity: AWS service → Bedrock AgentCore
- Attach: `AmazonDynamoDBFullAccess`, `AmazonBedrockFullAccess`
- Name: `BedrockAgentCoreRole`
- Copy the Role ARN, e.g. `arn:aws:iam::123456789012:role/BedrockAgentCoreRole`

### 13. Export the role ARN

```bash
export AGENTCORE_ROLE_ARN="arn:aws:iam::YOUR_ACCOUNT_ID:role/BedrockAgentCoreRole"
```

### 14. Deploy

```bash
python deployment/agentcore_deploy.py --mode sequential
```

Watch the output — it will configure `agentcore_entrypoint.py`, build and
push the artifact, then print an **Agent Runtime ARN**. Save that ARN.

Repeat with `--mode parallel` for the second workflow if your assessment
requires both deployed separately.

### 15. Invoke the deployed agent

```bash
aws bedrock-agentcore invoke-agent-runtime \
  --agent-runtime-arn <ARN_FROM_STEP_14> \
  --runtime-session-id "a-random-string-at-least-33-characters-long" \
  --payload '{"prompt": "I want to reserve book BOOK-2001 for member MEM-1001"}'
```

You should get back a JSON response with the agent's reply.

### 16. Check observability (optional)

AWS Console → CloudWatch → Transaction Search / X-Ray traces, to confirm
tool calls and (for the parallel agent) concurrent tool execution are
actually happening, not just claimed by the prompt.

---

## If Something Breaks

| Symptom | Likely cause | Fix |
|---|---|---|
| `No module named 'strands'` | venv not activated / deps not installed | `source .venv/bin/activate` then `uv pip install -e .` |
| `Unable to locate credentials` | AWS CLI not configured | `aws configure` |
| `AccessDeniedException` calling Bedrock | Model access not enabled | Part 1, Step 5 |
| `ResourceNotFoundException` on DynamoDB calls | Tables not created | `python deployment/init_dynamodb.py` |
| `on-demand throughput isn't supported` | Wrong model ID format | Use `us.`-prefixed inference profile (Part 1, Step 5) |
| `agentcore_deploy.py` fails on ECR/Docker step | No container engine running | Start Docker/Finch/Podman (Part 5, Step 11) |
| `AGENTCORE_ROLE_ARN environment variable is not set` | Forgot Step 13 | Export it, re-run deploy |
| Second reservation attempt for same book "succeeds" unexpectedly | You're testing against stale/mocked data | Re-run `init_dynamodb.py` or check you're pointed at the real table, not the test mocks |
