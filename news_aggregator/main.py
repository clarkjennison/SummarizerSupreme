#!/usr/bin/env python3
"""
Healthcare VC News Aggregator
==============================
Pulls healthcare VC / startup news from RSS feeds, Gmail newsletters,
NewsAPI, and Crunchbase, curates with Claude, and emails a digest at 8 AM ET.

Usage:
    python main.py           # Run and send the digest
    python main.py --test    # Dry run — print digest to console, no email sent
    python main.py --auth    # Authenticate Gmail only (first-time setup)
"""

import argparse
import os
import sys
import traceback

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv

_HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_HERE, ".env"), override=True)


def _require_env(key: str) -> str:
    val = os.getenv(key, "").strip()
    if not val:
        print(f"ERROR: {key} is not set in your .env file.")
        sys.exit(1)
    return val


def run(dry_run: bool = False) -> None:
    """Main pipeline: fetch → curate → send."""
    from rss_fetcher        import fetch_articles
    from newsapi_client     import fetch_newsapi_articles, fetch_crunchbase_rounds
    from gmail_news_reader  import get_newsletter_emails
    from curator            import build_article_block, build_newsletter_block, curate_with_claude
    from email_sender       import send_news_email

    # Reuse Gmail auth from daily_summary (same credentials + token files)
    from googleapiclient.discovery import build
    from google.oauth2.credentials  import Credentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow  import InstalledAppFlow

    anthropic_key    = _require_env("ANTHROPIC_API_KEY")
    from_email       = _require_env("SUMMARY_FROM_EMAIL")
    to_email         = _require_env("SUMMARY_TO_EMAIL")
    timezone         = os.getenv("TIMEZONE", "America/New_York")
    credentials_file = os.getenv("GMAIL_CREDENTIALS_FILE", os.path.join(_HERE, "..", "daily_summary", "credentials.json"))
    token_file       = os.getenv("GMAIL_TOKEN_FILE",       os.path.join(_HERE, "..", "daily_summary", "token.json"))
    newsapi_key      = os.getenv("NEWSAPI_KEY", "").strip()
    crunchbase_key   = os.getenv("CRUNCHBASE_API_KEY", "").strip()
    lookback_hours   = int(os.getenv("LOOKBACK_HOURS", "24"))

    # ---- Gmail auth --------------------------------------------------------
    SCOPES = [
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.send",
    ]

    print("[1/5] Authenticating with Gmail...")
    creds = None
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(credentials_file):
                print(f"ERROR: credentials.json not found at {credentials_file}")
                print("Point GMAIL_CREDENTIALS_FILE in .env to your OAuth client secret.")
                sys.exit(1)
            flow  = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_file, "w") as f:
            f.write(creds.to_json())
    gmail_service = build("gmail", "v1", credentials=creds)

    # ---- RSS feeds ---------------------------------------------------------
    print("[2/5] Fetching RSS feeds...")
    try:
        rss_articles = fetch_articles(lookback_hours=lookback_hours)
        print(f"       {len(rss_articles)} articles from {_count_sources(rss_articles)} sources")
    except Exception as e:
        print(f"  Warning: RSS fetch failed — {e}")
        rss_articles = []

    # ---- NewsAPI -----------------------------------------------------------
    newsapi_items = []
    if newsapi_key:
        print("[3/5] Fetching NewsAPI results...")
        try:
            newsapi_items = fetch_newsapi_articles(newsapi_key, lookback_hours=lookback_hours)
            print(f"       {len(newsapi_items)} articles")
        except Exception as e:
            print(f"  Warning: NewsAPI failed — {e}")
    else:
        print("[3/5] Skipping NewsAPI (NEWSAPI_KEY not set).")

    # ---- Crunchbase --------------------------------------------------------
    crunchbase_rounds = []
    if crunchbase_key:
        print("       Fetching Crunchbase funding rounds...")
        try:
            crunchbase_rounds = fetch_crunchbase_rounds(crunchbase_key, lookback_hours=lookback_hours)
            print(f"       {len(crunchbase_rounds)} funding rounds")
        except Exception as e:
            print(f"  Warning: Crunchbase failed — {e}")

    # ---- Gmail newsletters -------------------------------------------------
    print("[4/5] Scanning Gmail for newsletters...")
    try:
        newsletter_emails = get_newsletter_emails(
            gmail_service, from_email, lookback_hours=lookback_hours, timezone_str=timezone
        )
        print(f"       {len(newsletter_emails)} newsletter/funding emails found")
    except Exception as e:
        print(f"  Warning: Gmail newsletter scan failed — {e}")
        newsletter_emails = []

    # ---- Curate with Claude ------------------------------------------------
    print("[5/5] Curating with Claude...")
    article_block    = build_article_block(rss_articles, newsapi_items, crunchbase_rounds)
    newsletter_block = build_newsletter_block(newsletter_emails)

    try:
        digest = curate_with_claude(article_block, newsletter_block, anthropic_key, timezone)
    except Exception as e:
        print(f"\nERROR: Claude curation failed — {e}")
        traceback.print_exc()
        sys.exit(1)

    source_counts = {
        "RSS articles":       len(rss_articles),
        "NewsAPI":            len(newsapi_items),
        "Crunchbase rounds":  len(crunchbase_rounds),
        "Gmail newsletters":  len(newsletter_emails),
    }

    # ---- Send or print -----------------------------------------------------
    if dry_run:
        print("\n" + "=" * 60)
        print("DRY RUN — Healthcare VC Daily Digest:")
        print("=" * 60)
        print(digest)
        print("=" * 60)
        print(f"\nSources: {source_counts}")
        print("Dry run complete. No email sent.")
    else:
        try:
            send_news_email(gmail_service, from_email, to_email, digest, source_counts, timezone)
        except Exception as e:
            print(f"\nERROR: Failed to send email — {e}")
            traceback.print_exc()
            sys.exit(1)

    print("\nDone!")


def auth_only() -> None:
    """Run Gmail OAuth and cache the token."""
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.oauth2.credentials  import Credentials
    from google.auth.transport.requests import Request

    credentials_file = os.getenv(
        "GMAIL_CREDENTIALS_FILE",
        os.path.join(_HERE, "..", "daily_summary", "credentials.json")
    )
    token_file = os.getenv(
        "GMAIL_TOKEN_FILE",
        os.path.join(_HERE, "..", "daily_summary", "token.json")
    )
    SCOPES = [
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.send",
    ]

    creds = None
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow  = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_file, "w") as f:
            f.write(creds.to_json())
    print("Gmail authentication successful.")


def _count_sources(articles: list[dict]) -> int:
    return len({a.get("source") for a in articles})


def main() -> None:
    parser = argparse.ArgumentParser(description="Healthcare VC News Aggregator")
    parser.add_argument("--test", action="store_true", help="Dry run — no email sent")
    parser.add_argument("--auth", action="store_true", help="Run Gmail OAuth only")
    args = parser.parse_args()

    if args.auth:
        auth_only()
    else:
        run(dry_run=args.test)


if __name__ == "__main__":
    main()
