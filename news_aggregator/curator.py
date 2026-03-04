"""
curator.py
Takes raw articles from RSS feeds, NewsAPI, Crunchbase, and Gmail newsletters,
then uses Claude to curate, rank, and summarize the day's most important
healthcare VC / startup news into a structured digest.
"""

from datetime import datetime
import pytz
import anthropic

CLAUDE_MODEL = "claude-haiku-4-5-20251001"

# Hard cap on content sent to Claude
MAX_ARTICLE_CHARS   = 50_000
MAX_NEWSLETTER_CHARS = 20_000

# Maximum raw articles to send Claude (avoids token overruns on busy days)
MAX_ARTICLES_TO_CLAUDE = 60


def build_article_block(
    rss_articles:  list[dict],
    newsapi_items: list[dict],
    crunchbase_rounds: list[dict],
) -> str:
    """
    Combine all article sources into a single text block for the Claude prompt.
    Crunchbase rounds and tier-1 RSS are presented first.
    """
    all_items: list[dict] = []

    # Crunchbase first — highly specific, already filtered to healthcare funding
    all_items.extend(crunchbase_rounds)

    # Tier-1 and relevant RSS articles next
    relevant_rss = [a for a in rss_articles if a.get("is_relevant")]
    other_rss    = [a for a in rss_articles if not a.get("is_relevant")]
    all_items.extend(relevant_rss)
    all_items.extend(newsapi_items)
    all_items.extend(other_rss)

    # Deduplicate by URL
    seen: set[str] = set()
    deduped = []
    for item in all_items:
        url = item.get("url", "")
        if url and url not in seen:
            seen.add(url)
            deduped.append(item)

    # Cap total items
    capped = deduped[:MAX_ARTICLES_TO_CLAUDE]

    lines = [f"=== RAW ARTICLES ({len(capped)} items) ===\n"]
    for i, item in enumerate(capped, 1):
        source  = item.get("source", "Unknown")
        tier    = item.get("tier", 3)
        pub     = item.get("published_str", "")
        title   = item.get("title", "")
        url     = item.get("url", "")
        summary = item.get("summary", "")[:600]
        flags = []
        if item.get("is_relevant"):
            flags.append("FUNDING/M&A")
        if item.get("is_pharma_only"):
            flags.append("PHARMA-ONLY")
        flag_str = f" [{', '.join(flags)}]" if flags else ""

        lines.append(
            f"[{i}] {source} (tier {tier}){flag_str} | {pub}\n"
            f"Title:   {title}\n"
            f"URL:     {url}\n"
            f"Summary: {summary}\n"
        )

    full = "\n".join(lines)
    if len(full) > MAX_ARTICLE_CHARS:
        full = full[:MAX_ARTICLE_CHARS] + "\n\n[... additional articles truncated ...]"
    return full


def build_newsletter_block(newsletter_emails: list[dict]) -> str:
    """Format Gmail newsletter emails for the Claude prompt."""
    if not newsletter_emails:
        return "No newsletter emails received today."

    lines = [f"=== NEWSLETTER EMAILS ({len(newsletter_emails)} emails) ===\n"]
    for i, email in enumerate(newsletter_emails, 1):
        tag = "[NEWSLETTER]" if email["is_newsletter"] else "[FUNDING EMAIL]"
        lines.append(
            f"--- Email {i} {tag} ---\n"
            f"From:    {email['from']}\n"
            f"Subject: {email['subject']}\n"
            f"Body:\n{email['body'][:1500]}\n"
        )

    full = "\n".join(lines)
    if len(full) > MAX_NEWSLETTER_CHARS:
        full = full[:MAX_NEWSLETTER_CHARS] + "\n\n[... newsletter content truncated ...]"
    return full


def curate_with_claude(
    article_block:    str,
    newsletter_block: str,
    api_key:          str,
    timezone_str:     str = "America/New_York",
) -> str:
    """
    Call Claude to curate, rank, and summarize the day's healthcare VC news.
    Returns a structured markdown digest.
    """
    client = anthropic.Anthropic(api_key=api_key)

    tz    = pytz.timezone(timezone_str)
    today = datetime.now(tz).strftime("%A, %B %d, %Y")

    prompt = f"""You are a senior analyst at a top-tier healthcare venture capital firm \
with a primary focus on digital health and healthtech. Today is {today}. \
Your job is to review ALL of the raw articles and newsletter content below and produce \
a crisp, high-signal daily news digest.

FOCUS MANDATE — Digital health and healthtech are the PRIMARY lens:
  → Digital health platforms, health IT, EHR/EMR, telehealth, virtual care, RPM
  → AI in healthcare (clinical AI, ambient documentation, diagnostic AI, etc.)
  → Value-based care enablement, care navigation, population health
  → Behavioral / mental health technology
  → Revenue cycle management, prior auth automation, healthcare payments
  → Consumer health apps, wearables, connected health devices
  → Health data, interoperability, and data infrastructure

SECONDARY (include when investment-relevant, but do NOT crowd out digital health):
  → Medtech / medical devices with a venture / startup angle
  → Biotech / pharma ONLY when there is a clear VC investment event
    (funding round, acquisition, new fund) — pure drug trial updates are low priority

WHAT TO INCLUDE — in strict priority order:
1. 💰 Funding rounds in digital health / healthtech (any size) or medtech/biotech ≥ $30M
2. 🏦 New VC / PE fund launches or closes (LP/GP level) with healthcare or digital health focus
3. 🤝 M&A, acquisitions, or major strategic partnerships with a digital health / healthtech angle
4. 📈 IPO filings, SPAC deals, or secondary offerings by digital health or healthtech companies
5. 🔬 Significant regulatory, clinical, or product milestones with clear commercial / VC implications
6. 🌐 Key market trends, policy changes, or macro signals directly relevant to digital health investing

WHAT TO SKIP:
- Pure pharma drug trial updates with no funding / investment angle (tagged [PHARMA-ONLY])
- General hospital / provider operations with no technology or investment angle
- Incremental product updates from large incumbents (Epic, Cerner, etc.) unless strategic
- Opinion pieces with no hard news
- Duplicate stories — pick the best source, drop the rest

WRITING RULES:
- One sentence max per bullet — pack maximum signal into minimum words
- Funding rounds: company name, amount, stage, lead investor (if known), one-line description
- Fund launches: fund name, GP, size, focus thesis
- M&A: acquirer → target, deal value (or "undisclosed"), one-line strategic rationale
- Hyperlink every item: [Company or Title](URL)
- No filler: never write "In a sign of...", "It's worth noting...", "This comes as..."

---
{article_block}

---
{newsletter_block}

---

Produce the digest using EXACTLY this structure (markdown):

## 💰 Funding Rounds
Digital health and healthtech rounds first, then medtech, then biotech/pharma (only if ≥ $30M). \
Largest rounds first within each category. One bullet per round: \
[Company](URL) — amount, stage, lead investor, one-line description of what they do.
If none: *No funding rounds found today.*

## 🏦 New Funds
New VC, PE, or LP-level fund launches or closes with a healthcare or digital health focus. \
Fund name, GP, size, investment thesis — one line each.
If none: *No new fund announcements today.*

## 🤝 M&A & Partnerships
Acquisitions, mergers, and major strategic partnerships — digital health and healthtech angle first. \
Acquirer → target, deal value (or "undisclosed"), one-line strategic rationale.
If none: *No M&A activity today.*

## 📈 IPOs & Public Markets
IPO filings, SPAC transactions, secondary offerings, or notable public market moves \
by digital health or healthtech companies.
If none: *No IPO or public market news today.*

## 🔬 Notable Clinical & Regulatory
FDA decisions, product clearances, or clinical milestones with clear commercial implications. \
Prioritize digital health / AI tool approvals. Include pharma only if the investment angle is major. \
Skip pure drug trial updates.
If none: *Nothing notable today.*

## 🌐 Ecosystem & Macro
Policy, market research, or big-picture trends that directly affect digital health investing. \
Max 3 bullets. Skip generic hospital IT or EHR-vendor noise.
If none: *Nothing notable today.*

## 📊 Today at a Glance
- Funding rounds covered: X (total disclosed capital: $XM)
- Largest round: [Company] ($XM, Stage)
- New funds: X
- M&A deals: X
- Data sources: RSS feeds, Gmail newsletters, NewsAPI, Crunchbase

Keep the whole digest under 600 words. Every item should pass the test: \
"Would a healthcare VC partner read this and learn something actionable?"\
"""

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}],
    )

    return response.content[0].text
