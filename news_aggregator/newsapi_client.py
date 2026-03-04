"""
newsapi_client.py
Pulls healthcare VC / startup news from:
  1. NewsAPI (https://newsapi.org) — free tier: 100 requests/day
  2. Crunchbase Basic API — recent healthcare funding rounds

Both are optional. If the API key is not set, that source is silently skipped.
"""

import json
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone, timedelta


# ---------------------------------------------------------------------------
# NewsAPI
# ---------------------------------------------------------------------------

NEWSAPI_BASE = "https://newsapi.org/v2/everything"

# Search queries run against NewsAPI — each counts as one request
NEWSAPI_QUERIES = [
    "healthcare startup funding",
    "digital health venture capital",
    "health technology acquisition",
    "biotech Series A OR Series B OR Series C",
    "healthcare fund raises OR raised",
]

# Domains to prioritize in NewsAPI results
NEWSAPI_PREFERRED_DOMAINS = (
    "statnews.com,medcitynews.com,endpts.com,rockhealth.com,"
    "fiercehealthcare.com,biopharmadive.com,healthcaredive.com,"
    "modernhealthcare.com,techcrunch.com,axios.com,fortune.com,"
    "wsj.com,ft.com,bloomberg.com,reuters.com,businesswire.com,prnewswire.com"
)


def fetch_newsapi_articles(api_key: str, lookback_hours: int = 24) -> list[dict]:
    """
    Fetch articles from NewsAPI matching healthcare VC search queries.
    Returns deduplicated list of article dicts.
    """
    if not api_key:
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    from_date = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")

    seen_urls: set[str] = set()
    articles = []

    for query in NEWSAPI_QUERIES:
        params = {
            "q":          query,
            "from":       from_date,
            "language":   "en",
            "sortBy":     "publishedAt",
            "pageSize":   20,
            "domains":    NEWSAPI_PREFERRED_DOMAINS,
            "apiKey":     api_key,
        }
        url = f"{NEWSAPI_BASE}?{urllib.parse.urlencode(params)}"

        try:
            with urllib.request.urlopen(url, timeout=15) as resp:
                data = json.loads(resp.read())
        except Exception as e:
            print(f"  NewsAPI warning ({query!r}): {e}")
            continue

        for art in data.get("articles", []):
            article_url = art.get("url", "")
            if not article_url or article_url in seen_urls:
                continue
            seen_urls.add(article_url)

            pub_str = art.get("publishedAt", "")
            try:
                pub_dt = datetime.strptime(pub_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            except Exception:
                pub_dt = datetime.now(timezone.utc)

            articles.append({
                "title":        art.get("title") or "",
                "url":          article_url,
                "source":       art.get("source", {}).get("name") or "NewsAPI",
                "tier":         2,
                "summary":      (art.get("description") or art.get("content") or "")[:800],
                "published_dt": pub_dt,
                "published_ts": pub_dt.timestamp(),
                "published_str": pub_dt.strftime("%b %d, %I:%M %p UTC"),
                "categories":   [],
                "is_relevant":  True,   # Already filtered by query
            })

    return articles


# ---------------------------------------------------------------------------
# Crunchbase Basic API
# ---------------------------------------------------------------------------

CRUNCHBASE_BASE = "https://api.crunchbase.com/api/v4"

# Healthcare-related Crunchbase category groups
HEALTHCARE_CATEGORIES = [
    "health_care", "biotechnology", "life_sciences", "medical_device",
    "digital_health", "health_diagnostics", "pharmaceutical", "hospital",
    "health_insurance", "mental_health", "telehealth",
]


def fetch_crunchbase_rounds(api_key: str, lookback_hours: int = 24) -> list[dict]:
    """
    Fetch recent healthcare funding rounds from Crunchbase.
    Requires a Crunchbase Basic or Pro API key.
    Returns a list of funding event dicts.
    """
    if not api_key:
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    after_date = cutoff.strftime("%Y-%m-%d")

    # Crunchbase v4 search endpoint for funding rounds
    url = f"{CRUNCHBASE_BASE}/searches/funding_rounds?user_key={api_key}"
    payload = {
        "field_ids": [
            "identifier",
            "announced_on",
            "raised_amount_usd",
            "investment_type",
            "investor_identifiers",
            "organization_identifier",
            "short_description",
            "lead_investor_identifiers",
        ],
        "query": [
            {
                "type": "predicate",
                "field_id": "announced_on",
                "operator_id": "gte",
                "values": [after_date],
            },
            {
                "type": "predicate",
                "field_id": "organization_categories",
                "operator_id": "includes",
                "values": HEALTHCARE_CATEGORIES,
            },
        ],
        "order": [{"field_id": "announced_on", "sort": "desc"}],
        "limit": 25,
    }

    try:
        req_data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=req_data,
            headers={
                "Content-Type": "application/json",
                "User-Agent":   "HealthcareVCBot/1.0",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"  Crunchbase API error {e.code}: {body[:200]}")
        return []
    except Exception as e:
        print(f"  Crunchbase warning: {e}")
        return []

    rounds = []
    for entity in data.get("entities", []):
        props = entity.get("properties", {})

        org_name   = _cb_name(props.get("organization_identifier"))
        round_type = props.get("investment_type", "Funding Round").replace("_", " ").title()
        amount_usd = props.get("raised_amount_usd")
        amount_str = _format_amount(amount_usd)
        announced  = props.get("announced_on", "")
        description = props.get("short_description", "")

        investors = [_cb_name(i) for i in props.get("lead_investor_identifiers", [])]
        investor_str = ", ".join(filter(None, investors)) or "Undisclosed"

        cb_id    = props.get("identifier", {}).get("permalink", "")
        cb_url   = f"https://www.crunchbase.com/funding_round/{cb_id}" if cb_id else "https://www.crunchbase.com"

        try:
            pub_dt = datetime.strptime(announced, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except Exception:
            pub_dt = datetime.now(timezone.utc)

        title = f"{org_name} Raises {amount_str} {round_type}"
        summary = (
            f"{org_name} announced a {amount_str} {round_type}. "
            f"Lead investor(s): {investor_str}. "
            f"{description}"
        ).strip()

        rounds.append({
            "title":        title,
            "url":          cb_url,
            "source":       "Crunchbase",
            "tier":         1,
            "summary":      summary[:800],
            "published_dt": pub_dt,
            "published_ts": pub_dt.timestamp(),
            "published_str": pub_dt.strftime("%b %d"),
            "categories":   ["funding"],
            "is_relevant":  True,
            "amount_usd":   amount_usd or 0,
        })

    return rounds


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cb_name(identifier) -> str:
    """Safely extract entity name from a Crunchbase identifier dict."""
    if not identifier:
        return ""
    if isinstance(identifier, dict):
        return identifier.get("value") or identifier.get("name") or ""
    return str(identifier)


def _format_amount(amount_usd) -> str:
    """Format a dollar amount as $XM or $XB."""
    if not amount_usd:
        return "Undisclosed"
    try:
        amount = float(amount_usd)
    except (TypeError, ValueError):
        return "Undisclosed"

    if amount >= 1_000_000_000:
        return f"${amount / 1_000_000_000:.1f}B"
    if amount >= 1_000_000:
        return f"${amount / 1_000_000:.0f}M"
    if amount >= 1_000:
        return f"${amount / 1_000:.0f}K"
    return f"${amount:,.0f}"
