"""
summarizer.py
Formats email and Slack data and asks Claude to produce a prioritized
daily digest summary.
"""

from datetime import datetime, timedelta
import pytz
import anthropic

# Model to use for summarization.
# claude-3-5-haiku is cost-effective for a daily task (~$0.01–$0.05/day).
# Swap for claude-3-5-sonnet or claude-opus-4-5 for higher quality.
CLAUDE_MODEL = "claude-haiku-4-5-20251001"

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

PRIORITY HIERARCHY — surface and escalate these first, in this order:
1. URGENT: Any communication from Brett Shaheen — always treat as top priority regardless of topic
2. HIGH: Investors requesting information, data, or updates
3. HIGH: Communications from Redesign Health department leaders — especially Sam Lynch, \
but also any other department heads or senior leaders at Redesign Health
4. HIGH: Any communication from Nathan Mapp
5. ELEVATED: Any message — email or Slack — related to transactions that are time-sensitive, \
have approaching deadlines, require sign-off, or involve deal timing

When listing items in Action Required or Important FYI, always place the above priority \
contacts and topics at the top of each section, labeled with 🚨 if from Brett Shaheen \
or ⏰ if time-sensitive/deadline-driven.

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
WHAT they need, and WHICH channel (email/Slack channel name). \
Priority contacts (Brett Shaheen, investors, Sam Lynch, Redesign Health leaders, Nathan Mapp) \
and time-sensitive transactions must appear first with appropriate emoji labels.
If nothing requires action, write: *Nothing requires action today.*

## 🟡 Important — FYI
Key information the user should be aware of but doesn't need to act on right now. \
Decisions made, important news, things that affect the user. \
Apply the same priority ordering — priority contacts and deadline-sensitive items first.
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


# ---------------------------------------------------------------------------
# Weekly digest
# ---------------------------------------------------------------------------

def format_emails_for_claude_weekly(emails: list[dict]) -> str:
    """Render a week's worth of emails into a plain-text block for Claude."""
    if not emails:
        return "No emails received this week."

    received = [e for e in emails if not e["is_sent"]]
    sent     = [e for e in emails if e["is_sent"]]

    lines = [f"=== EMAILS THIS WEEK: {len(received)} received, {len(sent)} sent ===\n"]

    for i, e in enumerate(received, 1):
        priority_tag = "[DIRECT TO YOU]" if e["is_direct"] else "[CC/BCC]"
        lines.append(
            f"--- Email {i} {priority_tag} ---\n"
            f"From:    {e['from']}\n"
            f"Date:    {e['date']}\n"
            f"Subject: {e['subject']}\n"
            f"Snippet: {e['body'][:400]}\n"
        )

    full_text = "\n".join(lines)
    if len(full_text) > MAX_EMAIL_CHARS:
        full_text = full_text[:MAX_EMAIL_CHARS] + "\n\n[... additional emails truncated ...]"
    return full_text


def format_slack_for_claude_weekly(messages: list[dict], user_id: str) -> str:
    """Render a week's worth of Slack messages into a plain-text block for Claude."""
    if not messages:
        return "No Slack messages this week."

    channels: dict[str, list[dict]] = {}
    for msg in messages:
        channels.setdefault(msg["channel"], []).append(msg)

    mention_count = sum(1 for m in messages if m["is_mention"])
    dm_count      = sum(1 for m in messages if m["is_dm"])

    lines = [
        f"=== SLACK THIS WEEK: {len(messages)} messages across {len(channels)} conversations "
        f"({mention_count} mentions of you, {dm_count} DM messages) ===\n"
    ]

    for channel, msgs in sorted(channels.items(), key=lambda kv: not kv[1][0]["is_dm"]):
        msg_type = "DM" if msgs[0]["is_dm"] else ("Group DM" if msgs[0]["is_group_dm"] else "Channel")
        lines.append(f"\n--- {msg_type}: {channel} ({len(msgs)} messages this week) ---")
        for msg in msgs[:60]:
            tags = []
            if msg["is_mention"]:
                tags.append("MENTIONED YOU")
            if msg["is_from_user"]:
                tags.append("YOU")
            tag_str = f" [{', '.join(tags)}]" if tags else ""
            lines.append(f"  {msg['time']} {msg['sender']}{tag_str}: {msg['text'][:300]}")
            if msg["reply_count"] > 0:
                lines.append(f"    -> {msg['reply_count']} replies in thread")

    full_text = "\n".join(lines)
    if len(full_text) > MAX_SLACK_CHARS:
        full_text = full_text[:MAX_SLACK_CHARS] + "\n\n[... additional messages truncated ...]"
    return full_text


def summarize_week_with_claude(
    emails_text: str,
    slack_text: str,
    api_key: str,
    user_email: str,
    timezone_str: str = "America/New_York",
) -> str:
    """
    Call Claude to produce a structured weekly digest covering the full Mon-Fri window.
    Returns the summary as a markdown string.
    """
    client = anthropic.Anthropic(api_key=api_key)

    tz    = pytz.timezone(timezone_str)
    now   = datetime.now(tz)
    today = now.strftime("%A, %B %d, %Y")

    prompt = f"""You are an expert executive assistant. Today is {today} (Friday). \
The user's email address is {user_email}.

Your task: review the FULL WEEK of email and Slack activity below and produce a \
clear, strategic weekly digest. This is a Friday wrap-up — focus on the big picture, \
not individual messages.

PRIORITY HIERARCHY — surface and escalate these first, in this order:
1. URGENT: Any communication from Brett Shaheen — always treat as top priority regardless of topic
2. HIGH: Investors requesting information, data, or updates
3. HIGH: Communications from Redesign Health department leaders — especially Sam Lynch, \
but also any other department heads or senior leaders at Redesign Health
4. HIGH: Any communication from Nathan Mapp
5. ELEVATED: Any message — email or Slack — related to transactions that are time-sensitive, \
have approaching deadlines, require sign-off, or involve deal timing

When listing items, label with 🚨 if from Brett Shaheen or ⏰ if time-sensitive/deadline-driven. \
Priority contacts and topics must appear first in each section.

Focus on:
- Unresolved action items that still need a response or follow-up
- Important decisions that were made this week
- Key themes and recurring topics across the week
- Significant relationships/conversations with priority contacts
- Anything that needs to carry over into next week

Skip:
- Automated notifications and system messages
- Low-value chatter
- Fully resolved threads with no follow-up needed

---
{emails_text}

---
{slack_text}

---

Produce the weekly digest using EXACTLY this structure (use markdown):

## 🚨 Still Needs Your Attention
Open items from this week that have NOT been resolved and require follow-up. \
Priority contacts first. Include WHO it's from, WHAT is needed, and WHEN it came in.
If nothing is outstanding, write: *No outstanding items — great week!*

## ✅ Key Wins & Decisions This Week
Important things that were accomplished, resolved, or decided this week. \
Keep it high-level — what moved forward?
If nothing notable, write: *No major decisions this week.*

## 🔁 Carry Into Next Week
Threads, relationships, or topics that need to continue next week. \
Think of this as your Monday morning briefing prep.
If nothing to carry over, write: *Clean slate heading into next week.*

## 👥 Key People This Week
Brief summary of notable activity from your priority contacts (Brett Shaheen, investors, \
Sam Lynch / RH leaders, Nathan Mapp) and any other people who were especially active.
If none of them were active, write: *No activity from priority contacts this week.*

## 📊 Week at a Glance
- Emails received: X (X direct, X CC'd)
- Emails sent: X
- Slack messages: X across X channels/DMs
- Times @mentioned: X
- Busiest day: [day]

Keep bullet points tight. No long prose paragraphs. This should take 2 minutes to read."""

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}],
    )

    return response.content[0].text


# ---------------------------------------------------------------------------
# Monday morning calendar briefing
# ---------------------------------------------------------------------------

def format_emails_for_claude_lastweek(emails: list[dict]) -> str:
    """Render last week's emails as a brief context block for the Monday prompt."""
    if not emails:
        return "No significant emails from last week."

    received = [e for e in emails if not e["is_sent"]]
    sent     = [e for e in emails if e["is_sent"]]

    lines = [f"=== LAST WEEK'S EMAILS: {len(received)} received, {len(sent)} sent ===\n"]

    for i, e in enumerate(received, 1):
        priority_tag = "[DIRECT TO YOU]" if e["is_direct"] else "[CC/BCC]"
        lines.append(
            f"--- Email {i} {priority_tag} ---\n"
            f"From:    {e['from']}\n"
            f"Date:    {e['date']}\n"
            f"Subject: {e['subject']}\n"
            f"Snippet: {e['body'][:400]}\n"
        )

    full_text = "\n".join(lines)
    if len(full_text) > MAX_EMAIL_CHARS:
        full_text = full_text[:MAX_EMAIL_CHARS] + "\n\n[... additional emails truncated ...]"
    return full_text


def summarize_monday_briefing_with_claude(
    calendar_text: str,
    last_week_emails_text: str,
    last_week_slack_text: str,
    api_key: str,
    user_email: str,
    timezone_str: str = "America/New_York",
) -> str:
    """
    Call Claude to produce a Monday morning briefing that covers:
    - The week ahead (calendar)
    - Carry-overs and context from last week (email + Slack)
    - A skeleton of top priorities for the week
    Returns the briefing as a markdown string.
    """
    client = anthropic.Anthropic(api_key=api_key)

    tz    = pytz.timezone(timezone_str)
    now   = datetime.now(tz)
    today = now.strftime("%A, %B %d, %Y")

    # Date range for the upcoming week (Mon-Fri)
    week_end = now + timedelta(days=4)
    week_range = f"{now.strftime('%B %d')} - {week_end.strftime('%B %d, %Y')}"

    prompt = f"""You are an expert executive assistant preparing a Monday morning briefing \
for {user_email}. Today is {today}. The week ahead is {week_range}.

Your job is to set the user up for a great week. Be strategic, concise, and forward-looking.

PRIORITY HIERARCHY — flag these people/topics prominently throughout:
1. URGENT (🚨): Any communication or meeting involving Brett Shaheen
2. HIGH: Investor meetings, investor requests for information, investor-related prep
3. HIGH: Redesign Health department leaders — especially Sam Lynch and other senior RH leaders
4. HIGH: Nathan Mapp
5. ELEVATED (⏰): Time-sensitive transactions, approaching deadlines, deal timing

---
UPCOMING WEEK CALENDAR:
{calendar_text}

---
LAST WEEK'S EMAIL CONTEXT (for carry-overs and pending threads):
{last_week_emails_text}

---
LAST WEEK'S SLACK CONTEXT:
{last_week_slack_text}

---

Produce the Monday briefing using EXACTLY this structure (use markdown):

## 📅 Week Ahead — {week_range}
List every meeting or event from the calendar, grouped by day. For each meeting, note:
- What it is and who is involved
- Whether it likely requires preparation (and what kind)
Flag with 🚨 any meetings with Brett Shaheen or investor-related meetings.
Flag with ⏰ any meetings tied to deal timelines or deadlines.
If no events, write: *No calendar events found for this week.*

## 🎯 Top Priorities This Week
A numbered list of 3–6 concrete priorities the user should focus on this week, \
based on the calendar AND the carry-overs from last week. Think strategically: \
what actually moves the needle? Priority contacts and time-sensitive deals go first.
Label each with the relevant person/deal name.

## 📋 Prep Required
For each meeting that requires preparation (especially investor meetings, \
Brett Shaheen meetings, or board/leadership meetings), provide a brief prep checklist:
- What materials or data to pull together
- What questions or asks to anticipate
- Any open threads from last week that are relevant
If no prep is needed, write: *No significant prep required this week.*

## 🔁 Carry-Overs from Last Week
Unresolved threads, pending responses, or open items from last week that need \
attention this week. Priority contacts first. Include WHO it involves and WHAT is needed.
If nothing is outstanding, write: *Clean slate — no carry-overs.*

## 📊 Week at a Glance
- Meetings this week: X
- Meetings requiring prep: X
- Carry-overs from last week: X
- Top priority contact this week: [name or "None flagged"]

Keep everything tight and scannable. This should take 3 minutes to read and \
leave the user ready to attack the week."""

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=3500,
        messages=[{"role": "user", "content": prompt}],
    )

    return response.content[0].text
