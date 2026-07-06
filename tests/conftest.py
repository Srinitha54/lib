"""
tests/conftest.py
-------------------
Shared pytest fixtures. Spins up an in-memory mock of DynamoDB (via `moto`)
with the exact same table schema deployment/init_dynamodb.py creates, so
tools/db.py can be exercised with zero AWS account/credentials required.

Run with:
    uv pip install -e ".[dev]"
    pytest
"""

import os
import sys
import boto3
import pytest
from moto import mock_aws

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Force these for every test run, regardless of what's already set in the
# shell (e.g. AWS_DEFAULT_REGION=ap-south-1 exported for the live agent).
# Tests must be hermetic: moto's mock is region-scoped, so if tools/db.py
# picks up a different region than this fixture creates tables in, every
# lookup fails with ResourceNotFoundException even though everything is
# "working" — it's just looking in an empty region.
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")


@pytest.fixture
def dynamo_tables():
    """
    Starts a mocked DynamoDB, creates the 5 library_* tables, and tears
    everything down automatically when the test finishes.
    """
    with mock_aws():
        client = boto3.client("dynamodb", region_name="us-east-1")

        client.create_table(
            TableName="library_members",
            KeySchema=[{"AttributeName": "member_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "member_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        client.create_table(
            TableName="library_books",
            KeySchema=[{"AttributeName": "book_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "book_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        client.create_table(
            TableName="library_authors",
            KeySchema=[{"AttributeName": "author_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "author_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        client.create_table(
            TableName="library_reservations",
            KeySchema=[{"AttributeName": "reservation_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "reservation_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        client.create_table(
            TableName="library_borrowing_history",
            KeySchema=[
                {"AttributeName": "member_id", "KeyType": "HASH"},
                {"AttributeName": "record_id", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "member_id", "AttributeType": "S"},
                {"AttributeName": "record_id", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # tools/db.py builds its Table/Client references at import time, so
        # it must be imported only *after* mock_aws() is active and the
        # tables exist. Re-import fresh each test to avoid stale handles
        # bleeding between tests.
        for mod in ("tools.db", "tools.library_tools"):
            sys.modules.pop(mod, None)
        import tools.db as db

        resource = boto3.resource("dynamodb", region_name="us-east-1")
        resource.Table("library_members").put_item(Item={
            "member_id": "MEM-1001", "name": "Alice Johnson", "tier": "standard",
            "expiry_date": "2099-01-01", "active_reservations": 0,
        })
        resource.Table("library_members").put_item(Item={
            "member_id": "MEM-1004", "name": "David Brown", "tier": "premium",
            "expiry_date": "2099-01-01", "active_reservations": 5,
        })
        resource.Table("library_books").put_item(Item={
            "book_id": "BOOK-2001", "title": "The Great Gatsby",
            "author": "F. Scott Fitzgerald", "author_id": "AUTH-001",
            "status": "AVAILABLE",
        })
        resource.Table("library_authors").put_item(Item={
            "author_id": "AUTH-001", "name": "F. Scott Fitzgerald",
        })

        yield db
