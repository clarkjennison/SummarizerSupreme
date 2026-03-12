"""
email_sender.py
Renders the curated markdown digest as a polished newsletter-style HTML email
and sends it via the Gmail API.
"""

import base64
import mimetypes
import os
import re
from datetime import datetime
from email.mime.application import MIMEApplication
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional

import pytz


# Brand colours for the newsletter
COLOUR_PRIMARY   = "#0f766e"   # teal-700  — header bar
COLOUR_ACCENT    = "#14b8a6"   # teal-400  — highlights
COLOUR_BG        = "#f0fdfa"   # teal-50   — page background
COLOUR_CARD_BG   = "#ffffff"
COLOUR_TEXT      = "#1e293b"   # slate-800
COLOUR_MUTED     = "#64748b"   # slate-500


def send_news_email(
    service,
    from_email: str,
    to_email:   str,
    digest_md:  str,
    source_counts: dict,
    timezone_str: str = "America/New_York",
    attachments: Optional[List[str]] = None,
) -> None:
    """Build and send the healthcare VC news digest email.

    Args:
        attachments: Optional list of file paths to attach to the email.
    """
    tz    = pytz.timezone(timezone_str)
    today = datetime.now(tz).strftime("%A, %B %d, %Y")

    subject   = f"Healthcare VC Daily — {today}"
    html_body = _render_html(digest_md, today, source_counts)
    text_body = digest_md

    if attachments:
        # mixed → alternative (text+html) + file parts
        msg = MIMEMultipart("mixed")
        alt = MIMEMultipart("alternative")
        alt.attach(MIMEText(text_body, "plain", "utf-8"))
        alt.attach(MIMEText(html_body, "html",  "utf-8"))
        msg.attach(alt)
        for path in attachments:
            msg.attach(_build_attachment(path))
    else:
        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText(text_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html",  "utf-8"))

    msg["Subject"] = subject
    msg["From"]    = from_email
    msg["To"]      = to_email

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
    service.users().messages().send(userId="me", body={"raw": raw}).execute()
    attach_note = f" with {len(attachments)} attachment(s)" if attachments else ""
    print(f"  News digest sent -> {to_email}{attach_note}")


# ---------------------------------------------------------------------------
# Markdown → polished HTML
# ---------------------------------------------------------------------------

# Emoji → section accent colour map
SECTION_COLOURS = {
    "💰": "#0d9488",   # teal   — funding
    "🏦": "#7c3aed",   # purple — new funds
    "🤝": "#2563eb",   # blue   — M&A
    "📈": "#059669",   # green  — IPO/markets
    "🔬": "#dc2626",   # red    — clinical
    "🌐": "#d97706",   # amber  — ecosystem
    "📊": "#475569",   # slate  — at a glance
}


def _render_html(md: str, date_str: str, source_counts: dict) -> str:
    body_html = _md_to_html(md)
    sources_html = _render_source_bar(source_counts)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Healthcare VC Daily</title>
</head>
<body style="margin:0;padding:0;background:{COLOUR_BG};font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;color:{COLOUR_TEXT};">
<table width="100%" cellpadding="0" cellspacing="0" style="background:{COLOUR_BG};padding:24px 0;">
  <tr><td align="center">
  <table width="640" cellpadding="0" cellspacing="0" style="max-width:640px;width:100%;">

    <!-- Masthead -->
    <tr>
      <td style="background:{COLOUR_PRIMARY};border-radius:10px 10px 0 0;padding:24px 32px;">
        <table width="100%" cellpadding="0" cellspacing="0">
          <tr>
            <td>
              <p style="margin:0;color:rgba(255,255,255,0.65);font-size:11px;
                        text-transform:uppercase;letter-spacing:1.5px;">Daily Digest</p>
              <h1 style="margin:4px 0 0;color:#fff;font-size:22px;font-weight:800;
                         letter-spacing:-0.5px;">Healthcare VC Daily</h1>
            </td>
            <td align="right" style="vertical-align:middle;">
              <span style="background:rgba(255,255,255,0.15);color:#fff;
                           font-size:12px;padding:6px 12px;border-radius:20px;
                           white-space:nowrap;">{date_str}</span>
            </td>
          </tr>
        </table>
      </td>
    </tr>

    <!-- Source bar -->
    {sources_html}

    <!-- Digest body -->
    <tr>
      <td style="background:{COLOUR_CARD_BG};padding:28px 32px;
                 border-radius:0 0 10px 10px;
                 box-shadow:0 2px 12px rgba(0,0,0,0.07);">
        {body_html}
      </td>
    </tr>

    <!-- Footer -->
    <tr>
      <td style="padding:20px 0 8px;text-align:center;
                 color:{COLOUR_MUTED};font-size:11px;line-height:1.6;">
        Healthcare VC Daily &bull; Powered by Claude AI &bull;
        Sources: RSS feeds, Gmail newsletters, NewsAPI, Crunchbase
      </td>
    </tr>

  </table>
  </td></tr>
</table>
</body>
</html>"""


def _render_source_bar(source_counts: dict) -> str:
    """Render a slim bar showing how many items came from each source."""
    if not source_counts:
        return ""
    parts = " &nbsp;|&nbsp; ".join(
        f"<strong>{v}</strong> {k}" for k, v in sorted(source_counts.items()) if v > 0
    )
    return f"""
    <tr>
      <td style="background:#e4f7f5;padding:10px 32px;border-bottom:1px solid #ccefeb;">
        <p style="margin:0;font-size:11px;color:{COLOUR_MUTED};">
          📡 &nbsp;{parts}
        </p>
      </td>
    </tr>"""


def _md_to_html(md: str) -> str:
    """Convert the curator's markdown output to styled HTML."""
    lines   = md.split("\n")
    html    = []
    in_list = False

    for line in lines:
        s = line.rstrip()

        # Close list before non-list lines
        if in_list and not (s.startswith("- ") or s.startswith("* ")):
            html.append("</ul>")
            in_list = False

        if s.startswith("## "):
            heading = s[3:].strip()
            colour  = _section_colour(heading)
            emoji   = heading[:2] if heading and ord(heading[0]) > 127 else ""
            label   = heading[2:].strip() if emoji else heading
            html.append(
                f'<table width="100%" cellpadding="0" cellspacing="0" style="margin:24px 0 8px;">'
                f'<tr><td style="border-left:4px solid {colour};padding:4px 0 4px 12px;">'
                f'<h2 style="margin:0;font-size:16px;font-weight:700;color:{colour};">'
                f'{emoji} {label}</h2></td></tr></table>'
            )

        elif s.startswith("- ") or s.startswith("* "):
            if not in_list:
                html.append(
                    '<ul style="margin:0 0 4px 0;padding-left:18px;list-style:disc;">'
                )
                in_list = True
            item = _inline_md(s[2:].strip())
            html.append(
                f'<li style="margin:5px 0;font-size:14px;line-height:1.55;'
                f'color:{COLOUR_TEXT};">{item}</li>'
            )

        elif s.startswith("*") and s.endswith("*") and s.count("*") == 2:
            # *italic* — used for "no items" notes
            html.append(
                f'<p style="margin:4px 0 12px;font-size:13px;'
                f'color:{COLOUR_MUTED};font-style:italic;">{s[1:-1]}</p>'
            )

        elif s == "---":
            html.append(
                f'<hr style="border:none;border-top:1px solid #e2e8f0;margin:20px 0;">'
            )

        elif s == "":
            html.append('<div style="height:4px;"></div>')

        else:
            html.append(
                f'<p style="margin:3px 0;font-size:14px;line-height:1.55;">'
                f'{_inline_md(s)}</p>'
            )

    if in_list:
        html.append("</ul>")

    return "\n".join(html)


def _section_colour(heading: str) -> str:
    for emoji, colour in SECTION_COLOURS.items():
        if emoji in heading:
            return colour
    return COLOUR_PRIMARY


def _inline_md(text: str) -> str:
    """Convert inline markdown (links, bold, italic, code) to HTML."""
    # [text](url) → hyperlink
    text = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        r'<a href="\2" style="color:#0f766e;text-decoration:none;font-weight:600;">\1</a>',
        text,
    )
    # **bold**
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    # *italic*
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    # `code`
    text = re.sub(
        r"`(.+?)`",
        r'<code style="background:#f1f5f9;padding:1px 4px;border-radius:3px;font-size:12px;">\1</code>',
        text,
    )
    return text


# ---------------------------------------------------------------------------
# Attachment helper
# ---------------------------------------------------------------------------

def _build_attachment(file_path: str) -> MIMEBase:
    """Read a file from disk and return a MIME part ready to attach."""
    mime_type, _ = mimetypes.guess_type(file_path)
    if mime_type is None:
        mime_type = "application/octet-stream"
    main_type, sub_type = mime_type.split("/", 1)

    with open(file_path, "rb") as f:
        data = f.read()

    if main_type == "application":
        part = MIMEApplication(data, Name=os.path.basename(file_path))
    else:
        part = MIMEBase(main_type, sub_type)
        part.set_payload(data)

    part.add_header(
        "Content-Disposition",
        "attachment",
        filename=os.path.basename(file_path),
    )
    if main_type != "application":
        import email.encoders
        email.encoders.encode_base64(part)

    return part
