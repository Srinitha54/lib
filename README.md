# Library Reservation System
### AWS Track — Strands Agents + Amazon Bedrock + DynamoDB

A multi-agent system that allows library members to reserve books. The agent verifies membership status, checks book availability, calculates due dates, and saves reservations only after user confirmation.

---

## Project Structure

```
library_reservation_system/
│
├── agents/
│   ├── __init__.py
│   └── orchestrator_agent.py   ← The AI agent (sequential + parallel modes)
│
├── tools/
│   ├── __init__.py
│   ├── db.py                   ← All DynamoDB read/write logic (atomic reservation writes)
│   └── library_tools.py        ← @tool functions the agent can call
│
├── deployment/
│   ├── __init__.py
│   ├── init_dynamodb.py        ← Creates tables and seeds sample data
│   └── agentcore_deploy.py     ← Deploys to Bedrock AgentCore Runtime (starter toolkit)
│
├── main.py                     ← Entry point for LOCAL terminal testing
├── agentcore_entrypoint.py     ← Entry point used by AgentCore Runtime (HTTP service)
├── prompts.md                  ← Sample test prompts
├── pyproject.toml              ← Project dependencies (managed by uv)
└── README.md                   ← This file
```

---

## Prerequisites

| Requirement | Details |
|---|---|
| Python | 3.12 or higher |
| uv | Python package manager (faster than pip) |
| AWS Account | With Bedrock model access enabled |
| AWS CLI | Installed and configured |

---

## Step-by-Step Setup

### Step 1 — Install uv (if not already installed)

**Windows (PowerShell):**
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**Mac / Linux:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Step 2 — Create the project folder and copy files

Create a folder called `library_reservation_system` on your computer and place all the project files inside it exactly as shown in the structure above.

### Step 3 — Set up the Python environment

Open a terminal inside the `library_reservation_system` folder, then run:

```bash
uv venv
```

This creates a `.venv` folder. Then activate it:

**Windows:**
```powershell
.venv\Scripts\activate
```

**Mac / Linux:**
```bash
source .venv/bin/activate
```

### Step 4 — Install dependencies

```bash
uv pip install -e .
```

This reads `pyproject.toml` and installs all required packages.

### Step 5 — Configure AWS credentials

**Option A — Using the AWS CLI (recommended):**
```bash
aws configure
```
Enter your:
- AWS Access Key ID
- AWS Secret Access Key
- Default region (e.g., `us-east-1`)
- Default output format: `json`

**Option B — Using environment variables:**
```bash
# Windows PowerShell
$env:AWS_ACCESS_KEY_ID     = "YOUR_ACCESS_KEY"
$env:AWS_SECRET_ACCESS_KEY = "YOUR_SECRET_KEY"
$env:AWS_DEFAULT_REGION    = "us-east-1"

# Mac / Linux
export AWS_ACCESS_KEY_ID="YOUR_ACCESS_KEY"
export AWS_SECRET_ACCESS_KEY="YOUR_SECRET_KEY"
export AWS_DEFAULT_REGION="us-east-1"
```

### Step 6 — Enable Bedrock Model Access

1. Go to AWS Console → Amazon Bedrock
2. Click "Model access" in the left sidebar
3. Click "Manage model access"
4. Enable **Anthropic Claude 3.5 Sonnet**
5. Click "Save changes"

Wait 1–2 minutes for access to activate.

### Step 7 — Initialize the DynamoDB database

```bash
python deployment/init_dynamodb.py
```

This creates 5 DynamoDB tables (members, books, authors, reservations,
borrowing history) and inserts sample data. You only need to run this once.

**Expected output:**
```
STEP 1: Creating tables...
  [CREATE] Creating table 'library_members'...
  [OK] Table 'library_members' is now ACTIVE.
  ...

STEP 2: Seeding sample data...
  [SEEDED] 5 items inserted into 'library_members'.
  [SEEDED] 6 items inserted into 'library_authors'.
  [SEEDED] 6 items inserted into 'library_books'.
  ...
```

### Step 8 — Test locally

**Sequential mode (steps run one at a time):**
```bash
python main.py --mode sequential
```

**Parallel mode (membership + book checks run simultaneously):**
```bash
python main.py --mode parallel
```

Type a prompt like:
```
I want to reserve book BOOK-2001. My member ID is MEM-1001.
```

The agent will walk through all checks and ask you to confirm.

---

## Automated Tests

`tests/` has a pytest suite that mocks DynamoDB in-memory using `moto` —
no AWS account, credentials, or Bedrock access needed to run it. It covers
the highest-risk logic: the atomic reservation transaction (happy path,
book-already-reserved rejection, duplicate-rerun rejection) and the
`confirmed=True` human-in-the-loop gate.

```bash
uv pip install -e ".[dev]"
pytest -v
```

Run this before you attempt a real DynamoDB/Bedrock walkthrough — it
catches logic bugs (bad `ConditionExpression`, wrong attribute types, etc.)
in seconds instead of after waiting on live AWS calls.

---

## Deploying to Bedrock AgentCore

Deployment uses the official `bedrock-agentcore-starter-toolkit`, which
correctly packages the agent (container or direct code deploy) and calls
the AgentCore Runtime control plane on your behalf — you never construct
the artifact by hand.

### Step 1 — Install the deploy extras

```bash
uv pip install -e ".[deploy]"
```

### Step 2 — Create an IAM Role for AgentCore

The runtime needs a role that allows it to:
- Call DynamoDB (the `library_*` tables)
- Call Bedrock (`InvokeModel` on the Claude model)
- Pull from ECR / read from S3, depending on deployment mode

In the AWS Console → IAM → Roles → Create Role:
- Trusted entity: AWS service → Bedrock AgentCore
- Attach policies:
  - `AmazonDynamoDBFullAccess`
  - `AmazonBedrockFullAccess`
  - `AmazonEC2ContainerRegistryReadOnly` — **required**, or `CreateAgentRuntime`
    fails with `ValidationException: Access denied while validating ECR URI`
    (the execution role needs `ecr:GetAuthorizationToken`, `ecr:BatchGetImage`,
    `ecr:GetDownloadUrlForLayer` to pull the built container image)
- Name it: `BedrockAgentCoreRole`

Copy the Role ARN (looks like: `arn:aws:iam::123456789:role/BedrockAgentCoreRole`)

### Step 3 — Set the role ARN as environment variable

```bash
# Windows
$env:AGENTCORE_ROLE_ARN = "arn:aws:iam::YOUR_ACCOUNT_ID:role/BedrockAgentCoreRole"

# Mac / Linux
export AGENTCORE_ROLE_ARN="arn:aws:iam::YOUR_ACCOUNT_ID:role/BedrockAgentCoreRole"
```

### Step 4 — Deploy

```bash
python deployment/agentcore_deploy.py --mode sequential
python deployment/agentcore_deploy.py --mode parallel
```

This configures and launches `agentcore_entrypoint.py` (the AgentCore
Runtime HTTP entrypoint — separate from `main.py`, which is only for local
terminal testing) and prints the resulting Agent Runtime ARN.

### Step 5 — Invoke the deployed agent

Easiest path — use the included helper script, which uses the toolkit's own
`Runtime.invoke()` instead of wrestling with the AWS CLI's base64 payload
encoding for `invoke-agent-runtime`:

```bash
python deployment/invoke_agent.py --mode sequential --prompt "I want to reserve book BOOK-2001 for member MEM-1001"
```

Or via the AWS CLI directly if you prefer:

```bash
aws bedrock-agentcore invoke-agent-runtime \
  --agent-runtime-arn <ARN_FROM_STEP_4> \
  --runtime-session-id <a session id, 33+ characters> \
  --payload '{"prompt": "I want to reserve book BOOK-2001 for member MEM-1001"}' \
  --cli-binary-format raw-in-base64-out \
  response.json
```

---

## Sample Members for Testing

| Member ID | Name | Tier | Status |
|---|---|---|---|
| MEM-1001 | Alice Johnson | Standard | Valid |
| MEM-1002 | Bob Smith | Premium | Valid |
| MEM-1003 | Carol White | Standard | **EXPIRED** |
| MEM-1004 | David Brown | Premium | Valid, **AT LIMIT** |
| MEM-1005 | Eve Davis | Standard | Valid |

## Sample Books for Testing

| Book ID | Title | Status |
|---|---|---|
| BOOK-2001 | The Great Gatsby | Available |
| BOOK-2002 | To Kill a Mockingbird | Available |
| BOOK-2003 | 1984 | **Reserved** |
| BOOK-2004 | Pride and Prejudice | Available |
| BOOK-2005 | The Hobbit | Available |
| BOOK-2006 | Dune | Available |

## Sample Authors for Testing

| Author ID | Name |
|---|---|
| AUTH-001 | F. Scott Fitzgerald |
| AUTH-002 | Harper Lee |
| AUTH-003 | George Orwell |
| AUTH-004 | Jane Austen |
| AUTH-005 | J.R.R. Tolkien |
| AUTH-006 | Frank Herbert |

Each book in `library_books` carries an `author_id` pointing here, plus a
denormalized `author` display field so tools don't need a join for the
common case. Use `get_author_details` when you want bio/nationality info.

---

## How It Works

### Architecture

```
User Message
     │
     ▼
Strands Agent (orchestrator_agent.py)
     │  reads system prompt + decides which tools to call
     │
     ├── lookup_member()              ─┐
     ├── check_membership_status()     │  Tools call DynamoDB
     ├── check_book_availability()     │  via tools/db.py
     ├── check_reservation_eligibility()│
     ├── calculate_reservation_due_date()
     │
     ▼
Agent presents summary → asks user YES/NO
     │
     ├── YES → submit_reservation(confirmed=True) → atomic DynamoDB transaction
     └── NO  → cancels, nothing written
```

**Confirmation is enforced in code, not just in the prompt.** `submit_reservation`
takes a required `confirmed: bool` argument; if it's not explicitly `True`,
the tool refuses and returns an error instead of writing anything. This
means even if the model misreads an ambiguous reply, the write is blocked
at the tool boundary — not just discouraged by the system prompt.

**Reservation writes are atomic.** Writing the reservation record, flipping
the book's status to RESERVED, and incrementing the member's active count
all happen in a single DynamoDB `TransactWriteItems` call. If the book was
already reserved (a race, or the exact same request re-firing), the whole
transaction is rejected — no partial writes and no duplicate reservation
records.

### Sequential vs Parallel

**Sequential:** Each tool call waits for the previous one to finish.
```
lookup → check membership → check book → check eligibility → calculate date → confirm → save
```

**Parallel:** Membership and book availability checks run at the same time.
```
lookup → [check membership + check book] → check eligibility → calculate date → confirm → save
```

---

## Troubleshooting

**"No module named 'strands'"**
→ Make sure you activated the virtual environment and ran `uv pip install -e .`

**"Unable to locate credentials"**
→ Run `aws configure` or set the environment variables.

**"Access denied to Bedrock"**
→ Enable model access in the AWS Bedrock console (Step 6 above).

**"ResourceNotFoundException" for DynamoDB**
→ Run `python deployment/init_dynamodb.py` first.

**"Invocation of model ID ... with on-demand throughput isn't supported"**
→ Some Claude models on Bedrock require a cross-region inference profile ID
instead of the base model ID, e.g. `us.anthropic.claude-3-5-sonnet-20241022-v2:0`
rather than `anthropic.claude-3-5-sonnet-20241022-v2:0`. If you hit this,
set `BEDROCK_MODEL_ID` to the `us.`-prefixed inference profile ID for your
region.

**AgentCore deploy fails with an ECR/Docker error**
→ Make sure Docker, Finch, or Podman is running locally — the starter
toolkit needs a container engine to build the deployment artifact unless
you configure `direct_code_deploy` mode instead.

**`Runtime.configure() got an unexpected keyword argument 'environment_variables'`**
→ Fixed in the current `agentcore_deploy.py`: environment variables are
passed to `runtime.launch(env_vars=...)`, not `runtime.configure(...)`.
If you see this, you're on an older copy of the script — re-download it.

**`ValidationException: Access denied while validating ECR URI ...`**
→ Your `BedrockAgentCoreRole` execution role is missing ECR pull permissions.
Attach `AmazonEC2ContainerRegistryReadOnly`:
```bash
aws iam attach-role-policy --role-name BedrockAgentCoreRole --policy-arn arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly
```
Wait a few seconds for IAM propagation, then re-run the deploy command.

**Invoking the deployed agent returns `RuntimeClientError: Received error (500) from runtime`**
→ Check the actual traceback in CloudWatch first:
```bash
aws logs tail /aws/bedrock-agentcore/runtimes/<your-runtime-id>-DEFAULT --since 20m --region <your-region>
```
A common cause: Anthropic Claude models on Bedrock require a **one-time
EULA/marketplace subscription per AWS account** — separate from the
`AmazonBedrockFullAccess` IAM policy. If Amazon Nova models work but Claude
doesn't, that's almost certainly it. Fix in AWS Console → Bedrock → Model
catalog → open the Claude model → accept the EULA/request access, or switch
`BEDROCK_MODEL_ID` to an Amazon Nova model (e.g. `apac.amazon.nova-lite-v1:0`
for `ap-south-1` — check `aws bedrock list-inference-profiles --region
<your-region>` for what's available to you), which doesn't require this step.
Note: **the assessment brief specifies Claude** as the LLM, so a Nova-only
deployment may not match spec if this is being graded — treat it as a
workaround for testing, not necessarily the final submission choice.

Also always set `BEDROCK_MODEL_ID` explicitly before deploying — a bare
model ID (no region prefix) commonly fails with "on-demand throughput isn't
supported" in most regions; you need an inference profile ID instead
(`us.`/`apac.`/`eu.`/`global.` prefix depending on your region).