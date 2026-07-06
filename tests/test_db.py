"""
tests/test_db.py
------------------
Exercises the atomic reservation write in tools/db.py against a mocked
DynamoDB. This is the highest-risk piece of the rewrite (TransactWriteItems
with low-level typed values + ConditionExpressions), so it gets the most
direct coverage.
"""

import pytest


def test_create_reservation_happy_path(dynamo_tables):
    db = dynamo_tables

    reservation = db.create_reservation("MEM-1001", "BOOK-2001", "2026-07-15")

    assert reservation["reservation_id"] == "RES-MEM-1001-BOOK-2001"
    assert reservation["status"] == "RESERVED"

    # Book should now be RESERVED
    book = db.get_book("BOOK-2001")
    assert book["status"] == "RESERVED"

    # Member's active_reservations should have incremented from 0 -> 1
    member = db.get_member("MEM-1001")
    assert int(member["active_reservations"]) == 1

    # The reservation record itself should exist and be readable
    active = db.get_active_reservations("MEM-1001")
    assert len(active) == 1
    assert active[0]["book_id"] == "BOOK-2001"


def test_create_reservation_rejects_unavailable_book(dynamo_tables):
    db = dynamo_tables

    # First reservation succeeds and flips the book to RESERVED
    db.create_reservation("MEM-1001", "BOOK-2001", "2026-07-15")

    # A different member trying to grab the same (now-reserved) book
    # must be rejected atomically, not partially applied.
    with pytest.raises(db.ReservationConflictError):
        db.create_reservation("MEM-1004", "BOOK-2001", "2026-08-14")

    # Verify no partial damage: member MEM-1004's count must be untouched
    member = db.get_member("MEM-1004")
    assert int(member["active_reservations"]) == 5  # unchanged from setup


def test_create_reservation_rejects_exact_duplicate_rerun(dynamo_tables):
    db = dynamo_tables

    db.create_reservation("MEM-1001", "BOOK-2001", "2026-07-15")

    # Simulate the exact same request re-firing (e.g. a retried tool call).
    # Because reservation_id is deterministic (member+book) and the book
    # is no longer AVAILABLE, this must fail rather than silently create
    # a second reservation record or double-increment the member's count.
    with pytest.raises(db.ReservationConflictError):
        db.create_reservation("MEM-1001", "BOOK-2001", "2026-07-15")

    member = db.get_member("MEM-1001")
    assert int(member["active_reservations"]) == 1  # NOT incremented twice

    active = db.get_active_reservations("MEM-1001")
    assert len(active) == 1  # NOT duplicated


def test_get_author_lookup(dynamo_tables):
    db = dynamo_tables
    author = db.get_author("AUTH-001")
    assert author["name"] == "F. Scott Fitzgerald"

    assert db.get_author("AUTH-DOES-NOT-EXIST") is None
    assert db.get_author("") is None


def test_membership_validity(dynamo_tables):
    db = dynamo_tables
    member = db.get_member("MEM-1001")
    assert db.is_membership_valid(member) is True

    expired_member = {"expiry_date": "2020-01-01"}
    assert db.is_membership_valid(expired_member) is False


def test_due_date_by_tier(dynamo_tables):
    db = dynamo_tables
    # Just sanity-check the day count; exact date depends on "today".
    from datetime import datetime, timedelta

    standard_due = db.calculate_due_date("standard")
    premium_due = db.calculate_due_date("premium")

    expected_standard = str((datetime.today().date() + timedelta(days=14)))
    expected_premium = str((datetime.today().date() + timedelta(days=30)))

    assert standard_due == expected_standard
    assert premium_due == expected_premium
