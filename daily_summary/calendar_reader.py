"""
calendar_reader.py
Authenticates with the Google Calendar API and fetches events for the
upcoming week (Mon–Sun starting from the next Monday, or this week if
called on a Monday).

Reuses the same OAuth credentials/token as gmail_reader.py — the token
is refreshed automatically by the google-auth library.
"""

from datetime import datetime, timedelta

import pytz
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Scopes that must be present — must match the list in gmail_reader.py
CALENDAR_SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
]


def get_calendar_service(credentials_file: str, token_file: str):
    """
    Return an authorised Google Calendar API service object.
    Shares the same token.json as Gmail so no second browser login is needed
    after the initial re-auth.
    """
    import os
    from google.oauth2.credentials import Credentials as _Creds

    # All required scopes (Gmail + Calendar) — must stay in sync with gmail_reader.py
    ALL_SCOPES = [
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/calendar.readonly",
    ]

    creds = None
    if os.path.exists(token_file):
        creds = _Creds.from_authorized_user_file(token_file, ALL_SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(credentials_file):
                raise FileNotFoundError(
                    f"Google credentials file not found: {credentials_file}\n"
                    "Please download it from Google Cloud Console."
                )
            flow = InstalledAppFlow.from_client_secrets_file(credentials_file, ALL_SCOPES)
            creds = flow.run_local_server(port=0)

        with open(token_file, "w") as f:
            f.write(creds.to_json())

    return build("calendar", "v3", credentials=creds)


def get_week_ahead_events(
    service,
    timezone_str: str = "America/New_York",
) -> list[dict]:
    """
    Fetch all calendar events for the upcoming Mon–Sun week.

    If called on a Monday, returns events for today through Sunday.
    If called any other day, returns events for the *next* Monday through Sunday.
    This way the Monday 8 AM briefing email always covers the week that is
    just starting.

    Returns a list of dicts with keys:
        title, start, end, start_dt, all_day, location,
        description, attendees, calendar, organizer,
        is_recurring, video_link
    """
    tz = pytz.timezone(timezone_str)
    now = datetime.now(tz)

    # Calculate the Monday of the target week
    days_until_monday = (7 - now.weekday()) % 7
    if days_until_monday == 0:
        # Today IS Monday — cover the full week starting today
        week_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        # Jump forward to next Monday
        week_start = (now + timedelta(days=days_until_monday)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

    week_end = week_start + timedelta(days=7)  # Sunday midnight

    time_min = week_start.isoformat()
    time_max = week_end.isoformat()

    events_result = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime",
            maxResults=100,
        )
        .execute()
    )

    raw_events = events_result.get("items", [])
    events: list[dict] = []

    for ev in raw_events:
        # --- Parse start/end ---
        start_raw = ev.get("start", {})
        end_raw   = ev.get("end", {})

        if "dateTime" in start_raw:
            start_dt = datetime.fromisoformat(start_raw["dateTime"]).astimezone(tz)
            end_dt   = datetime.fromisoformat(end_raw["dateTime"]).astimezone(tz)
            all_day  = False
            start_str = start_dt.strftime("%a %b %d, %I:%M %p")
            end_str   = end_dt.strftime("%I:%M %p")
            time_str  = f"{start_str} - {end_str}"
        else:
            # All-day event — date string only, no time component
            start_naive = datetime.fromisoformat(start_raw["date"])
            end_naive   = datetime.fromisoformat(end_raw["date"])
            start_dt    = tz.localize(start_naive)
            end_dt      = tz.localize(end_naive)
            all_day     = True
            time_str    = start_dt.strftime("%a %b %d (all day)")

        # --- Attendees ---
        attendees = [
            a.get("displayName") or a.get("email", "")
            for a in ev.get("attendees", [])
            if not a.get("self")  # exclude the calendar owner
        ]

        # --- Video / conference link ---
        video_link = ""
        conf = ev.get("conferenceData", {})
        for ep in conf.get("entryPoints", []):
            if ep.get("entryPointType") == "video":
                video_link = ep.get("uri", "")
                break

        # --- Organizer ---
        organizer = ev.get("organizer", {})
        organizer_str = organizer.get("displayName") or organizer.get("email", "")

        events.append({
            "title":        ev.get("summary", "(No title)"),
            "start":        time_str,
            "start_dt":     start_dt,
            "end_dt":       end_dt,
            "all_day":      all_day,
            "location":     ev.get("location", ""),
            "description":  (ev.get("description") or "")[:500],
            "attendees":    attendees,
            "organizer":    organizer_str,
            "calendar":     "primary",
            "is_recurring": bool(ev.get("recurringEventId")),
            "video_link":   video_link,
        })

    return events


def format_events_for_claude(events: list[dict]) -> str:
    """
    Render the upcoming week's calendar events as a plain-text block
    suitable for inclusion in the Claude prompt.
    """
    if not events:
        return "No calendar events found for the upcoming week."

    lines = [f"=== CALENDAR: {len(events)} events next week ===\n"]

    for i, ev in enumerate(events, 1):
        lines.append(f"--- Event {i} ---")
        lines.append(f"Title:     {ev['title']}")
        lines.append(f"When:      {ev['start']}")
        if ev["location"]:
            lines.append(f"Location:  {ev['location']}")
        if ev["attendees"]:
            attendee_str = ", ".join(ev["attendees"][:10])
            if len(ev["attendees"]) > 10:
                attendee_str += f" (+{len(ev['attendees']) - 10} more)"
            lines.append(f"Attendees: {attendee_str}")
        if ev["organizer"]:
            lines.append(f"Organizer: {ev['organizer']}")
        if ev["video_link"]:
            lines.append(f"Video:     {ev['video_link']}")
        if ev["description"]:
            lines.append(f"Notes:     {ev['description'][:300]}")
        lines.append("")

    return "\n".join(lines)
