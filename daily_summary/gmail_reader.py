"""
gmail_reader.py
Handles Gmail OAuth authentication and fetches today's emails.
"""

import os
import base64
from datetime import datetime, timedelta
from email.utils import parseaddr

import pytz
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Scopes needed: read emails + send the summary email + read calendar
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar.readonly",
]

# Senders to skip even if not caught by Gmail's filters
SKIP_SENDERS = [
    "noreply", "no-reply", "donotreply", "do-not-reply",
    "notifications@", "updates@", "newsletter", "mailer-daemon",
    "postmaster", "alerts@", "digest@", "automated@",
]

SKIP_LABELS = {"CATEGORY_PROMOTIONS", "CATEGORY_SOCIAL", "CATEGORY_UPDATES", "SPAM"}


def get_gmail_service(credentials_file: str, token_file: str):
    """
    Authenticate with Gmail via OAuth and return an authorized service object.
    On first run this opens a browser window for login. Subsequent runs use
    the stored token.
    """
    creds = None

    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(credentials_file):
                raise FileNotFoundError(
                    f"Gmail credentials file not found: {credentials_file}\n"
                    "Please download it from Google Cloud Console and place it here.\n"
                    "See README.md for step-by-step instructions."
                )
            flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(token_file, "w") as f:
            f.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def get_today_emails(service, user_email: str, timezone_str: str = "America/New_York") -> list[dict]:
    """
    Fetch all non-automated emails received today.

    Returns a list of dicts with keys:
        id, subject, from, to, cc, date, body, snippet,
        is_direct (True if user is in To: field),
        is_sent   (True if user sent it)
    """
    tz = pytz.timezone(timezone_str)
    today_str = datetime.now(tz).strftime("%Y/%m/%d")

    # Build Gmail search query — excludes promotions/social/updates/spam categories
    query = (
        f"after:{today_str} "
        "-category:promotions "
        "-category:social "
        "-category:updates "
        "-in:spam "
        "-in:trash"
    )

    try:
        result = service.users().messages().list(
            userId="me", q=query, maxResults=200
        ).execute()
    except Exception as e:
        print(f"  Gmail API error listing messages: {e}")
        return []

    message_stubs = result.get("messages", [])
    emails = []

    for stub in message_stubs:
        try:
            msg = service.users().messages().get(
                userId="me", id=stub["id"], format="full"
            ).execute()

            label_ids = set(msg.get("labelIds", []))

            # Skip if categorized as promotions/social/updates/spam
            if label_ids & SKIP_LABELS:
                continue

            headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}

            subject  = headers.get("Subject", "(no subject)")
            from_raw = headers.get("From", "")
            to_raw   = headers.get("To", "")
            cc_raw   = headers.get("Cc", "")
            date_raw = headers.get("Date", "")

            _, from_email = parseaddr(from_raw)

            # Skip automated senders
            if any(skip in from_email.lower() for skip in SKIP_SENDERS):
                continue

            is_sent   = from_email.lower() == user_email.lower()
            is_direct = user_email.lower() in to_raw.lower()

            snippet = msg.get("snippet", "")
            body    = _extract_plain_text(msg["payload"]) or snippet

            emails.append({
                "id":        stub["id"],
                "subject":   subject,
                "from":      from_raw,
                "to":        to_raw,
                "cc":        cc_raw,
                "date":      date_raw,
                "snippet":   snippet,
                "body":      body[:3000],   # cap length sent to Claude
                "is_direct": is_direct,
                "is_sent":   is_sent,
                "labels":    list(label_ids),
            })

        except Exception as e:
            print(f"  Warning: could not parse email {stub['id']}: {e}")
            continue

    return emails


def get_week_emails(service, user_email: str, timezone_str: str = "America/New_York") -> list[dict]:
    """
    Fetch all non-automated emails received this week (Monday through now).
    Same structure as get_today_emails but covers the full Mon–Fri window.
    """
    tz = pytz.timezone(timezone_str)
    now = datetime.now(tz)
    monday = now - timedelta(days=now.weekday())
    monday_str = monday.strftime("%Y/%m/%d")

    query = (
        f"after:{monday_str} "
        "-category:promotions "
        "-category:social "
        "-category:updates "
        "-in:spam "
        "-in:trash"
    )

    try:
        result = service.users().messages().list(
            userId="me", q=query, maxResults=500
        ).execute()
    except Exception as e:
        print(f"  Gmail API error listing messages: {e}")
        return []

    message_stubs = result.get("messages", [])
    emails = []

    for stub in message_stubs:
        try:
            msg = service.users().messages().get(
                userId="me", id=stub["id"], format="full"
            ).execute()

            label_ids = set(msg.get("labelIds", []))
            if label_ids & SKIP_LABELS:
                continue

            headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}

            subject  = headers.get("Subject", "(no subject)")
            from_raw = headers.get("From", "")
            to_raw   = headers.get("To", "")
            cc_raw   = headers.get("Cc", "")
            date_raw = headers.get("Date", "")

            _, from_email = parseaddr(from_raw)

            if any(skip in from_email.lower() for skip in SKIP_SENDERS):
                continue

            is_sent   = from_email.lower() == user_email.lower()
            is_direct = user_email.lower() in to_raw.lower()

            snippet = msg.get("snippet", "")
            body    = _extract_plain_text(msg["payload"]) or snippet

            emails.append({
                "id":        stub["id"],
                "subject":   subject,
                "from":      from_raw,
                "to":        to_raw,
                "cc":        cc_raw,
                "date":      date_raw,
                "snippet":   snippet,
                "body":      body[:800],   # shorter cap for weekly volume
                "is_direct": is_direct,
                "is_sent":   is_sent,
                "labels":    list(label_ids),
            })

        except Exception as e:
            print(f"  Warning: could not parse email {stub['id']}: {e}")
            continue

    return emails


def get_last_week_emails(service, user_email: str, timezone_str: str = "America/New_York") -> list[dict]:
    """
    Fetch all non-automated emails from LAST week (the Mon–Sun before this week).
    Used by the Monday morning briefing to provide prior-week email context.

    Returns the same structure as get_today_emails / get_week_emails.
    """
    tz = pytz.timezone(timezone_str)
    now = datetime.now(tz)

    # Last Monday = this Monday minus 7 days
    this_monday = now - timedelta(days=now.weekday())
    last_monday = this_monday - timedelta(days=7)
    last_sunday = this_monday - timedelta(days=1)

    after_str  = last_monday.strftime("%Y/%m/%d")
    before_str = last_sunday.strftime("%Y/%m/%d")

    query = (
        f"after:{after_str} before:{before_str} "
        "-category:promotions "
        "-category:social "
        "-category:updates "
        "-in:spam "
        "-in:trash"
    )

    try:
        result = service.users().messages().list(
            userId="me", q=query, maxResults=500
        ).execute()
    except Exception as e:
        print(f"  Gmail API error listing last-week messages: {e}")
        return []

    message_stubs = result.get("messages", [])
    emails = []

    for stub in message_stubs:
        try:
            msg = service.users().messages().get(
                userId="me", id=stub["id"], format="full"
            ).execute()

            label_ids = set(msg.get("labelIds", []))
            if label_ids & SKIP_LABELS:
                continue

            headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}

            subject  = headers.get("Subject", "(no subject)")
            from_raw = headers.get("From", "")
            to_raw   = headers.get("To", "")
            cc_raw   = headers.get("Cc", "")
            date_raw = headers.get("Date", "")

            _, from_email = parseaddr(from_raw)

            if any(skip in from_email.lower() for skip in SKIP_SENDERS):
                continue

            is_sent   = from_email.lower() == user_email.lower()
            is_direct = user_email.lower() in to_raw.lower()

            snippet = msg.get("snippet", "")
            body    = _extract_plain_text(msg["payload"]) or snippet

            emails.append({
                "id":        stub["id"],
                "subject":   subject,
                "from":      from_raw,
                "to":        to_raw,
                "cc":        cc_raw,
                "date":      date_raw,
                "snippet":   snippet,
                "body":      body[:600],   # short cap — context only
                "is_direct": is_direct,
                "is_sent":   is_sent,
                "labels":    list(label_ids),
            })

        except Exception as e:
            print(f"  Warning: could not parse email {stub['id']}: {e}")
            continue

    return emails


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_plain_text(payload: dict) -> str:
    """Recursively extract the first plain-text body part from an email payload."""
    mime_type = payload.get("mimeType", "")

    if mime_type == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")

    for part in payload.get("parts", []):
        text = _extract_plain_text(part)
        if text:
            return text

    return ""
