"""
deployment/init_dynamodb.py
----------------------------
Creates all required DynamoDB tables and seeds them with sample data.

HOW TO RUN:
  python deployment/init_dynamodb.py

WHAT IT DOES:
  1. Creates 5 tables: library_members, library_books, library_authors,
     library_reservations, library_borrowing_history
  2. Waits for all tables to be ACTIVE
  3. Seeds sample members, authors, books, and borrowing history data
  4. Prints a summary at the end

Run this ONCE before testing the agent. Safe to re-run — it skips existing tables.
"""

import boto3
import time
import os
from datetime import datetime, timedelta

AWS_REGION = os.getenv("AWS_DEFAULT_REGION", "ap-south-1")
dynamodb    = boto3.resource("dynamodb", region_name=AWS_REGION)
client      = boto3.client("dynamodb", region_name=AWS_REGION)


# ─────────────────────────────────────────────
# TABLE DEFINITIONS
# ─────────────────────────────────────────────

TABLES = [
    {
        "TableName": "library_members",
        "KeySchema": [{"AttributeName": "member_id", "KeyType": "HASH"}],
        "AttributeDefinitions": [{"AttributeName": "member_id", "AttributeType": "S"}],
        "BillingMode": "PAY_PER_REQUEST",
    },
    {
        "TableName": "library_books",
        "KeySchema": [{"AttributeName": "book_id", "KeyType": "HASH"}],
        "AttributeDefinitions": [{"AttributeName": "book_id", "AttributeType": "S"}],
        "BillingMode": "PAY_PER_REQUEST",
    },
    {
        "TableName": "library_authors",
        "KeySchema": [{"AttributeName": "author_id", "KeyType": "HASH"}],
        "AttributeDefinitions": [{"AttributeName": "author_id", "AttributeType": "S"}],
        "BillingMode": "PAY_PER_REQUEST",
    },
    {
        "TableName": "library_reservations",
        "KeySchema": [{"AttributeName": "reservation_id", "KeyType": "HASH"}],
        "AttributeDefinitions": [{"AttributeName": "reservation_id", "AttributeType": "S"}],
        "BillingMode": "PAY_PER_REQUEST",
    },
    {
        "TableName": "library_borrowing_history",
        "KeySchema": [
            {"AttributeName": "member_id", "KeyType": "HASH"},
            {"AttributeName": "record_id",  "KeyType": "RANGE"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "member_id", "AttributeType": "S"},
            {"AttributeName": "record_id",  "AttributeType": "S"},
        ],
        "BillingMode": "PAY_PER_REQUEST",
    },
]


# ─────────────────────────────────────────────
# SAMPLE DATA
# ─────────────────────────────────────────────

# Members: 2 standard, 2 premium, 1 expired
MEMBERS = [
    {
        "member_id": "MEM-1001",
        "name": "Alice Johnson",
        "email": "alice@example.com",
        "tier": "standard",
        "expiry_date": str((datetime.today() + timedelta(days=180)).date()),  # valid
        "active_reservations": 0,
    },
    {
        "member_id": "MEM-1002",
        "name": "Bob Smith",
        "email": "bob@example.com",
        "tier": "premium",
        "expiry_date": str((datetime.today() + timedelta(days=365)).date()),  # valid
        "active_reservations": 1,
    },
    {
        "member_id": "MEM-1003",
        "name": "Carol White",
        "email": "carol@example.com",
        "tier": "standard",
        "expiry_date": "2025-01-01",  # EXPIRED
        "active_reservations": 0,
    },
    {
        "member_id": "MEM-1004",
        "name": "David Brown",
        "email": "david@example.com",
        "tier": "premium",
        "expiry_date": str((datetime.today() + timedelta(days=90)).date()),  # valid
        "active_reservations": 5,  # AT LIMIT — reservation limit reached
    },
    {
        "member_id": "MEM-1005",
        "name": "Eve Davis",
        "email": "eve@example.com",
        "tier": "standard",
        "expiry_date": str((datetime.today() + timedelta(days=60)).date()),  # valid
        "active_reservations": 0,
    },
]

# Authors: one record per author, referenced from books via author_id
AUTHORS = [
    {
        "author_id": "AUTH-001",
        "name": "F. Scott Fitzgerald",
        "nationality": "American",
        "birth_year": 1896,
        "bio": "American novelist, widely regarded as one of the greatest writers of the 20th century.",
    },
    {
        "author_id": "AUTH-002",
        "name": "Harper Lee",
        "nationality": "American",
        "birth_year": 1926,
        "bio": "American novelist best known for 'To Kill a Mockingbird'.",
    },
    {
        "author_id": "AUTH-003",
        "name": "George Orwell",
        "nationality": "British",
        "birth_year": 1903,
        "bio": "English novelist and essayist known for dystopian and political fiction.",
    },
    {
        "author_id": "AUTH-004",
        "name": "Jane Austen",
        "nationality": "British",
        "birth_year": 1775,
        "bio": "English novelist known for romantic fiction with social commentary.",
    },
    {
        "author_id": "AUTH-005",
        "name": "J.R.R. Tolkien",
        "nationality": "British",
        "birth_year": 1892,
        "bio": "English writer and philologist, author of 'The Hobbit' and 'The Lord of the Rings'.",
    },
    {
        "author_id": "AUTH-006",
        "name": "Frank Herbert",
        "nationality": "American",
        "birth_year": 1920,
        "bio": "American science fiction author best known for 'Dune'.",
    },
]

# Books: mix of available and reserved. `author_id` links to library_authors;
# `author` is kept as a denormalized display field so tools don't need a join
# for the common case.
BOOKS = [
    {
        "book_id": "BOOK-2001",
        "title": "The Great Gatsby",
        "author": "F. Scott Fitzgerald",
        "author_id": "AUTH-001",
        "genre": "Classic Fiction",
        "isbn": "978-0-7432-7356-5",
        "status": "AVAILABLE",
    },
    {
        "book_id": "BOOK-2002",
        "title": "To Kill a Mockingbird",
        "author": "Harper Lee",
        "author_id": "AUTH-002",
        "genre": "Classic Fiction",
        "isbn": "978-0-06-112008-4",
        "status": "AVAILABLE",
    },
    {
        "book_id": "BOOK-2003",
        "title": "1984",
        "author": "George Orwell",
        "author_id": "AUTH-003",
        "genre": "Dystopian Fiction",
        "isbn": "978-0-452-28423-4",
        "status": "RESERVED",  # already taken
    },
    {
        "book_id": "BOOK-2004",
        "title": "Pride and Prejudice",
        "author": "Jane Austen",
        "author_id": "AUTH-004",
        "genre": "Romance",
        "isbn": "978-0-14-143951-8",
        "status": "AVAILABLE",
    },
    {
        "book_id": "BOOK-2005",
        "title": "The Hobbit",
        "author": "J.R.R. Tolkien",
        "author_id": "AUTH-005",
        "genre": "Fantasy",
        "isbn": "978-0-618-00221-4",
        "status": "AVAILABLE",
    },
    {
        "book_id": "BOOK-2006",
        "title": "Dune",
        "author": "Frank Herbert",
        "author_id": "AUTH-006",
        "genre": "Science Fiction",
        "isbn": "978-0-441-17271-9",
        "status": "AVAILABLE",
    },
]

# Borrowing history (past records for MEM-1002)
HISTORY = [
    {
        "member_id": "MEM-1002",
        "record_id": "HIST-001",
        "book_id": "BOOK-2003",
        "title": "1984",
        "action": "BORROWED",
        "date": str((datetime.today() - timedelta(days=45)).date()),
        "due_date": str((datetime.today() + timedelta(days=15)).date()),
        "status": "RESERVED",
    },
    {
        "member_id": "MEM-1001",
        "record_id": "HIST-002",
        "book_id": "BOOK-2005",
        "title": "The Hobbit",
        "action": "RETURNED",
        "date": str((datetime.today() - timedelta(days=20)).date()),
        "due_date": str((datetime.today() - timedelta(days=6)).date()),
        "status": "RETURNED",
    },
]

# Reservations: must stay consistent with BOOKS (status=RESERVED) and
# MEMBERS (active_reservations counter). BOOK-2003 is seeded as RESERVED
# and MEM-1002's active_reservations is seeded as 1 — this record is what
# actually backs that state, so get_active_reservations_list("MEM-1002")
# and check_reservation_eligibility both agree with the seeded counters
# instead of showing 0 active reservations for a member whose profile
# claims 1.
RESERVATIONS = [
    {
        "reservation_id":   "RES-MEM-1002-BOOK-2003",
        "member_id":        "MEM-1002",
        "book_id":          "BOOK-2003",
        "status":           "RESERVED",
        "reservation_date": str((datetime.today() - timedelta(days=45)).date()),
        "due_date":         str((datetime.today() + timedelta(days=15)).date()),
    },
]


# ─────────────────────────────────────────────
# HELPER FUNCTIONS
# ─────────────────────────────────────────────

def table_exists(table_name: str) -> bool:
    """Check if a DynamoDB table already exists."""
    try:
        client.describe_table(TableName=table_name)
        return True
    except client.exceptions.ResourceNotFoundException:
        return False


def create_table_if_not_exists(table_def: dict):
    """Create a table if it doesn't exist, then wait for it to be ACTIVE."""
    name = table_def["TableName"]
    if table_exists(name):
        print(f"  [SKIP] Table '{name}' already exists.")
        return

    print(f"  [CREATE] Creating table '{name}'...")
    dynamodb.create_table(**table_def)

    # Wait until the table is ACTIVE (usually 5–15 seconds)
    table = dynamodb.Table(name)
    table.wait_until_exists()
    print(f"  [OK] Table '{name}' is now ACTIVE.")


def seed_table(table_name: str, items: list):
    """Insert sample items into a table using batch_writer for efficiency."""
    table = dynamodb.Table(table_name)
    with table.batch_writer() as batch:
        for item in items:
            batch.put_item(Item=item)
    print(f"  [SEEDED] {len(items)} items inserted into '{table_name}'.")


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    print()
    print("=" * 55)
    print("  Library System — DynamoDB Initialization")
    print("=" * 55)
    print()

    # Step 1: Create all tables
    print("STEP 1: Creating tables...")
    for table_def in TABLES:
        create_table_if_not_exists(table_def)
    print()

    # Step 2: Seed data
    print("STEP 2: Seeding sample data...")
    seed_table("library_members",          MEMBERS)
    seed_table("library_authors",          AUTHORS)
    seed_table("library_books",            BOOKS)
    seed_table("library_reservations",     RESERVATIONS)
    seed_table("library_borrowing_history", HISTORY)
    print()

    # Step 3: Summary
    print("=" * 55)
    print("  DONE! Database is ready for testing.")
    print()
    print("  Sample Members:")
    print("    MEM-1001  Alice Johnson   (standard, VALID)")
    print("    MEM-1002  Bob Smith       (premium,  VALID, 1 active)")
    print("    MEM-1003  Carol White     (standard, EXPIRED)")
    print("    MEM-1004  David Brown     (premium,  VALID, AT LIMIT)")
    print("    MEM-1005  Eve Davis       (standard, VALID)")
    print()
    print("  Sample Books:")
    print("    BOOK-2001  The Great Gatsby       (AVAILABLE)")
    print("    BOOK-2002  To Kill a Mockingbird  (AVAILABLE)")
    print("    BOOK-2003  1984                   (RESERVED - taken)")
    print("    BOOK-2004  Pride and Prejudice    (AVAILABLE)")
    print("    BOOK-2005  The Hobbit             (AVAILABLE)")
    print("    BOOK-2006  Dune                   (AVAILABLE)")
    print()
    print("  Sample Authors:")
    print("    AUTH-001..006  (F. Scott Fitzgerald, Harper Lee, George Orwell,")
    print("                    Jane Austen, J.R.R. Tolkien, Frank Herbert)")
    print()
    print("  Sample Reservations:")
    print("    RES-MEM-1002-BOOK-2003  (Bob Smith / 1984, matches his")
    print("                             active_reservations=1 counter)")
    print()
    print("  NOTE: Re-running this script RESETS all seeded records back to")
    print("  these defaults (e.g. BOOK-2001 back to AVAILABLE if a prior test")
    print("  run reserved it) — safe to re-run before every demo/test pass.")
    print("  It does NOT delete extra reservation records your own testing")
    print("  created beyond this seed set; for a fully clean slate, delete")
    print("  and recreate the tables instead.")
    print("=" * 55)
    print()


if __name__ == "__main__":
    main()