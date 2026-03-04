# Summarizer Supreme — Daily Intelligence Bot

An automated email digest system that reads your Gmail, Slack, and Google Calendar and sends you a daily AI-generated briefing via email.

Built with Python + Claude (Anthropic) and runs on Windows Task Scheduler.

---

## What It Does

### 📬 Daily Digest (Mon–Fri, 5:30 PM)
Pulls the day's emails and Slack messages, runs them through Claude, and emails a structured summary including:
- **🔴 Action Required** — items needing a response or decision
- **🟡 Important FYI** — notable updates, no action needed
- **💬 Notable Conversations** — key threads worth tracking
- **📊 Day at a Glance** — counts of emails, Slack messages, @mentions, DMs

Priority contacts are flagged automatically:
- 🚨 Brett Shaheen (always urgent)
- Investors requesting information
- Redesign Health department leaders (esp. Sam Lynch)
- Nathan Mapp (Controller)
- ⏰ Time-sensitive transactions / approaching deadlines

### 📅 Monday Morning Briefing (Mondays, 8:00 AM)
Combines Google Calendar + prior week's emails + Slack into a week-ahead planner:
- **📅 Week Ahead** — every meeting with prep notes and key attendees
- **🎯 Top Priorities** — AI-ranked action items for the week
- **📋 Prep Required** — meetings that need deck/doc/data prep flagged
- **🔁 Carry-Overs** — unresolved items from last week
- **📊 Week at a Glance** — high-level stats

### 📊 Friday Wrap-Up (Fridays, 5:31 PM)
End-of-week digest with a retrospective view of the full week's activity.

---

## Architecture

```
daily_summary/
├── main.py            # Entry point — --monday, --weekly, --test flags
├── summarizer.py      # Claude prompt logic & model config
├── gmail_reader.py    # Gmail OAuth + fetch (today's emails or last week's)
├── slack_reader.py    # Slack SDK — channels, DMs, @mentions
├── calendar_reader.py # Google Calendar API — week-ahead events
├── email_sender.py    # Gmail send + HTML rendering
├── .env               # API keys & config (gitignored)
├── credentials.json   # Google OAuth client (gitignored)
├── token.json         # Cached Google OAuth token (gitignored)
└── venv/              # Python 3.14 virtualenv (gitignored)
```

---

## Data Sources

| Source | What's Pulled | Auth Method |
|--------|--------------|-------------|
| Gmail | Inbox + Sent (today or last week) | OAuth 2.0 |
| Slack | All channels + DMs + @mentions | User OAuth Token (`xoxp-`) |
| Google Calendar | Upcoming week's events | OAuth 2.0 (shared with Gmail) |

---

## Setup

### Prerequisites
- Python 3.10+
- Google Cloud project with Gmail + Calendar APIs enabled
- Slack app with User Token Scopes (see below)
- Anthropic API key

### Google OAuth
1. Create a project at [console.cloud.google.com](https://console.cloud.google.com)
2. Enable Gmail API + Google Calendar API
3. Create OAuth 2.0 credentials → Download as `credentials.json`
4. Run `python main.py --auth` to complete the OAuth flow and cache `token.json`

### Slack App
Create a Slack app at [api.slack.com/apps](https://api.slack.com/apps) with these **User Token Scopes**:

```
channels:read      channels:history
groups:read        groups:history
im:read            im:history
mpim:read          mpim:history
users:read
```

Install to workspace → copy the `xoxp-` User OAuth Token into `.env`.

### Environment Variables (`.env`)
```env
ANTHROPIC_API_KEY=sk-ant-...
SUMMARY_FROM_EMAIL=you@company.com
SUMMARY_TO_EMAIL=you@company.com
GMAIL_CREDENTIALS_FILE=credentials.json
GMAIL_TOKEN_FILE=token.json
SLACK_USER_TOKEN=xoxp-...
TIMEZONE=America/New_York
```

### Install Dependencies
```bash
python -m venv venv
venv\Scripts\activate
pip install anthropic google-auth google-auth-oauthlib google-api-python-client slack-sdk python-dotenv pytz
```

---

## Running

```bash
# Daily digest (today's emails + Slack)
python main.py

# Monday briefing (calendar + last week context)
python main.py --monday

# Friday wrap-up
python main.py --weekly

# Dry run — prints output, no email sent
python main.py --test
python main.py --monday --test
```

---

## Scheduling (Windows Task Scheduler)

Three tasks are registered:

| Task Name | Schedule | Command |
|-----------|----------|---------|
| `DailySummaryBot` | Mon–Fri 5:30 PM | `python main.py` |
| `MondayBriefingBot` | Every Monday 8:00 AM | `python main.py --monday` |
| `WeeklySummaryBot` | Every Friday 5:31 PM | `python main.py --weekly` |

Logs written to `daily_summary/logs/`.

---

## Model

Uses `claude-haiku-4-5-20251001` — fast, cost-efficient, handles long email/Slack context windows well.

---

## Known Quirks (Windows)
- `load_dotenv(override=True)` required — Claude Code sets `ANTHROPIC_API_KEY=''` in the shell env
- Use `pytz` not `zoneinfo` — Windows Python has no IANA timezone data
- Set `sys.stdout.reconfigure(encoding="utf-8")` — Windows console is cp1252 and chokes on emoji
- Python may be at a non-standard path: `%LOCALAPPDATA%\Python\bin\python.exe`
