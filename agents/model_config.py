"""
agents/model_config.py
------------------------
Shared Bedrock model configuration used by every agent in this project
(orchestrator, sequential, parallel, human_review). Centralized here so
all agents always use the exact same model/region, and the region /
inference-profile gotcha is documented in exactly one place instead of
being duplicated across four files.
"""

import os
from strands.models import BedrockModel

# We use Amazon Bedrock with Amazon Nova Lite. Nova Lite is not hosted
# directly in ap-south-1 (Mumbai) as an on-demand model — Mumbai is only
# a supported *source* region for Nova's APAC cross-Region inference
# profile, so the "apac." prefix is required here (a bare
# "amazon.nova-lite-v1:0" will fail with "provided model identifier is
# invalid" in this region). See:
# https://docs.aws.amazon.com/bedrock/latest/userguide/inference-profiles-support.html
AWS_REGION = os.getenv("AWS_DEFAULT_REGION", "ap-south-1")
MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "apac.amazon.nova-lite-v1:0")

# A single shared model instance — Python only executes this module once
# regardless of how many agent files import from it, so all four agents
# reuse the same client rather than each creating their own.
bedrock_model = BedrockModel(
    model_id=MODEL_ID,
    region_name=AWS_REGION,
)