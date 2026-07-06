# Sample Prompts — Library Reservation System

Use these prompts when testing the agent locally (`python main.py`) or in the Bedrock AgentCore console.

---

## 1. Happy Path (Successful Reservation)

**Member:** MEM-1001 (Alice Johnson, standard, valid membership)
**Book:** BOOK-2001 (The Great Gatsby, available)

```
I'd like to reserve a book. My member ID is MEM-1001 and I want book BOOK-2001.
```

**Expected flow:**
1. Agent looks up member MEM-1001 → Found: Alice Johnson
2. Agent checks membership → Valid, standard tier
3. Agent checks book BOOK-2001 → Available
4. Agent checks eligibility → 0 active reservations, limit is 2, eligible
5. Agent calculates due date → 14 days from today (standard tier)
6. Agent shows reservation summary and asks for confirmation
7. You type: `YES`
8. Agent saves to DynamoDB and confirms reservation

---

## 2. Expired Membership

**Member:** MEM-1003 (Carol White, expired membership)
**Book:** BOOK-2002

```
Hi, I want to borrow a book. My member ID is MEM-1003 and the book ID is BOOK-2002.
```

**Expected:** Agent detects expired membership and stops. Does NOT proceed to book check.

---

## 3. Book Not Available

**Member:** MEM-1001 (valid membership)
**Book:** BOOK-2003 (1984 — already RESERVED by someone else)

```
Can I reserve book BOOK-2003? My member ID is MEM-1001.
```

**Expected:** Agent finds member valid, then sees BOOK-2003 is RESERVED (not available), stops and informs the user.

---

## 4. Reservation Limit Reached

**Member:** MEM-1004 (David Brown, premium, 5 active reservations — AT LIMIT)
**Book:** BOOK-2004

```
I am member MEM-1004 and I want to reserve book BOOK-2004.
```

**Expected:** Agent finds David Brown has 5/5 active reservations (premium limit). Stops and says limit is reached.

---

## 5. Human Rejection (User Says NO)

**Member:** MEM-1005 (Eve Davis, valid)
**Book:** BOOK-2005 (The Hobbit, available)

```
Reserve book BOOK-2005 for member MEM-1005 please.
```

When the agent presents the summary and asks for confirmation, type:

```
NO
```

**Expected:** Agent cancels without writing anything to DynamoDB. Reservation is NOT saved.

---

## 6. Multi-Book / Edge Cases

### 6a. Genuine Multi-Book Reservation

**Member:** MEM-1001 (Alice Johnson, standard, valid, 0 active reservations, limit 2)
**Books:** BOOK-2001 (available) and BOOK-2004 (available)

```
I'd like to reserve two books for member MEM-1001: BOOK-2001 and BOOK-2004.
```

**Expected flow:** The agent should run the full check (membership, availability,
eligibility, due date) for each book, and treat the reservation-limit check as
stateful across both — e.g. after the first book is confirmed, Alice now has 1
active reservation, so the eligibility check for the second book should reflect
that before presenting its own confirmation. Each book gets its own YES/NO
confirmation and its own `submit_reservation` call (with `confirmed=True` only
after that specific book is approved), so the user could say YES to one and NO
to the other.

### 6b. Multi-Book Where the Limit Is Hit Mid-Request

**Member:** MEM-1004 (David Brown, premium, already at 5/5 limit)
**Books:** BOOK-2004 and BOOK-2006 (both available)

```
Reserve BOOK-2004 and BOOK-2006 for member MEM-1004.
```

**Expected:** Agent finds the member already at their reservation limit and
stops before offering either book — it should not attempt to reserve one book
just because the limit hasn't technically been exceeded by *that* book alone.

### 6c. Premium Member Gets 30-Day Loan

```
I want to reserve book BOOK-2006. My ID is MEM-1002.
```

**Expected:** Bob Smith (premium) gets a 30-day due date instead of 14 days.

### 6d. Member Not Found

```
Reserve book BOOK-2001 for member MEM-9999.
```

**Expected:** Agent says member MEM-9999 is not found.

### 6e. Book Not Found

```
I want book BOOK-9999. My member ID is MEM-1001.
```

**Expected:** Agent says book BOOK-9999 is not in the catalogue.

### 6f. Check Borrowing History

```
Show me the borrowing history for member MEM-1001.
```

**Expected:** Agent calls get_member_borrowing_history and lists past records.

### 6g. Check Active Reservations

```
How many books does member MEM-1002 currently have reserved?
```

**Expected:** Agent calls get_active_reservations_list and shows Bob Smith's current reservations.

---

## 7. Parallel Workflow Specific

Run with `python main.py --mode parallel` and use this prompt:

```
Please check if member MEM-1005 can reserve book BOOK-2004.
```

**Expected in parallel mode:** The agent runs membership check and book availability check simultaneously, then merges results before proceeding.

---

## 8. Duplicate Submission / Re-run Protection

**Member:** MEM-1005 (Eve Davis, valid)
**Book:** BOOK-2005 (The Hobbit, available)

```
Reserve book BOOK-2005 for member MEM-1005 please.
```

Confirm with `YES`, let the reservation succeed, then in the **same or a new
session** send the identical request again and confirm `YES` again.

**Expected:** The second attempt fails cleanly (the book is now RESERVED, so
`check_book_availability` reports it as unavailable before `submit_reservation`
is even reached). If you bypass that and call `submit_reservation` directly
twice for the same member+book, the second call returns an error from the
DynamoDB transaction rather than creating a second reservation record —
verify only one item exists with ID `RES-MEM-1005-BOOK-2005` in
`library_reservations`.
