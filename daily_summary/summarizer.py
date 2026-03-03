"""
summarizer.py
Formats email and Slack data and asks Claude to produce a prioritized
daily digest summary.
"""

from datetime import datetime
import pytz
import anthropic

# Model to use for summarization.
# claude-3-5-haiku is cost-effective for a daily task (~$0.01–$0.05/day).
# Swap for claude-3-5-sonnet or claude-opus-4-5 for higher quality.
CLAUDE_MODEL = "claude-3-5-haiku-20241022"

# Hard cap on tokens sent to Claude to avoid huge bills on busy days
MAX_EMAIL_CHARS  = 40_000
MAX_SLACK_CHARS  = 40_000


def format_emails_for_claude(emails: list[dict]) -> str:
    """Render emails into a plain-text block for the Claude prompt."""
    if not emails:
        return "No emails received today."

    received = [e for e in emails if not e["is_sent"]]
    sent     = [e for e in emails if e["is_sent"]]

    lines = [f"=== EMAILS: {len(received)} received, {len(sent)} sent today ===\n"]

    for i, e in enumerate(received, 1):
        priority_tag = "[DIRECT TO YOU]" if e["is_direct"] else "[CC/BCC]"
        lines.append(
            f"--- Email {i} {priority_tag} ---\n"
            f"From:    {e['from']}\n"
            f"To:      {e['to']}\n"
            f"Subject: {e['subject']}\n"
            f"Body:\n{e['body'][:1500]}\n"
        )

    if sent:
        lines.append(f"\n=== EMAILS YOU SENT TODAY ({len(sent)}) ===")
        for e in sent:
            lines.append(f"  To: {e['to']} | Subject: {e['subject']}")

    full_text = "\n".join(lines)
    # Trim to cap if needed
    if len(full_text) > MAX_EMAIL_CHARS:
        full_text = full_text[:MAX_EMAIL_CHARS] + "\n\n[... additional emails truncated ...]"
    return full_text


def format_slack_for_claude(messages: list[dict], user_id: str) -> str:
    """Render Slack messages into a plain-text block for the Claude prompt."""
    if not messages:
        return "No Slack messages today."

    # Group messages by channel
    channels: dict[str, list[dict]] = {}
    for msg in messages:
        channels.setdefault(msg["channel"], []).append(msg)

    mention_count = sum(1 for m in messages if m["is_mention"])
    dm_count      = sum(1 for m in messages if m["is_dm"])

    lines = [
        f"=== SLACK: {len(messages)} messages across {len(channels)} conversations "
        f"({mention_count} mentions of you, {dm_count} DM messages) ===\n"
    ]

    # DMs and group DMs first (highest priority)
    for channel, msgs in sorted(channels.items(), key=lambda kv: not kv[1][0]["is_dm"]):
        msg_type = "DM" if msgs[0]["is_dm"] else ("Group DM" if msgs[0]["is_group_dm"] else "Channel")
        lines.append(f"\n--- {msg_type}: {channel} ({len(msgs)} messages) ---")
        for msg in msgs[:40]:  # cap per channel
            tags = []
            if msg["is_mention"]:
                tags.append("MENTIONED YOU")
            if msg["is_from_user"]:
                tags.append("YOU")
            tag_str = f" [{', '.join(tags)}]" if tags else ""
            lines.append(f"  {msg['time']} {msg['sender']}{tag_str}: {msg['text'][:400]}")
            if msg["reply_count"] > 0:
                lines.append(f"    ↳ {msg['reply_count']} replies in thread")

    full_text = "\n".join(lines)
    if len(full_text) > MAX_SLACK_CHARS:
        full_text = full_text[:MAX_SLACK_CHARS] + "\n\n[... additional messages truncated ...]"
    return full_text


def summarize_with_claude(
    emails_text: str,
    slack_text: str,
    api_key: str,
    user_email: str,
    timezone_str: str = "America/New_York",
) -> str:
    """
    Call Claude to produce a structured, prioritized daily digest.
    Returns the summary as a markdown string.
    """
    client = anthropic.Anthropic(api_key=api_key)

    tz    = pytz.timezone(timezone_str)
    today = datetime.now(tz).strftime("%A, %B %d, %Y")

    prompt = f"""You are an expert executive assistant. Today is {today}. \
The user's email address is {user_email}.

Your task: review all of today's email and Slack activity below and produce a \
clear, scannable daily digest. Be concise — the user wants to catch up quickly.

Focus on:
- Messages that require a response or action from the user
- Important decisions, updates, or information the user should know
- Notable conversations and their outcomes
- Direct messages / DMs (these are highest priority)
- Any messages that @mention the user

Skip:
- Automated notifications, alerts, and system messages
- Low-value chatter and off-topic banter
- Things the user sent (they already know about those)

---
{emails_text}

---
{slack_text}

---

Produce the digest using EXACTLY this structure (use markdown):

## 🔴 Action Required
Items where the user must respond or do something. For each, include WHO sent it, \
WHAT they need, and WHICH channel (email/Slack channel name).
If nothing requires action, write: *Nothing requires action today.*

## 🟡 Important — FYI
Key information the user should be aware of but doesn't need to act on right now. \
Decisions made, important news, things that affect the user.
If nothing notable, write: *No important FYIs today.*

## 💬 Notable Conversations
Brief summaries of meaningful discussions that happened today. Group by topic or thread.
If nothing notable, write: *No notable conversations today.*

## 📊 Day at a Glance
- Emails received: X (X sent directly to you, X CC'd)
- Emails you sent: X
- Slack messages: X across X channels/DMs
- Times you were @mentioned: X
- Direct messages received: X

Keep bullet points tight. No long prose paragraphs."""

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )

    return response.content[0].text
