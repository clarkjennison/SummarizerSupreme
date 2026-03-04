# Summarizer Supreme — Daily Digest Bot

Fetches your Gmail and Slack messages each day, summarizes them with Claude AI, and delivers a structured digest to your inbox every weekday at **5:30 PM ET**.

---

## What you get

Every evening you receive a styled HTML email with four sections:

| Section | Contents |
|---|---|
| 🔴 **Action Required** | Messages that need a reply or action from you |
| 🟡 **Important — FYI** | Key info you should know but don't need to act on |
| 💬 **Notable Conversations** | Summaries of meaningful discussions |
| 📊 **Day at a Glance** | Quick stats (email count, Slack mentions, DMs) |

---

## What you need before starting

- A Windows PC (the scheduler uses Windows Task Scheduler)
- A Gmail or Google Workspace account
- An [Anthropic API key](https://console.anthropic.com/) — free to create, costs ~$0.01–0.05/day to run
- A Slack workspace *(optional — skip Step 4 if you only want email)*

---

## Setup — Step by Step

### Step 1 — Install Python

1. Download Python 3.11+ from [python.org/downloads](https://www.python.org/downloads/)
2. Run the installer
3. ⚠️ **On the first screen, check "Add python.exe to PATH"** before clicking Install Now — this is easy to miss and required

Verify it worked by opening a terminal and running:
```
python --version
```

---

### Step 2 — Download this project

Download or clone the repo and place the `daily_summary` folder somewhere convenient, e.g.:
```
C:\Users\YourName\daily_summary\
```

---

### Step 3 — Create your `.env` file

In the `daily_summary` folder, copy the example config:
```
copy .env.example .env
```

Open `.env` in Notepad — you'll fill in the values as you complete the steps below.

---

### Step 4 — Get your Anthropic API key

1. Go to [console.anthropic.com](https://console.anthropic.com/) and sign in (or create a free account)
2. Click **API Keys** in the left sidebar → **Create Key**
3. Give it a name (e.g. `daily-summary-bot`) and copy the key
4. Paste it into `.env` as `ANTHROPIC_API_KEY`

> ⚠️ Keep this key private — don't share it or commit it to GitHub. If it's ever exposed, rotate it immediately from the Anthropic console.

---

### Step 5 — Set up Gmail access

This gives the bot permission to read your emails and send the digest.

1. Go to [console.cloud.google.com](https://console.cloud.google.com/) and sign in with your Gmail/Workspace account
2. Click the project dropdown at the top → **New Project** → name it `daily-summary-bot` → **Create**
3. In the left sidebar: **APIs & Services → Library** → search **Gmail API** → **Enable**
4. Go to **APIs & Services → OAuth consent screen**
   - Choose **External** → **Create**
   - Fill in App name (`Daily Summary Bot`), your email for support and developer contact
   - Click **Save and Continue** through the remaining screens (no changes needed)
5. Go to **APIs & Services → Credentials → Create Credentials → OAuth client ID**
   - Application type: **Desktop app**
   - Name: anything → **Create**
6. Click **Download JSON** on the confirmation popup (or click the download icon next to your credential in the list)
7. Rename the file to `credentials.json` and place it in the `daily_summary` folder
8. Set these values in `.env`:
   ```
   SUMMARY_FROM_EMAIL=you@yourdomain.com
   SUMMARY_TO_EMAIL=you@yourdomain.com
   ```

---

### Step 6 — Set up Slack access *(optional)*

Skip this step if you only want email summaries. You can always add it later.

> ⚠️ **Important: When Slack asks about "token rotation", skip it / close that dialog. Do NOT opt in.** Token rotation removes the standard install button and makes setup significantly harder.

1. Go to [api.slack.com/apps](https://api.slack.com/apps) → **Create New App → From scratch**
2. Name it `Daily Summary Bot`, select your workspace → **Create App**
3. In the left sidebar go to **OAuth & Permissions**
4. Scroll down to **User Token Scopes** (not Bot Token Scopes — important!) and add all of these:

   | Scope | What it does |
   |---|---|
   | `channels:history` | Read public channel messages |
   | `channels:read` | See list of public channels |
   | `groups:history` | Read private channel messages |
   | `groups:read` | See list of private channels |
   | `im:history` | Read direct messages |
   | `im:read` | See list of DMs |
   | `mpim:history` | Read group DMs |
   | `mpim:read` | See list of group DMs |
   | `users:read` | Look up user names |

5. Scroll back to the top of the page and click **Install to Workspace** → **Allow**
6. The **User OAuth Token** (starting with `xoxp-`) will appear at the top of the page — copy it
7. Paste it into `.env` as `SLACK_USER_TOKEN`

---

### Step 7 — Install dependencies and register the scheduler

Open **PowerShell** and run the following (replace the path with wherever you put the folder):

```powershell
# Navigate to the folder
Set-Location "C:\Users\YourName\daily_summary"

# Create virtual environment
python -m venv venv

# Install dependencies
.\venv\Scripts\python.exe -m pip install -r requirements.txt

# Authenticate Gmail (a browser window will open — sign in and click Allow)
.\venv\Scripts\python.exe main.py --auth

# Register the Task Scheduler job (runs Mon-Fri at 5:30 PM)
$action = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument '/c "C:\Users\YourName\daily_summary\run.bat"'
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 5:30PM
$settings = New-ScheduledTaskSettingsSet -RunOnlyIfNetworkAvailable
Register-ScheduledTask -TaskName 'DailySummaryBot' -Action $action -Trigger $trigger -Settings $settings -Force
```

> ⚠️ Make sure your PC is **on and not sleeping** at 5:30 PM or the task won't fire.

---

### Step 8 — Test it

Send a real digest right now to make sure everything works:

```powershell
Set-Location "C:\Users\YourName\daily_summary"

# Preview in console only (no email sent)
.\venv\Scripts\python.exe main.py --test

# Send a real digest email now
.\venv\Scripts\python.exe main.py
```

Check your inbox — you should receive the digest within a minute.

---

## Files

```
daily_summary/
├── main.py              # Entry point — orchestrates everything
├── gmail_reader.py      # Gmail OAuth + email fetching
├── slack_reader.py      # Slack API + message fetching
├── summarizer.py        # Claude AI summarization + priority rules
├── email_sender.py      # Styled HTML email via Gmail API
├── requirements.txt     # Python dependencies
├── .env.example         # Configuration template (copy to .env)
├── run.bat              # Called by Task Scheduler each day
└── logs/
    └── daily_summary.log  # Appended on every run
```

> `.env`, `credentials.json`, `token.json`, and `venv/` are excluded from the repo — each person needs their own.

---

## Customization

### Change the delivery time
Open **Task Scheduler** (search in Start menu), find `DailySummaryBot`, and edit the trigger time.

### Run on weekends
In the PowerShell setup command above, add `Saturday,Sunday` to the `-DaysOfWeek` list.

### Send to a different email address
Set `SUMMARY_TO_EMAIL` in `.env` to any email address.

### Use a smarter Claude model (higher quality, higher cost)
Open `summarizer.py` and change `CLAUDE_MODEL`:
```python
CLAUDE_MODEL = "claude-sonnet-4-5"   # Smarter, ~5x more expensive
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `Python not found` | Re-run the Python installer and check **"Add python.exe to PATH"** |
| `credentials.json not found` | Make sure the file is in the `daily_summary` folder (not a subfolder) |
| `Gmail auth failed / invalid_grant` | Delete `token.json` and re-run `.\venv\Scripts\python.exe main.py --auth` |
| `Slack error: missing_scope` | Re-check Step 6 — make sure you added **User Token Scopes**, not Bot Token Scopes |
| Slack Install button missing | You may have opted into token rotation — delete the app and recreate it (skip token rotation) |
| No email at 5:30 PM | Check `logs\daily_summary.log`; make sure your PC is on and not sleeping |
| Summary is empty | No non-automated messages arrived today, or your PC clock is off |

---

## Logs

Every run appends to `logs\daily_summary.log`. Check this file first if anything seems off:

```powershell
Get-Content "logs\daily_summary.log" -Tail 50
```
