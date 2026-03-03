#!/usr/bin/env python3
"""
Daily Summary Bot
=================
Fetches today's Gmail and Slack messages, summarizes them with Claude,
and emails a structured digest to you at 5:30 PM ET (via Windows Task Scheduler).

Usage:
    python main.py           # Run once (intended to be called by Task Scheduler)
    python main.py --test    # Dry run — prints summary to console, skips sending email
    python main.py --auth    # Run OAuth flows only (first-time setup), then exit
"""

import argparse
import os
import sys
import traceback

from dotenv import load_dotenv

# Load .env from the same directory as this script
_HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_HERE, ".env"))


def _require_env(key: str) -> str:
    val = os.getenv(key, "").strip()
    if not val:
        print(f"ERROR: {key} is not set in your .env file.")
        sys.exit(1)
    return val


def run(dry_run: bool = False) -> None:
    """Main entry point — fetch, summarize, send."""
    from gmail_reader import get_gmail_service, get_today_emails
    from slack_reader import get_today_slack_messages
    from summarizer  import format_emails_for_claude, format_slack_for_claude, summarize_with_claude
    from email_sender import send_summary_email

    # ---- Load configuration ------------------------------------------------
    anthropic_key    = _require_env("ANTHROPIC_API_KEY")
    slack_token      = os.getenv("SLACK_USER_TOKEN", "").strip()
    credentials_file = os.getenv("GMAIL_CREDENTIALS_FILE", os.path.join(_HERE, "credentials.json"))
    token_file       = os.getenv("GMAIL_TOKEN_FILE",       os.path.join(_HERE, "token.json"))
    from_email       = _require_env("SUMMARY_FROM_EMAIL")
    to_email         = _require_env("SUMMARY_TO_EMAIL")
    timezone         = os.getenv("TIMEZONE", "America/New_York")

    # ---- Gmail authentication ----------------------------------------------
    print("[1/4] Authenticating with Gmail...")
    try:
        gmail_service = get_gmail_service(credentials_file, token_file)
    except FileNotFoundError as e:
        print(f"\nERROR: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nERROR: Gmail authentication failed — {e}")
        traceback.print_exc()
        sys.exit(1)

    # ---- Fetch emails ------------------------------------------------------
    print("[2/4] Fetching today's emails...")
    try:
        emails = get_today_emails(gmail_service, from_email, timezone)
        received = [e for e in emails if not e["is_sent"]]
        print(f"       {len(received)} received, {len(emails) - len(received)} sent")
    except Exception as e:
        print(f"  Warning: could not fetch emails — {e}")
        emails = []

    # ---- Fetch Slack messages ----------------------------------------------
    print("[3/4] Fetching today's Slack messages...")
    slack_messages: list[dict] = []
    slack_user_id = ""

    if not slack_token:
        print("  Skipping Slack (SLACK_USER_TOKEN not set).")
    else:
        try:
            slack_messages, slack_user_id = get_today_slack_messages(slack_token, timezone)
            mentions = sum(1 for m in slack_messages if m["is_mention"])
            print(f"       {len(slack_messages)} messages, {mentions} @mentions")
        except Exception as e:
            print(f"  Warning: could not fetch Slack messages — {e}")

    # ---- Summarize with Claude ---------------------------------------------
    print("[4/4] Generating summary with Claude...")
    emails_text = format_emails_for_claude(emails)
    slack_text  = format_slack_for_claude(slack_messages, slack_user_id)

    try:
        summary = summarize_with_claude(
            emails_text, slack_text, anthropic_key, from_email, timezone
        )
    except Exception as e:
        print(f"\nERROR: Claude summarization failed — {e}")
        traceback.print_exc()
        sys.exit(1)

    # ---- Send or print -----------------------------------------------------
    if dry_run:
        print("\n" + "=" * 60)
        print("DRY RUN — Summary (would be emailed):")
        print("=" * 60)
        print(summary)
        print("=" * 60)
        print("\nDry run complete. No email was sent.")
    else:
        try:
            send_summary_email(gmail_service, from_email, to_email, summary, timezone)
        except Exception as e:
            print(f"\nERROR: Failed to send email — {e}")
            traceback.print_exc()
            sys.exit(1)

    print("\nDone!")


def auth_only() -> None:
    """Run OAuth flows so credentials are cached before the first scheduled run."""
    from gmail_reader import get_gmail_service

    credentials_file = os.getenv("GMAIL_CREDENTIALS_FILE", os.path.join(_HERE, "credentials.json"))
    token_file       = os.getenv("GMAIL_TOKEN_FILE",       os.path.join(_HERE, "token.json"))

    print("Running Gmail OAuth flow (a browser window will open)...")
    get_gmail_service(credentials_file, token_file)
    print("Gmail authentication successful. Token saved.")

    slack_token = os.getenv("SLACK_USER_TOKEN", "").strip()
    if slack_token:
        from slack_sdk import WebClient
        client = WebClient(token=slack_token)
        auth   = client.auth_test()
        print(f"Slack authentication successful. Logged in as: {auth['user']} ({auth['team']})")
    else:
        print("SLACK_USER_TOKEN not set — skipping Slack auth check.")

    print("\nAll authentication checks passed. You're ready to run the scheduler.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Daily Digest Bot")
    parser.add_argument(
        "--test", action="store_true",
        help="Dry run: print summary to console without sending email"
    )
    parser.add_argument(
        "--auth", action="store_true",
        help="Run OAuth flows only (first-time setup)"
    )
    args = parser.parse_args()

    if args.auth:
        auth_only()
    else:
        run(dry_run=args.test)


if __name__ == "__main__":
    main()
