"""
gmail_news_reader.py
Scans Gmail inbox for healthcare / VC newsletters and funding-related emails
received in the last 24 hours and extracts their content for the digest.
"""

import base64
import re
from datetime import datetime, timezone, timedelta
from email.utils import parseaddr

import pytz

# Gmail OAuth scopes (read-only — this module never sends)
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# ---------------------------------------------------------------------------
# Known newsletter senders to prioritize
# ---------------------------------------------------------------------------
NEWSLETTER_SENDERS = [
    # Domain fragments or full addresses
    "rockhealth.com",
    "endpoints.com", "endpts.com",
    "statnews.com",
    "medcitynews.com",
    "fiercehealthcare.com",
    "biopharmadive.com",
    "healthcaredive.com",
    "modernhealthcare.com",
    "healthcarefinancenews.com",
    "hitconsultant.net",
    "beckershospitalreview.com",
    "cbinsights.com",
    "pitchbook.com",
    "hlth.com",
    "axios.com",
    "morningbrew.com",
    "crunchbase.com",
    "fortune.com",
    "wsj.com",
    "ft.com",
]

# Subject-line keywords that signal a relevant email even from unknown senders
FUNDING_SUBJECT_KEYWORDS = [
    "raises", "raised", "funding", "series a", "series b", "series c",
    "seed round", "acquisition", "acquires", "merger", "ipo", "spac",
    "new fund", "fund close", "lp update", "portfolio update",
    "digital health", "healthtech", "health startup", "venture",
    "investment round", "valuation",
]

# Labels to always skip
SKIP_LABELS = {"SENT", "DRAFT", "SPAM", "TRASH"}


def get_newsletter_emails(
    service,
    user_email: str,
    lookback_hours: int = 24,
    timezone_str: str = "America/New_York",
) -> list[dict]:
    """
    Fetch newsletters and funding-related emails received in the last `lookback_hours`.

    Returns a list of dicts with keys:
        subject, from, from_email, date, body, snippet, is_newsletter, is_funding_related
    """
    tz = pytz.timezone(timezone_str)
    cutoff_utc = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    cutoff_date = cutoff_utc.strftime("%Y/%m/%d")

    query = (
        f"after:{cutoff_date} "
        "-in:sent -in:draft -in:spam -in:trash "
        "-category:social "
        "-category:updates"
    )

    try:
        result = service.users().messages().list(
            userId="me", q=query, maxResults=200
        ).execute()
    except Exception as e:
        print(f"  Gmail API error fetching news emails: {e}")
        return []

    stubs = result.get("messages", [])
    emails = []

    for stub in stubs:
        try:
            msg = service.users().messages().get(
                userId="me", id=stub["id"], format="full"
            ).execute()

            label_ids = set(msg.get("labelIds", []))
            if label_ids & SKIP_LABELS:
                continue

            headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
            subject   = headers.get("Subject", "")
            from_raw  = headers.get("From", "")
            date_raw  = headers.get("Date", "")

            _, from_email = parseaddr(from_raw)
            from_domain   = from_email.split("@")[-1].lower() if "@" in from_email else ""

            is_newsletter = any(
                sender in from_email.lower() or sender in from_domain
                for sender in NEWSLETTER_SENDERS
            )

            is_funding_related = any(
                kw in subject.lower() for kw in FUNDING_SUBJECT_KEYWORDS
            )

            # Only include newsletters OR emails with funding/deal subject lines
            if not is_newsletter and not is_funding_related:
                continue

            snippet = msg.get("snippet", "")
            body    = _extract_plain_text(msg["payload"]) or snippet
            body    = _clean_body(body)[:3000]

            emails.append({
                "subject":            subject,
                "from":               from_raw,
                "from_email":         from_email,
                "date":               date_raw,
                "body":               body,
                "snippet":            snippet,
                "is_newsletter":      is_newsletter,
                "is_funding_related": is_funding_related,
            })

        except Exception as e:
            print(f"  Warning: could not parse email {stub['id']}: {e}")
            continue

    return emails


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_plain_text(payload: dict) -> str:
    """Recursively extract the first plain-text body from an email payload."""
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


def _clean_body(text: str) -> str:
    """Remove common newsletter clutter (unsubscribe boilerplate, excessive whitespace)."""
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        line = line.strip()
        # Skip typical newsletter footer lines
        lower = line.lower()
        if any(skip in lower for skip in [
            "unsubscribe", "manage preferences", "view in browser",
            "you are receiving", "you received this", "sent to:",
            "privacy policy", "terms of service", "©", "all rights reserved",
        ]):
            continue
        cleaned.append(line)

    result = "\n".join(cleaned)
    # Collapse 3+ blank lines into 2
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()
