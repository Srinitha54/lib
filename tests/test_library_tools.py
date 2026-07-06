"""
tests/test_library_tools.py
-----------------------------
Verifies the human-in-the-loop gate is enforced in code: submit_reservation
must refuse to write anything unless confirmed=True is passed explicitly.

Per the Strands SDK docs, @tool-decorated functions "can be called both as
a regular Python function and as a Strands tool" — so these are called
directly, no Bedrock/Strands Agent runtime needed for this layer of testing.
"""


def test_submit_reservation_blocks_without_confirmation(dynamo_tables):
    import tools.library_tools as lt

    result = lt.submit_reservation(
        member_id="MEM-1001", book_id="BOOK-2001", due_date="2026-07-15", confirmed=False
    )

    assert result["success"] is False
    assert "confirmation" in result["error"].lower()

    # Nothing should have been written
    from tools.db import get_book
    assert get_book("BOOK-2001")["status"] == "AVAILABLE"


def test_submit_reservation_succeeds_when_confirmed(dynamo_tables):
    import tools.library_tools as lt

    result = lt.submit_reservation(
        member_id="MEM-1001", book_id="BOOK-2001", due_date="2026-07-15", confirmed=True
    )

    assert result["success"] is True
    assert result["reservation_id"] == "RES-MEM-1001-BOOK-2001"


def test_submit_reservation_rejects_already_reserved_book(dynamo_tables):
    import tools.library_tools as lt

    lt.submit_reservation(member_id="MEM-1001", book_id="BOOK-2001", due_date="2026-07-15", confirmed=True)

    # A second, different member confirming a reservation for the same
    # (now-taken) book must be rejected, not silently succeed.
    result = lt.submit_reservation(
        member_id="MEM-1004", book_id="BOOK-2001", due_date="2026-08-14", confirmed=True
    )
    assert result["success"] is False
    assert "error" in result


def test_check_reservation_eligibility_flags_limit_reached(dynamo_tables):
    import tools.library_tools as lt

    result = lt.check_reservation_eligibility(member_id="MEM-1004")  # premium, already at 5/5 in fixture

    assert result["eligible"] is False
    assert result["active_count"] == 5
    assert result["limit"] == 5
