"""
main.py
--------
Entry point for LOCAL testing of the Library Reservation System.

HOW TO RUN:
  Sequential mode:  python main.py --mode sequential
  Parallel mode:    python main.py --mode parallel

The agent will start an interactive chat session in your terminal.
Type your request (e.g., "I want to reserve a book") and follow the prompts.
Type 'exit' or 'quit' to stop.
"""

import argparse
import re
import sys
import os

# Make sure Python can find the agents/ and tools/ folders
sys.path.insert(0, os.path.dirname(__file__))

from agents.orchestrator_agent import get_agent, _reset_trace_clock

# Nova Lite emits its chain-of-thought as literal <thinking>...</thinking>
# text inside the response instead of a separate hidden reasoning field.
# Strip it out before showing the response to the user.
_THINKING_TAG_RE = re.compile(r"<thinking>.*?</thinking>\s*", re.DOTALL)


def clean_response(text: str) -> str:
    return _THINKING_TAG_RE.sub("", str(text)).strip()


def run_interactive_session(workflow_mode: str, debug: bool = False):
    """Run an interactive chat loop with the library agent."""

    print("=" * 60)
    print("  Library Reservation System")
    print(f"  Workflow Mode: {workflow_mode.upper()}")
    if debug:
        print("  Debug tracing: ON (tool call START/END timestamps)")
    print("  Powered by: AWS Strands + Amazon Bedrock (Claude)")
    print("=" * 60)
    print()
    print("Type your message and press Enter.")
    print("Type 'exit' or 'quit' to stop.")
    print()
    print("Example: 'I want to reserve book BOOK-2001 for member MEM-1001'")
    print()

    # Create the agent once — it maintains conversation history across turns
    agent = get_agent(workflow_mode, debug=debug)

    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            break

        if not user_input:
            continue

        if user_input.lower() in ("exit", "quit", "bye"):
            print("Agent: Thank you for using the Library System. Goodbye!")
            break

        # Send the user's message to the agent and print the response
        try:
            if debug:
                _reset_trace_clock()  # restart the per-turn stopwatch
            response = agent(user_input)
            print(f"\nAgent: {clean_response(response)}\n")
        except Exception as e:
            print(f"\n[ERROR] Agent encountered an error: {e}")
            print("Please check your AWS credentials and DynamoDB tables.\n")


def main():
    parser = argparse.ArgumentParser(
        description="Library Reservation System - Local Testing"
    )
    parser.add_argument(
        "--mode",
        choices=["sequential", "parallel"],
        default="sequential",
        help="Workflow mode: 'sequential' (default) or 'parallel'",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print timestamped START/END lines around each tool call, "
             "so you can visually confirm parallel vs sequential execution.",
    )
    args = parser.parse_args()

    run_interactive_session(args.mode, debug=args.debug)


if __name__ == "__main__":
    main()