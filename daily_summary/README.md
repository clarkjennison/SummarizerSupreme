# Daily Summary Bot

Fetches your Gmail and Slack messages each day, summarizes them with Claude AI, and delivers a structured digest to your inbox every weekday at **5:30 PM ET**.

---

## What you get

Every evening you receive a styled email with four sections:

| Section | Contents |
|---|---|
| 🔴 **Action Required** | Messages that need a reply or action from you |
| 🟡 **Important — FYI** | Key info you should know but don't need to act on |
| 💬 **Notable Conversations** | Summaries of meaningful discussions |
| 📊 **Day at a Glance** | Quick stats (email count, Slack mentions, DMs) |

---

## Prerequisites

- Python 3.11 or later (`python --version`)
- A Gmail / Google Workspace account
- A Slack workspace (optional)
- An [Anthropic API key](https://console.anthropic.com/)

---

## Setup — Step by Step

### Step 1 — Clone / download this folder

Place the `daily_summary` folder anywhere you like, e.g.:
```
C:\Users\YourName\daily_summary\
```

### Step 2 — Create your `.env` file

```
copy .env.example .env
```

Open `.env` in Notepad and fill in your values. Details for each credential are in the sections below.

---

### Step 3 — Get a Gmail OAuth credential

1. Go to [Google Cloud Console](https://console.cloud.google.com/) and sign in with your Gmail account.
2. Create a new project (or use an existing one). Name it anything, e.g. `daily-summary-bot`.
3. In the left sidebar: **APIs & Services → Library**.
4. Search for **Gmail API** and click **Enable**.
5. Go to **APIs & Services → OAuth consent screen**.
   - Choose **External** and click **Create**.
   - Fill in App name (`Daily Summary Bot`), your email as support email, and your email again as developer contact.
   - Click **Save and Continue** through the scopes and test users pages (no changes needed).
6. Go to **APIs & Services → Credentials → Create Credentials → OAuth client ID**.
   - Application type: **Desktop app**.
   - Name: anything (e.g. `Daily Summary`).
   - Click **Create**, then **Download JSON**.
7. Rename the downloaded file to `credentials.json` and place it in the `daily_summary` folder.

> The first time you run the bot a browser window will open asking you to sign in and grant access. After that, the token is cached in `token.json` and no browser is needed.

---

### Step 4 — Get a Slack User OAuth Token (optional)

If you skip this step the bot will only summarize email.

1. Go to [api.slack.com/apps](https://api.slack.com/apps) and click **Create New App → From scratch**.
2. Name it `Daily Summary Bot` and pick your workspace.
3. In the left sidebar go to **OAuth & Permissions**.
4. Scroll to **User Token Scopes** (not Bot Token Scopes) and add:
   - `channels:history`
   - `channels:read`
   - `groups:history`
   - `groups:read`
   - `im:history`
   - `im:read`
   - `mpim:history`
   - `mpim:read`
   - `users:read`
5. Scroll up and click **Install to Workspace**, then **Allow**.
6. Copy the **User OAuth Token** (starts with `xoxp-`) and paste it into `.env` as `SLACK_USER_TOKEN`.

---

### Step 5 — Run setup

Double-click **`setup_scheduler.bat`** (or run it in a terminal):

```
setup_scheduler.bat
```

This will:
1. Create a Python virtual environment in `venv\`
2. Install all dependencies
3. Open a browser for Gmail OAuth (sign in once)
4. Register a Windows Task Scheduler job for **Mon–Fri at 5:30 PM**

---

### Step 6 — Test it

Open a terminal in the `daily_summary` folder:

```
# Activate the venv
venv\Scripts\activate

# Dry run — prints the summary, does NOT send email
python main.py --test

# Send a real summary right now
python main.py
```

---

## Files

```
daily_summary/
├── main.py              # Entry point — orchestrates everything
├── gmail_reader.py      # Gmail OAuth + email fetching
├── slack_reader.py      # Slack API + message fetching
├── summarizer.py        # Claude API summarization
├── email_sender.py      # Styled HTML email via Gmail API
├── requirements.txt     # Python dependencies
├── .env.example         # Configuration template
├── run.bat              # Called by Task Scheduler
├── setup_scheduler.bat  # One-time setup script
└── logs/
    └── daily_summary.log  # Created automatically
```

---

## Customization

### Change the summary time
Open **Task Scheduler** (search in Start menu), find `DailySummaryBot`, and edit the trigger time.

Or re-run `setup_scheduler.bat` after editing the `/st 17:30` value in the script.

### Run on weekends too
Edit `setup_scheduler.bat` and change `/d MON,TUE,WED,THU,FRI` to `/d MON,TUE,WED,THU,FRI,SAT,SUN`.

### Upgrade to a smarter Claude model
Open `summarizer.py` and change `CLAUDE_MODEL`:
```python
CLAUDE_MODEL = "claude-opus-4-5"   # Higher quality, higher cost
```

### Send the digest to a different email
Set `SUMMARY_TO_EMAIL` in `.env` to any email address.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `credentials.json not found` | Re-read Step 3; make sure the file is in the `daily_summary` folder |
| `Gmail auth failed / invalid_grant` | Delete `token.json` and run `python main.py --auth` again |
| `Slack error: missing_scope` | Make sure you added **User Token Scopes** (not Bot Token Scopes) in Step 4 |
| No email received at 5:30 PM | Check `logs\daily_summary.log`; ensure your PC is on and not sleeping |
| Empty summary | Your PC's clock may be off, or no non-automated messages arrived today |

---

## Logs

Every run appends to `logs\daily_summary.log`. Check this file if you suspect the bot isn't running.

```
type logs\daily_summary.log
```
