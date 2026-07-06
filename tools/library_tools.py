"""
tools/library_tools.py
-----------------------
All @tool-decorated functions that the Strands Agent can call.
Each tool does ONE specific thing. The agent decides which tools to call and in what order.

HOW TOOLS WORK:
  - The @tool decorator from strands exposes these functions to the LLM.
  - The LLM reads the docstring to understand what each tool does.
  - The LLM reads the type hints to know what parameters to pass.
  - You NEVER call these manually — the agent calls them automatically.
"""

from strands import tool
from datetime import datetime
from tools.db import (
    get_member,
    is_membership_valid,
    get_membership_tier,
    get_book,
    is_book_available,
    get_author,
    get_active_reservations,
    get_reservation_limit,
    calculate_due_date,
    check_overdue_books,
    create_reservation,
    get_borrowing_history,
    get_reservation,
    cancel_reservation,
    ReservationConflictError,
)


# ─────────────────────────────────────────────
# TOOL 1: Look up a member
# ─────────────────────────────────────────────
@tool
def lookup_member(member_id: str) -> dict:
    """
    Look up a library member by their member ID.
    Returns the member's full profile including name, tier, expiry date,
    and current active reservation count.
    If the member is not found, returns an error message.

    Args:
        member_id: The unique member ID (e.g., "MEM-1001")
    """
    member = get_member(member_id)
    if not member:
        return {"error": f"Member '{member_id}' not found in the system."}
    return {
        "member_id":    member["member_id"],
        "name":         member.get("name", "Unknown"),
        "tier":         member.get("tier", "standard"),
        "expiry_date":  member.get("expiry_date", "N/A"),
        "active_reservations": int(member.get("active_reservations", 0)),
    }


# ─────────────────────────────────────────────
# TOOL 2: Check membership validity
# ─────────────────────────────────────────────
@tool
def check_membership_status(member_id: str) -> dict:
    """
    Check whether a library member's membership is currently valid (not expired).
    Returns is_valid (True/False), the expiry date, and the membership tier.

    Args:
        member_id: The unique member ID (e.g., "MEM-1001")
    """
    member = get_member(member_id)
    if not member:
        return {"error": f"Member '{member_id}' not found."}

    valid    = is_membership_valid(member)
    tier     = get_membership_tier(member)
    expiry   = member.get("expiry_date", "N/A")

    return {
        "member_id":    member_id,
        "is_valid":     valid,
        "tier":         tier,
        "expiry_date":  expiry,
        "message":      "Membership is active." if valid else f"Membership expired on {expiry}.",
    }


# ─────────────────────────────────────────────
# TOOL 3: Check book availability
# ─────────────────────────────────────────────
@tool
def check_book_availability(book_id: str) -> dict:
    """
    Check whether a specific book is currently available for reservation.
    Returns the book's title, author, and availability status.

    Args:
        book_id: The unique book ID (e.g., "BOOK-2001")
    """
    book = get_book(book_id)
    if not book:
        return {"error": f"Book '{book_id}' not found in the catalogue."}

    available = is_book_available(book)

    return {
        "book_id":   book["book_id"],
        "title":     book.get("title", "Unknown"),
        "author":    book.get("author", "Unknown"),
        "author_id": book.get("author_id"),
        "status":    book.get("status", "UNKNOWN"),
        "available": available,
        "message":   "Book is available for reservation." if available else "Book is currently not available.",
    }


# ─────────────────────────────────────────────
# TOOL 3b: Look up an author's details
# ─────────────────────────────────────────────
@tool
def get_author_details(author_id: str) -> dict:
    """
    Look up an author's biographical details by author ID.
    Useful when presenting a reservation summary that should mention
    who wrote the book.

    Args:
        author_id: The unique author ID (e.g., "AUTH-001")
    """
    author = get_author(author_id)
    if not author:
        return {"error": f"Author '{author_id}' not found."}
    return {
        "author_id":    author["author_id"],
        "name":         author.get("name", "Unknown"),
        "nationality":  author.get("nationality", "Unknown"),
        "birth_year":   author.get("birth_year"),
        "bio":          author.get("bio", ""),
    }


# ─────────────────────────────────────────────
# TOOL 4: Check reservation eligibility
# ─────────────────────────────────────────────
@tool
def check_reservation_eligibility(member_id: str) -> dict:
    """
    Check whether a member is eligible to make a new reservation.
    This verifies:
      1. Membership is valid (not expired)
      2. They haven't exceeded their concurrent reservation limit
      3. They have no overdue books

    Args:
        member_id: The unique member ID (e.g., "MEM-1001")
    """
    member = get_member(member_id)
    if not member:
        return {"error": f"Member '{member_id}' not found."}

    tier          = get_membership_tier(member)
    limit         = get_reservation_limit(tier)
    # Use the member's own active_reservations counter as the source of
    # truth (it's kept in sync atomically inside create_reservation's
    # transaction), rather than re-scanning the reservations table.
    active_count  = int(member.get("active_reservations", 0))
    overdue       = check_overdue_books(member_id)
    membership_ok = is_membership_valid(member)

    eligible = membership_ok and active_count < limit and len(overdue) == 0

    reasons = []
    if not membership_ok:
        reasons.append("Membership has expired.")
    if active_count >= limit:
        reasons.append(f"Reservation limit reached ({active_count}/{limit}).")
    if overdue:
        reasons.append(f"Has {len(overdue)} overdue book(s) to return first.")

    return {
        "member_id":    member_id,
        "tier":         tier,
        "eligible":     eligible,
        "active_count": active_count,
        "limit":        limit,
        "overdue_count": len(overdue),
        "reasons":      reasons if reasons else ["Member is eligible."],
    }


# ─────────────────────────────────────────────
# TOOL 5: Calculate the due date
# ─────────────────────────────────────────────
@tool
def calculate_reservation_due_date(member_id: str) -> dict:
    """
    Calculate the due date for a reservation based on the member's tier,
    and return today's actual date as the reservation date.

    Standard members get 14 days. Premium members get 30 days.
    Returns both reservation_date (today, YYYY-MM-DD) and due_date
    (YYYY-MM-DD). ALWAYS use reservation_date from this tool's output for
    "today" in the summary — never guess or infer today's date yourself,
    since your own sense of the current date may be wrong.

    Args:
        member_id: The unique member ID (e.g., "MEM-1001")
    """
    member = get_member(member_id)
    if not member:
        return {"error": f"Member '{member_id}' not found."}

    tier     = get_membership_tier(member)
    due_date = calculate_due_date(tier)
    days     = 30 if tier == "premium" else 14

    return {
        "member_id":         member_id,
        "tier":              tier,
        "reservation_date":  str(datetime.today().date()),
        "due_date":          due_date,
        "loan_days":         days,
    }


# ─────────────────────────────────────────────
# TOOL 6: Submit the reservation (after user confirms YES)
# ─────────────────────────────────────────────
@tool
def submit_reservation(member_id: str, book_id: str, due_date: str, confirmed: bool) -> dict:
    """
    Submit and save a confirmed reservation to DynamoDB.

    IMPORTANT: This must ONLY be called with confirmed=True, and ONLY after
    the user has explicitly typed a clear affirmative response (e.g. "YES")
    to the reservation summary you presented. If the user has not yet been
    shown the summary and asked to confirm, or if they said anything other
    than a clear yes, call this with confirmed=False (or don't call it at
    all) — do not guess or assume confirmation.

    The write itself is atomic: the reservation record, the book's
    AVAILABLE -> RESERVED status flip, and the member's active reservation
    count are all updated in a single DynamoDB transaction. If the book was
    already reserved (e.g. by a concurrent request, or this exact call
    re-firing), the transaction is safely rejected and no duplicate or
    partial record is written.

    Args:
        member_id: The unique member ID (e.g., "MEM-1001")
        book_id:   The unique book ID (e.g., "BOOK-2001")
        due_date:  The calculated due date as YYYY-MM-DD (e.g., "2026-07-29")
        confirmed: Must be True. Set only after the user has explicitly said YES.
    """
    if not confirmed:
        return {
            "success": False,
            "error": "Reservation not submitted: user confirmation was not received. "
                     "Present the reservation summary and ask for YES/NO before calling this tool again.",
        }

    # Final safety check before writing
    book = get_book(book_id)
    if not book or not is_book_available(book):
        # Before reporting failure, check whether THIS exact member already
        # holds an active reservation on this book — that would mean a
        # duplicate/overlapping call to this same tool (this agent runs on
        # ConcurrentToolExecutor for every tool, and smaller models like
        # Nova Lite occasionally emit a tool call twice in one turn) already
        # succeeded a moment ago. In that case this is a successful no-op,
        # not a real failure.
        existing = get_reservation(member_id, book_id)
        if existing and existing.get("status") == "RESERVED":
            return {
                "success":        True,
                "reservation_id": existing["reservation_id"],
                "member_id":      member_id,
                "book_id":        book_id,
                "due_date":       existing.get("due_date", due_date),
                "message":        f"Reservation already confirmed! Return by {existing.get('due_date', due_date)}.",
            }
        return {
            "success": False,
            "error": f"Book '{book_id}' is no longer available. Cannot reserve.",
        }

    try:
        reservation = create_reservation(member_id, book_id, due_date)
    except ReservationConflictError:
        # Same idempotency check: if a concurrent duplicate call already
        # created this exact reservation, that's a success, not an error.
        existing = get_reservation(member_id, book_id)
        if existing and existing.get("status") == "RESERVED":
            return {
                "success":        True,
                "reservation_id": existing["reservation_id"],
                "member_id":      member_id,
                "book_id":        book_id,
                "due_date":       existing.get("due_date", due_date),
                "message":        f"Reservation already confirmed! Return by {existing.get('due_date', due_date)}.",
            }
        return {
            "success": False,
            "error": f"Book '{book_id}' is no longer available or this reservation already exists.",
        }

    return {
        "success":        True,
        "reservation_id": reservation["reservation_id"],
        "member_id":      member_id,
        "book_id":        book_id,
        "due_date":       due_date,
        "message":        f"Reservation confirmed! Return by {due_date}.",
    }


# ─────────────────────────────────────────────
# TOOL 6b: Cancel an existing reservation (un-reserve a book)
# ─────────────────────────────────────────────
@tool
def cancel_book_reservation(member_id: str, book_id: str, confirmed: bool) -> dict:
    """
    Cancel an existing RESERVED reservation for a member and book, freeing
    the book back up so it (or another member) can be reserved again.

    IMPORTANT: This must ONLY be called with confirmed=True, and ONLY after
    the user has explicitly asked to cancel/un-reserve/release this specific
    book and, if there was any ambiguity, confirmed with a clear "YES". If
    the user has not clearly asked to cancel, call this with confirmed=False
    (or don't call it at all) — do not guess.

    The write itself is atomic: the reservation's RESERVED -> CANCELLED
    flip, the book's RESERVED -> AVAILABLE flip, and the member's active
    reservation count decrement are all updated in a single DynamoDB
    transaction. If there is no active RESERVED reservation for this exact
    member+book pair (e.g. it was already cancelled, already returned, or
    never existed), the transaction is safely rejected and nothing changes.

    Args:
        member_id: The unique member ID (e.g., "MEM-1001")
        book_id:   The unique book ID (e.g., "BOOK-2001")
        confirmed: Must be True. Set only once the user has clearly asked
                   to cancel this reservation.
    """
    if not confirmed:
        return {
            "success": False,
            "error": "Cancellation not submitted: confirmation was not received. "
                     "Confirm which book/member to cancel before calling this tool again.",
        }

    existing = get_reservation(member_id, book_id)

    if not existing:
        return {
            "success": False,
            "error": f"No reservation found for book '{book_id}' and member '{member_id}' to cancel.",
        }

    # Idempotency: if it's already CANCELLED (e.g. a duplicate/overlapping
    # tool call from this same request already cancelled it a moment ago),
    # treat this as a successful no-op rather than an error. Without this,
    # two concurrent cancel calls for the same reservation — which can
    # happen since this agent runs on ConcurrentToolExecutor — would have
    # one succeed and the other report a confusing false "not found" error
    # even though the cancellation genuinely went through.
    if existing.get("status") == "CANCELLED":
        return {
            "success":        True,
            "reservation_id": existing["reservation_id"],
            "member_id":      member_id,
            "book_id":        book_id,
            "status":         "CANCELLED",
            "message":        f"Reservation for '{book_id}' is already cancelled. The book is available.",
        }

    if existing.get("status") != "RESERVED":
        return {
            "success": False,
            "error": f"Reservation for book '{book_id}' and member '{member_id}' is not active "
                     f"(current status: {existing.get('status')}), so it cannot be cancelled.",
        }

    try:
        result = cancel_reservation(member_id, book_id)
    except ReservationConflictError:
        # Lost the race to a concurrent duplicate call that cancelled it
        # first. Re-check: if it's now CANCELLED, that's still a success
        # from the user's point of view.
        recheck = get_reservation(member_id, book_id)
        if recheck and recheck.get("status") == "CANCELLED":
            return {
                "success":        True,
                "reservation_id": recheck["reservation_id"],
                "member_id":      member_id,
                "book_id":        book_id,
                "status":         "CANCELLED",
                "message":        f"Reservation for '{book_id}' has been cancelled. The book is now available again.",
            }
        return {
            "success": False,
            "error": f"Could not cancel reservation for '{book_id}' / '{member_id}': "
                     "it is no longer in a cancellable state.",
        }

    return {
        "success":        True,
        "reservation_id": result["reservation_id"],
        "member_id":      member_id,
        "book_id":        book_id,
        "status":         result["status"],
        "message":        f"Reservation for '{book_id}' has been cancelled. The book is now available again.",
    }


# ─────────────────────────────────────────────
# TOOL 7: Get member's borrowing history
# ─────────────────────────────────────────────
@tool
def get_member_borrowing_history(member_id: str) -> dict:
    """
    Retrieve the full borrowing history for a library member.
    Shows all past and current reservations.

    Args:
        member_id: The unique member ID (e.g., "MEM-1001")
    """
    history = get_borrowing_history(member_id)
    return {
        "member_id": member_id,
        "total_records": len(history),
        "history": history,
    }


# ─────────────────────────────────────────────
# TOOL 8: Get active reservations list
# ─────────────────────────────────────────────
@tool
def get_active_reservations_list(member_id: str) -> dict:
    """
    Get the list of currently active (unreturned) reservations for a member.

    Args:
        member_id: The unique member ID (e.g., "MEM-1001")
    """
    reservations = get_active_reservations(member_id)
    return {
        "member_id":   member_id,
        "active_count": len(reservations),
        "reservations": reservations,
    }