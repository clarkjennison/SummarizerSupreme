"""
curator.py
Takes raw articles from RSS feeds, NewsAPI, Crunchbase, and Gmail newsletters,
then uses Claude to curate, rank, and summarize the day's most important
healthcare VC / startup news into a structured digest.
"""

from datetime import datetime
import pytz
import anthropic

CLAUDE_MODEL = "claude-3-5-sonnet-20241022"

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
        relevant_flag = " [FUNDING/M&A]" if item.get("is_relevant") else ""

        lines.append(
            f"[{i}] {source} (tier {tier}){relevant_flag} | {pub}\n"
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

    prompt = f"""You are a senior analyst at a top-tier healthcare venture capital firm. \
Today is {today}. Your job is to review ALL of the raw articles and newsletter content below \
and produce a crisp, high-signal daily news digest for a healthcare VC investor.

WHAT TO INCLUDE — in strict priority order:
1. 💰 New funding rounds (Series A/B/C/D, seed, growth equity) in healthcare / digital health / biotech / medtech — especially rounds ≥ $20M
2. 🏦 New VC / PE fund launches or closes (LP/GP level) focused on healthcare
3. 🤝 M&A, acquisitions, or major strategic partnerships in the healthcare ecosystem
4. 📈 IPO filings, SPAC deals, or secondary offerings by healthcare companies
5. 🧠 Significant product launches, clinical trial results, or regulatory approvals with major commercial implications
6. 🌐 Key market trends, policy changes, or macro signals that a healthcare VC investor must know today

WHAT TO SKIP:
- General hospital / provider operations news with no investment angle
- Incremental product updates from large incumbent health systems
- Opinion pieces with no hard news
- Duplicate stories (pick the best source, drop the rest)
- Anything from yesterday that was already widely covered

WRITING RULES:
- One sentence max per item in the lists — pack maximum signal into minimum words
- For funding rounds: always include company name, amount, round stage, lead investor (if known), and what the company does
- For fund launches: always include fund name, GP, size, and focus
- For M&A: always include acquirer, target, deal value (if disclosed), and strategic rationale in one line
- Use hyperlinks (markdown format) for every item: [Title](URL)
- No filler phrases like "In a sign of...", "It's worth noting...", "This comes as..."

---
{article_block}

---
{newsletter_block}

---

Produce the digest using EXACTLY this structure (markdown):

## 💰 Funding Rounds
Bullet list of healthcare startup / biotech / medtech funding rounds announced today. \
Each bullet = one round. Largest rounds first. Include amount, stage, lead investor, and \
one-line description of what the company does. Use [Company Name](URL) format.
If none: *No funding rounds found today.*

## 🏦 New Funds
Bullet list of new VC, PE, or LP-level fund launches or closes focused on healthcare. \
Include fund name, GP, target/final size, and investment thesis in one line.
If none: *No new fund announcements today.*

## 🤝 M&A & Partnerships
Bullet list of acquisitions, mergers, and major strategic partnerships. \
Include acquirer → target, deal value (or "undisclosed"), and one-line strategic rationale.
If none: *No M&A activity today.*

## 📈 IPOs & Public Markets
Filings, SPAC transactions, secondary offerings, or notable public market moves \
by healthcare / digital health companies.
If none: *No IPO or public market news today.*

## 🔬 Notable Clinical & Regulatory
Significant FDA decisions, major clinical trial readouts, or breakthrough designations \
with clear commercial / investment implications. Skip incremental updates.
If none: *Nothing notable today.*

## 🌐 Ecosystem & Macro
Key policy news, market reports, or big-picture trends a healthcare investor must know. \
Max 3 bullets. Skip generic healthcare IT news.
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
