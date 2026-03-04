"""
rss_fetcher.py
Fetches articles from curated healthcare / VC RSS feeds published in the last 24 hours.
No API key required — all sources are publicly available.
"""

import time
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from typing import Optional
import xml.etree.ElementTree as ET
import urllib.request
import urllib.error

# ---------------------------------------------------------------------------
# Feed registry — add / remove feeds here as needed
# Each entry: (feed_url, source_label, tier)
#   tier 1 = must-read  |  tier 2 = good signal  |  tier 3 = supplemental
# ---------------------------------------------------------------------------
FEEDS = [
    # Tier 1 — Digital health & healthtech VC (primary focus)
    ("https://rockhealth.com/feed/",                                   "Rock Health",            1),
    ("https://medcitynews.com/feed/",                                  "MedCity News",           1),
    ("https://hitconsultant.net/feed/",                                "HIT Consultant",         1),
    ("https://www.healthcaredive.com/feeds/news/",                     "Healthcare Dive",        1),
    ("https://techcrunch.com/tag/health/feed/",                        "TechCrunch Health",      1),
    ("https://mhealthintelligence.com/feed",                           "mHealth Intelligence",   1),
    ("https://www.healthcareitnews.com/rss.xml",                       "Healthcare IT News",     1),

    # Tier 2 — Broad healthcare news with significant digital health coverage
    ("https://www.statnews.com/feed/",                                 "STAT News",              2),
    ("https://www.fiercehealthcare.com/rss/xml",                       "Fierce Healthcare",      2),
    ("https://www.modernhealthcare.com/section/hospitals/rss",         "Modern Healthcare",      2),
    ("https://www.beckershospitalreview.com/rss/all-topics",           "Becker's Hospital Review", 2),

    # Tier 3 — Pharma / biotech / broader VC (supplemental; still included, lower priority)
    ("https://endpts.com/feed/",                                       "Endpoints News",         3),
    ("https://www.biopharmadive.com/feeds/news/",                      "BioPharma Dive",         3),
    ("https://www.fiercebiotech.com/rss/xml",                          "Fierce Biotech",         3),
    ("https://news.crunchbase.com/feed/",                              "Crunchbase News",        3),
    ("https://techcrunch.com/category/venture/feed/",                  "TechCrunch Venture",     3),
    ("https://www.axios.com/feeds/feed.rss",                           "Axios",                  3),
]

# Keywords that flag an article as directly relevant to healthtech / healthcare VC
RELEVANCE_KEYWORDS = [
    # Funding events
    "raises", "raised", "funding", "fundraise", "series a", "series b", "series c",
    "seed round", "venture", "investment", "investors", "backed", "capital",
    "valuation", "unicorn", "pre-ipo", "ipo",
    # M&A
    "acquires", "acquired", "acquisition", "merger", "deal", "partnership",
    "strategic investment", "buys", "sold to",
    # Fund-level
    "new fund", "fund launch", "lp", "gp", "limited partner", "general partner",
    "closes fund", "fund close", "fund raise",
    # Digital health / healthtech (primary focus)
    "digital health", "health tech", "healthtech", "health it", "health information",
    "healthcare startup", "health startup", "telehealth", "telemedicine",
    "remote patient monitoring", "rpm", "virtual care", "care navigation",
    "ai health", "health ai", "clinical ai", "ambient ai", "ambient documentation",
    "ehr", "emr", "electronic health", "interoperability", "health data",
    "value-based care", "vbc", "population health", "care management",
    "mental health app", "behavioral health tech", "digital therapeutics", "dtx",
    "wearable", "connected health", "patient engagement", "care coordination",
    "revenue cycle", "rcm", "prior authorization", "claims automation",
    # Medtech / devices (included)
    "medtech", "medical device", "diagnostics", "point-of-care",
    # Biotech / pharma (included at lower weight — Claude handles de-prioritization)
    "biotech", "therapeutics", "clinical trial", "fda approval",
]

# Keywords that signal a story is primarily pharma/drug-focused.
# Articles matching these (but not RELEVANCE_KEYWORDS) are tagged for Claude
# to rank lower unless there is a clear VC / investment angle.
PHARMA_SIGNALS = [
    "phase 1", "phase 2", "phase 3", "nda filing", "bla filing", "pdufa",
    "investigational new drug", "ind ", "clinical trial data", "trial results",
    "drug approval", "drug candidate", "molecule", "compound", "antibody",
    "biologics", "gene therapy", "cell therapy", "biosimilar", "oncology drug",
]


def fetch_articles(lookback_hours: int = 24) -> list[dict]:
    """
    Pull articles published within the last `lookback_hours` from all registered feeds.
    Returns a list of article dicts, sorted newest first.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    articles = []

    for feed_url, source, tier in FEEDS:
        try:
            fetched = _fetch_feed(feed_url, source, tier, cutoff)
            articles.extend(fetched)
        except Exception as e:
            print(f"  Warning: could not fetch {source} ({feed_url}): {e}")

    # Deduplicate by URL
    seen_urls: set[str] = set()
    unique = []
    for a in articles:
        if a["url"] not in seen_urls:
            seen_urls.add(a["url"])
            unique.append(a)

    # Sort: tier 1 first, then newest
    unique.sort(key=lambda a: (a["tier"], -a["published_ts"]))
    return unique


def _fetch_feed(url: str, source: str, tier: int, cutoff: datetime) -> list[dict]:
    """Fetch and parse a single RSS/Atom feed, returning articles newer than cutoff."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (compatible; HealthcareVCBot/1.0; "
                "+https://github.com/clarkjennison/SummarizerSupreme)"
            )
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw_xml = resp.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}")

    try:
        root = ET.fromstring(raw_xml)
    except ET.ParseError as e:
        raise RuntimeError(f"XML parse error: {e}")

    # Detect RSS vs Atom
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    is_atom = root.tag == "{http://www.w3.org/2005/Atom}feed" or "Atom" in root.tag

    articles = []

    if is_atom:
        items = root.findall("atom:entry", ns) or root.findall("{http://www.w3.org/2005/Atom}entry")
    else:
        channel = root.find("channel")
        items = channel.findall("item") if channel is not None else root.findall("item")

    for item in items:
        try:
            art = _parse_item(item, source, tier, is_atom, ns)
            if art and art["published_dt"] >= cutoff:
                articles.append(art)
        except Exception:
            continue

    return articles


def _parse_item(item, source: str, tier: int, is_atom: bool, ns: dict) -> Optional[dict]:
    """Extract fields from a single RSS item or Atom entry."""
    def get(tag, attr=None):
        # Try with and without Atom namespace
        el = item.find(tag)
        if el is None and is_atom:
            el = item.find(f"atom:{tag}", ns)
        if el is None:
            el = item.find(f"{{http://www.w3.org/2005/Atom}}{tag}")
        if el is None:
            return ""
        if attr:
            return el.get(attr, "")
        return (el.text or "").strip()

    title   = get("title")
    if not title:
        return None

    url = get("link")
    if not url and is_atom:
        # Atom link is usually an attribute
        link_el = item.find("{http://www.w3.org/2005/Atom}link")
        if link_el is not None:
            url = link_el.get("href", "")

    # Published date
    pub_str = get("pubDate") or get("published") or get("updated") or get("dc:date")
    pub_dt  = _parse_date(pub_str)
    if pub_dt is None:
        pub_dt = datetime.now(timezone.utc)

    # Summary / description
    summary = get("description") or get("summary") or get("content") or ""
    # Strip HTML tags (basic)
    summary = _strip_html(summary)[:800]

    # Category tags
    cats = [c.text or "" for c in item.findall("category")] if not is_atom else []

    return {
        "title":        title,
        "url":          url,
        "source":       source,
        "tier":         tier,
        "summary":      summary,
        "published_dt": pub_dt,
        "published_ts": pub_dt.timestamp(),
        "published_str": pub_dt.strftime("%b %d, %I:%M %p UTC"),
        "categories":    cats,
        "is_relevant":   _is_relevant(title, summary),
        "is_pharma_only": _is_pharma_only(title, summary),
    }


def _is_relevant(title: str, summary: str) -> bool:
    """Quick keyword check to flag articles directly about healthcare VC."""
    text = (title + " " + summary).lower()
    return any(kw in text for kw in RELEVANCE_KEYWORDS)


def _is_pharma_only(title: str, summary: str) -> bool:
    """True if the article reads as primarily pharma/drug news with no clear investment angle."""
    text = (title + " " + summary).lower()
    has_pharma  = any(kw in text for kw in PHARMA_SIGNALS)
    has_vc_hook = any(kw in text for kw in [
        "raises", "raised", "funding", "acquires", "acquisition",
        "venture", "investment", "ipo", "new fund", "startup",
    ])
    return has_pharma and not has_vc_hook


def _parse_date(date_str: str) -> Optional[datetime]:
    """Parse RFC 2822 (RSS) or ISO 8601 (Atom) dates."""
    if not date_str:
        return None
    try:
        dt = parsedate_to_datetime(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        pass
    # Try ISO 8601
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(date_str[:25], fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


def _strip_html(html: str) -> str:
    """Remove HTML tags from a string."""
    import re
    clean = re.sub(r"<[^>]+>", " ", html)
    clean = re.sub(r"&nbsp;", " ", clean)
    clean = re.sub(r"&amp;",  "&", clean)
    clean = re.sub(r"&lt;",   "<", clean)
    clean = re.sub(r"&gt;",   ">", clean)
    clean = re.sub(r"&quot;", '"', clean)
    clean = re.sub(r"\s+",    " ", clean)
    return clean.strip()
