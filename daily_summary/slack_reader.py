"""
slack_reader.py
Fetches today's Slack messages from all channels, private groups, and DMs
that the authenticated user has access to.

Requires a User OAuth Token (xoxp-...) with scopes:
  channels:history, channels:read, groups:history, groups:read,
  im:history, im:read, mpim:history, mpim:read, users:read
"""

from datetime import datetime, timedelta
import pytz
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# Message subtypes that are system noise, not real messages
SKIP_SUBTYPES = {
    "channel_join", "channel_leave", "channel_archive", "channel_unarchive",
    "channel_purpose", "channel_name", "channel_topic",
    "group_join", "group_leave", "group_archive", "group_unarchive",
    "bot_message", "bot_add", "bot_remove",
    "file_comment", "pinned_item",
}


def get_today_slack_messages(
    token: str, timezone_str: str = "America/New_York"
) -> tuple[list[dict], str]:
    """
    Fetch all Slack messages sent today across every conversation the user
    is a member of (public channels, private channels, DMs, group DMs).

    Returns:
        (messages, user_id)
        messages: list of dicts with keys:
            channel, channel_id, is_dm, is_group_dm, sender, sender_id,
            text, time, ts, is_mention, is_from_user, thread_ts, reply_count
        user_id: the authenticated user's Slack user ID
    """
    client = WebClient(token=token)

    # Determine the start of today in the user's timezone (as a Unix timestamp)
    tz = pytz.timezone(timezone_str)
    today_start = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    oldest_ts = str(today_start.timestamp())

    # Identify the authenticated user
    try:
        auth = client.auth_test()
        user_id  = auth["user_id"]
        team_id  = auth.get("team_id", "")
    except SlackApiError as e:
        raise RuntimeError(f"Slack authentication failed: {e.response['error']}")

    # Build a user-name cache to avoid repeated API calls
    _user_cache: dict[str, str] = {}

    def resolve_name(uid: str) -> str:
        if not uid:
            return "Unknown"
        if uid not in _user_cache:
            try:
                info = client.users_info(user=uid)
                profile = info["user"]["profile"]
                _user_cache[uid] = profile.get("display_name") or profile.get("real_name") or uid
            except Exception:
                _user_cache[uid] = uid
        return _user_cache[uid]

    # Fetch every conversation the user is a member of
    conversations: list[dict] = []
    cursor = None
    while True:
        try:
            kwargs = dict(
                types="public_channel,private_channel,mpim,im",
                exclude_archived=True,
                limit=200,
            )
            if cursor:
                kwargs["cursor"] = cursor
            resp = client.conversations_list(**kwargs)
            conversations.extend(resp.get("channels", []))
            cursor = resp.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break
        except SlackApiError as e:
            print(f"  Warning: could not list Slack conversations: {e.response['error']}")
            break

    all_messages: list[dict] = []

    for conv in conversations:
        channel_id   = conv["id"]
        is_dm        = conv.get("is_im", False)
        is_group_dm  = conv.get("is_mpim", False)

        # Determine a human-readable channel name
        if is_dm:
            other_uid    = conv.get("user", "")
            channel_name = resolve_name(other_uid) if other_uid else "DM"
        else:
            channel_name = conv.get("name", channel_id)

        # Fetch messages sent since the start of today
        try:
            history = client.conversations_history(
                channel=channel_id,
                oldest=oldest_ts,
                limit=200,
            )
        except SlackApiError as e:
            err = e.response.get("error", "")
            if err not in ("not_in_channel", "channel_not_found", "missing_scope"):
                print(f"  Warning: could not read #{channel_name}: {err}")
            continue

        for msg in history.get("messages", []):
            subtype = msg.get("subtype", "")
            if subtype in SKIP_SUBTYPES:
                continue
            # Skip bot-only messages
            if msg.get("bot_id") and not msg.get("user"):
                continue

            sender_id   = msg.get("user", "")
            sender_name = resolve_name(sender_id) if sender_id else "Bot/App"
            text        = msg.get("text", "").strip()
            ts          = float(msg.get("ts", 0))
            msg_time    = datetime.fromtimestamp(ts, tz=tz)

            # Does the message @mention the authenticated user?
            is_mention    = f"<@{user_id}>" in text
            is_from_user  = sender_id == user_id
            thread_ts     = msg.get("thread_ts")
            reply_count   = msg.get("reply_count", 0)

            # Resolve any <@USERID> mentions in the text to readable names
            display_text = _resolve_mentions(text, client, _user_cache)

            all_messages.append({
                "channel":      channel_name,
                "channel_id":   channel_id,
                "is_dm":        is_dm,
                "is_group_dm":  is_group_dm,
                "sender":       sender_name,
                "sender_id":    sender_id,
                "text":         display_text,
                "time":         msg_time.strftime("%I:%M %p"),
                "ts":           ts,
                "is_mention":   is_mention,
                "is_from_user": is_from_user,
                "thread_ts":    thread_ts,
                "reply_count":  reply_count,
            })

    # Sort by timestamp so the summary reads chronologically
    all_messages.sort(key=lambda m: m["ts"])
    return all_messages, user_id


def get_week_slack_messages(
    token: str, timezone_str: str = "America/New_York"
) -> tuple[list[dict], str]:
    """
    Fetch all Slack messages from this week (Monday midnight through now).
    Same structure as get_today_slack_messages but covers Mon–Fri.
    """
    client = WebClient(token=token)

    tz = pytz.timezone(timezone_str)
    now = datetime.now(tz)
    monday = now - timedelta(days=now.weekday())
    monday_start = monday.replace(hour=0, minute=0, second=0, microsecond=0)
    oldest_ts = str(monday_start.timestamp())

    try:
        auth = client.auth_test()
        user_id = auth["user_id"]
    except SlackApiError as e:
        raise RuntimeError(f"Slack authentication failed: {e.response['error']}")

    _user_cache: dict[str, str] = {}

    def resolve_name(uid: str) -> str:
        if not uid:
            return "Unknown"
        if uid not in _user_cache:
            try:
                info = client.users_info(user=uid)
                profile = info["user"]["profile"]
                _user_cache[uid] = profile.get("display_name") or profile.get("real_name") or uid
            except Exception:
                _user_cache[uid] = uid
        return _user_cache[uid]

    conversations: list[dict] = []
    cursor = None
    while True:
        try:
            kwargs = dict(
                types="public_channel,private_channel,mpim,im",
                exclude_archived=True,
                limit=200,
            )
            if cursor:
                kwargs["cursor"] = cursor
            resp = client.conversations_list(**kwargs)
            conversations.extend(resp.get("channels", []))
            cursor = resp.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break
        except SlackApiError as e:
            print(f"  Warning: could not list Slack conversations: {e.response['error']}")
            break

    all_messages: list[dict] = []

    for conv in conversations:
        channel_id  = conv["id"]
        is_dm       = conv.get("is_im", False)
        is_group_dm = conv.get("is_mpim", False)

        if is_dm:
            other_uid    = conv.get("user", "")
            channel_name = resolve_name(other_uid) if other_uid else "DM"
        else:
            channel_name = conv.get("name", channel_id)

        try:
            history = client.conversations_history(
                channel=channel_id,
                oldest=oldest_ts,
                limit=500,
            )
        except SlackApiError as e:
            err = e.response.get("error", "")
            if err not in ("not_in_channel", "channel_not_found", "missing_scope"):
                print(f"  Warning: could not read #{channel_name}: {err}")
            continue

        for msg in history.get("messages", []):
            subtype = msg.get("subtype", "")
            if subtype in SKIP_SUBTYPES:
                continue
            if msg.get("bot_id") and not msg.get("user"):
                continue

            sender_id   = msg.get("user", "")
            sender_name = resolve_name(sender_id) if sender_id else "Bot/App"
            text        = msg.get("text", "").strip()
            ts          = float(msg.get("ts", 0))
            msg_time    = datetime.fromtimestamp(ts, tz=tz)

            is_mention   = f"<@{user_id}>" in text
            is_from_user = sender_id == user_id
            thread_ts    = msg.get("thread_ts")
            reply_count  = msg.get("reply_count", 0)

            display_text = _resolve_mentions(text, client, _user_cache)

            all_messages.append({
                "channel":      channel_name,
                "channel_id":   channel_id,
                "is_dm":        is_dm,
                "is_group_dm":  is_group_dm,
                "sender":       sender_name,
                "sender_id":    sender_id,
                "text":         display_text,
                "time":         msg_time.strftime("%a %I:%M %p"),  # include day for weekly
                "ts":           ts,
                "is_mention":   is_mention,
                "is_from_user": is_from_user,
                "thread_ts":    thread_ts,
                "reply_count":  reply_count,
            })

    all_messages.sort(key=lambda m: m["ts"])
    return all_messages, user_id


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_mentions(text: str, client: WebClient, cache: dict) -> str:
    """Replace <@USERID> tokens with @DisplayName for readability."""
    import re

    def replace(match):
        uid = match.group(1)
        if uid not in cache:
            try:
                info = client.users_info(user=uid)
                profile = info["user"]["profile"]
                cache[uid] = profile.get("display_name") or profile.get("real_name") or uid
            except Exception:
                cache[uid] = uid
        return f"@{cache[uid]}"

    return re.sub(r"<@([A-Z0-9]+)>", replace, text)
