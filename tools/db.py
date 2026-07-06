"""
tools/db.py
-----------
All DynamoDB interactions for the Library Reservation System.
This file handles reading members, books, reservations, and writing new reservations.
"""

import boto3
import os
from datetime import datetime, timedelta
from boto3.dynamodb.conditions import Key, Attr
from botocore.exceptions import ClientError

# ─────────────────────────────────────────────
# DynamoDB Client Setup
# ─────────────────────────────────────────────
# boto3 automatically reads credentials from:
#   1. Environment variables: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION
#   2. ~/.aws/credentials file (set by `aws configure`)
# You do NOT need to hardcode credentials anywhere.

AWS_REGION = os.getenv("AWS_DEFAULT_REGION", "ap-south-1")

dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)

# Table references — these names must match what you created in DynamoDB
TABLE_MEMBERS      = dynamodb.Table("library_members")
TABLE_BOOKS        = dynamodb.Table("library_books")
TABLE_AUTHORS      = dynamodb.Table("library_authors")
TABLE_RESERVATIONS = dynamodb.Table("library_reservations")
TABLE_HISTORY      = dynamodb.Table("library_borrowing_history")

# Raw table names, needed for TransactWriteItems (which takes table names,
# not Table resource objects).
_TABLE_NAME_BOOKS        = "library_books"
_TABLE_NAME_MEMBERS      = "library_members"
_TABLE_NAME_RESERVATIONS = "library_reservations"

dynamodb_client = boto3.client("dynamodb", region_name=AWS_REGION)


# ─────────────────────────────────────────────
# Member Functions
# ─────────────────────────────────────────────

def get_member(member_id: str) -> dict | None:
    """
    Fetch a member record from DynamoDB by member_id.
    Returns the member dict or None if not found.
    """
    response = TABLE_MEMBERS.get_item(Key={"member_id": member_id})
    return response.get("Item")


def is_membership_valid(member: dict) -> bool:
    """
    Check if a member's membership is currently active (not expired).
    The expiry_date field is stored as a string in format YYYY-MM-DD.
    """
    expiry_str = member.get("expiry_date", "")
    if not expiry_str:
        return False
    expiry_date = datetime.strptime(expiry_str, "%Y-%m-%d").date()
    return expiry_date >= datetime.today().date()


def get_membership_tier(member: dict) -> str:
    """Returns 'standard' or 'premium'."""
    return member.get("tier", "standard").lower()


# ─────────────────────────────────────────────
# Book Functions
# ─────────────────────────────────────────────

def get_book(book_id: str) -> dict | None:
    """
    Fetch a book record from DynamoDB by book_id.
    Returns the book dict or None if not found.
    """
    response = TABLE_BOOKS.get_item(Key={"book_id": book_id})
    return response.get("Item")


def is_book_available(book: dict) -> bool:
    """
    Check if a book is currently available (status == 'AVAILABLE').
    """
    return book.get("status", "").upper() == "AVAILABLE"


# ─────────────────────────────────────────────
# Author Functions
# ─────────────────────────────────────────────

def get_author(author_id: str) -> dict | None:
    """
    Fetch an author record from DynamoDB by author_id.
    Returns the author dict or None if not found.
    """
    if not author_id:
        return None
    response = TABLE_AUTHORS.get_item(Key={"author_id": author_id})
    return response.get("Item")


# ─────────────────────────────────────────────
# Reservation Functions
# ─────────────────────────────────────────────

def get_active_reservations(member_id: str) -> list:
    """
    Fetch all ACTIVE reservations for a given member.
    Uses a scan with a filter — works fine for small datasets.
    """
    response = TABLE_RESERVATIONS.scan(
        FilterExpression=Attr("member_id").eq(member_id) & Attr("status").eq("RESERVED")
    )
    return response.get("Items", [])


def get_reservation_limit(tier: str) -> int:
    """
    Return how many books a member can reserve at once based on tier.
      - standard: up to 2 books
      - premium:  up to 5 books
    """
    limits = {"standard": 2, "premium": 5}
    return limits.get(tier, 2)


def calculate_due_date(tier: str) -> str:
    """
    Calculate the due date for a reservation based on membership tier.
      - standard: 14 days from today
      - premium:  30 days from today
    Returns date as a string: YYYY-MM-DD
    """
    days = 30 if tier == "premium" else 14
    due_date = datetime.today().date() + timedelta(days=days)
    return str(due_date)


def check_overdue_books(member_id: str) -> list:
    """
    Find any reservations that are RESERVED but past their due date.
    Returns a list of overdue items.
    """
    today_str = str(datetime.today().date())
    response = TABLE_RESERVATIONS.scan(
        FilterExpression=(
            Attr("member_id").eq(member_id)
            & Attr("status").eq("RESERVED")
            & Attr("due_date").lt(today_str)
        )
    )
    return response.get("Items", [])


class ReservationConflictError(Exception):
    """
    Raised when a reservation cannot be safely written — either the book is
    no longer AVAILABLE (someone else grabbed it first) or this exact
    reservation already exists (duplicate submit / re-run).
    """
    pass


def create_reservation(member_id: str, book_id: str, due_date: str) -> dict:
    """
    Atomically write a new reservation to DynamoDB.

    Uses a single TransactWriteItems call so that all three writes succeed
    or fail together:
      1. Create the reservation record (status RESERVED).
      2. Flip the book's status AVAILABLE -> RESERVED.
      3. Increment the member's active_reservations count.

    Idempotency / no-duplicates:
      - reservation_id is deterministic (member_id + book_id), so re-running
        the exact same reservation request maps to the same primary key.
      - The book-update step carries a ConditionExpression requiring the
        book to currently be AVAILABLE. If the book was already reserved
        (by this same request re-firing, or by someone else), the whole
        transaction is rejected atomically instead of silently creating a
        second record or double-booking the book.

    Raises:
        ReservationConflictError: if the book is not AVAILABLE or the
            reservation already exists.

    Returns the created reservation item.
    """
    reservation_id = f"RES-{member_id}-{book_id}"
    today_str = str(datetime.today().date())

    reservation_item = {
        "reservation_id":    reservation_id,
        "member_id":         member_id,
        "book_id":           book_id,
        "status":            "RESERVED",
        "reservation_date":  today_str,
        "due_date":          due_date,
    }

    try:
        dynamodb_client.transact_write_items(
            TransactItems=[
                {
                    "Put": {
                        "TableName": _TABLE_NAME_RESERVATIONS,
                        "Item": {
                            "reservation_id":   {"S": reservation_id},
                            "member_id":        {"S": member_id},
                            "book_id":          {"S": book_id},
                            "status":           {"S": "RESERVED"},
                            "reservation_date": {"S": today_str},
                            "due_date":         {"S": due_date},
                        },
                        # Allows writing when either (a) this reservation_id
                        # has never existed, or (b) it exists but its
                        # current status is NOT "RESERVED" (e.g. it was
                        # previously CANCELLED or RETURNED) — so a member
                        # can re-reserve the same book after cancelling,
                        # since reservation_id is deterministic on
                        # member_id+book_id and cancel_reservation only
                        # flips status rather than deleting the record.
                        # Still blocks true duplicates: if it's currently
                        # RESERVED, the condition fails and no double
                        # reservation/duplicate record is written.
                        "ConditionExpression": "attribute_not_exists(reservation_id) OR #s <> :reserved",
                        "ExpressionAttributeNames": {"#s": "status"},
                        "ExpressionAttributeValues": {
                            ":reserved": {"S": "RESERVED"},
                        },
                    }
                },
                {
                    "Update": {
                        "TableName": _TABLE_NAME_BOOKS,
                        "Key": {"book_id": {"S": book_id}},
                        "UpdateExpression": "SET #s = :reserved",
                        "ConditionExpression": "#s = :available",
                        "ExpressionAttributeNames": {"#s": "status"},
                        "ExpressionAttributeValues": {
                            ":reserved":  {"S": "RESERVED"},
                            ":available": {"S": "AVAILABLE"},
                        },
                    }
                },
                {
                    "Update": {
                        "TableName": _TABLE_NAME_MEMBERS,
                        "Key": {"member_id": {"S": member_id}},
                        "UpdateExpression": "ADD active_reservations :one",
                        "ExpressionAttributeValues": {":one": {"N": "1"}},
                    }
                },
            ]
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "TransactionCanceledException":
            raise ReservationConflictError(
                f"Could not reserve '{book_id}' for '{member_id}': "
                "book is no longer available or this reservation already exists."
            ) from e
        raise

    return reservation_item


def get_reservation(member_id: str, book_id: str) -> dict | None:
    """
    Fetch a single reservation record by its deterministic ID
    (RES-{member_id}-{book_id}). Returns None if it never existed.
    """
    reservation_id = f"RES-{member_id}-{book_id}"
    response = TABLE_RESERVATIONS.get_item(Key={"reservation_id": reservation_id})
    return response.get("Item")


def _explain_cancellation_failure(error: ClientError, reservation_id: str, book_id: str, member_id: str) -> str:
    """
    A TransactWriteItems failure only tells you "TransactionCanceledException"
    by default — it doesn't say WHICH of the 3 items failed or why. AWS
    does include a CancellationReasons list (one entry per TransactItem,
    in the same order they were submitted) with a per-item Code such as
    "ConditionalCheckFailed" or "None" (that item was fine). This decodes
    that into a specific, actionable message instead of a generic one —
    this is exactly the kind of detail that would have made the
    "reservation says RESERVED but book says AVAILABLE" data-drift issue
    (e.g. from re-running init_dynamodb.py, which resets books but not
    reservations) immediately diagnosable instead of a misleading
    "no active reservation found".
    """
    reasons = error.response.get("CancellationReasons", [])
    # Order matches the TransactItems list in cancel_reservation:
    # [0] reservation update, [1] book update, [2] member update
    labels = [
        f"reservation '{reservation_id}' is not currently RESERVED (already cancelled, or never existed)",
        f"book '{book_id}' is not currently RESERVED in the books table (status drift — "
        f"did init_dynamodb.py get re-run after this reservation was made?)",
        f"member '{member_id}' has no positive active_reservations count to decrement",
    ]
    failed = [
        labels[i] for i, r in enumerate(reasons)
        if i < len(labels) and r.get("Code") not in (None, "None")
    ]
    if failed:
        return f"Could not cancel: {'; '.join(failed)}."
    return (
        f"Could not cancel reservation for '{book_id}' / '{member_id}': "
        "transaction was rejected for an unspecified reason — check CancellationReasons in the raw error."
    )


def cancel_reservation(member_id: str, book_id: str) -> dict:
    """
    Atomically cancel an existing RESERVED reservation and free up the book.

    Uses a single TransactWriteItems call so that all three writes succeed
    or fail together:
      1. Flip the reservation's status RESERVED -> CANCELLED.
      2. Flip the book's status RESERVED -> AVAILABLE.
      3. Decrement the member's active_reservations count (floor 0).

    ConditionExpression on the reservation update requires it to currently
    be RESERVED, so this safely no-ops/raises instead of double-cancelling
    or cancelling something that was never reserved.

    Raises:
        ReservationConflictError: if there is no active RESERVED reservation
            for this member+book pair (already cancelled, already returned,
            or never existed).

    Returns the updated reservation item (now CANCELLED).
    """
    reservation_id = f"RES-{member_id}-{book_id}"

    try:
        dynamodb_client.transact_write_items(
            TransactItems=[
                {
                    "Update": {
                        "TableName": _TABLE_NAME_RESERVATIONS,
                        "Key": {"reservation_id": {"S": reservation_id}},
                        "UpdateExpression": "SET #s = :cancelled",
                        "ConditionExpression": "attribute_exists(reservation_id) AND #s = :reserved",
                        "ExpressionAttributeNames": {"#s": "status"},
                        "ExpressionAttributeValues": {
                            ":cancelled": {"S": "CANCELLED"},
                            ":reserved":  {"S": "RESERVED"},
                        },
                    }
                },
                {
                    "Update": {
                        "TableName": _TABLE_NAME_BOOKS,
                        "Key": {"book_id": {"S": book_id}},
                        "UpdateExpression": "SET #s = :available",
                        "ConditionExpression": "#s = :reserved",
                        "ExpressionAttributeNames": {"#s": "status"},
                        "ExpressionAttributeValues": {
                            ":available": {"S": "AVAILABLE"},
                            ":reserved":  {"S": "RESERVED"},
                        },
                    }
                },
                {
                    "Update": {
                        "TableName": _TABLE_NAME_MEMBERS,
                        "Key": {"member_id": {"S": member_id}},
                        "UpdateExpression": "SET active_reservations = if_not_exists(active_reservations, :zero) - :one",
                        "ConditionExpression": "attribute_not_exists(active_reservations) OR active_reservations > :zero",
                        "ExpressionAttributeValues": {
                            ":one":  {"N": "1"},
                            ":zero": {"N": "0"},
                        },
                    }
                },
            ]
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "TransactionCanceledException":
            raise ReservationConflictError(
                _explain_cancellation_failure(e, reservation_id, book_id, member_id)
            ) from e
        raise

    return {
        "reservation_id": reservation_id,
        "member_id":       member_id,
        "book_id":         book_id,
        "status":          "CANCELLED",
    }


def get_borrowing_history(member_id: str) -> list:
    """
    Fetch the full borrowing history for a member.
    """
    response = TABLE_HISTORY.scan(
        FilterExpression=Attr("member_id").eq(member_id)
    )
    return response.get("Items", [])