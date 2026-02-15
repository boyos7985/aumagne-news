import os
import sys
import json
import datetime
import time
import email.utils
import requests
import feedparser
from bs4 import BeautifulSoup

# --- Configuration ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(SCRIPT_DIR, "last_digest.json")
MAX_SEEN_URLS = 500
REQUEST_TIMEOUT = 10

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; AumagneNewsBot/1.0)"
}

# --- Communes dans le perimetre ---
COMMUNE_AUMAGNE = "aumagne"
COMMUNES = [
    "aumagne", "aujac", "la brousse", "blanzac-les-matha", "blanzac",
    "authon-ebeon", "authon", "sainte-meme", "bercloux", "courcerac",
    "fontenet", "mons", "nantille", "prignac", "varaize",
    "matha", "saint-jean-d'angely", "saint jean d'angely",
    "saint-jean-d-angely", "vals de saintonge",
]

# --- Villes hors perimetre (a exclure) ---
EXCLUDED_CITIES = [
    "poitiers", "la rochelle", "bordeaux", "niort", "angouleme",
    "royan", "rochefort", "limoges", "pau", "biarritz", "bayonne",
    "agen", "perigueux", "mont-de-marsan", "dax", "bergerac",
    "chatellerault", "bressuire", "parthenay", "thouars",
]

# --- Mots-cles d'interet ---
KEYWORDS = [
    # Enfants / loisirs
    "enfant", "famille", "stage", "atelier", "animation", "ludique",
    "peche", "sport", "piscine", "jeux", "camp", "centre de loisirs",
    # Activites permanentes
    "cinema", "marche", "artisan", "maraicher", "boulanger", "patissier",
    "ouverture", "inauguration", "nouveau",
    # Nature / rando
    "randonnee", "pedestre", "circuit", "sentier", "bateau", "kayak",
    "canoe", "balade", "velo",
    # Culture / patrimoine
    "histoire", "patrimoine", "visite", "chateau", "eglise", "musee",
    "terra aventura",
    # Evenements
    "brocante", "vide-grenier", "vide grenier", "foire", "fete",
    "concert", "spectacle", "exposition", "festival",
]


def safe_fetch(url, timeout=REQUEST_TIMEOUT):
    """Fetch URL with error handling, returns None on failure."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        return resp
    except Exception as e:
        print(f"  [WARN] Failed to fetch {url}: {e}")
        return None


# --- Source fetchers ---

def fetch_google_news():
    """Fetch articles from Google News RSS for local queries."""
    articles = []
    queries = [
        "Aumagne 17770",
        "Aumagne Charente-Maritime",
        "Saint-Jean-d'Angely activites",
        "Matha 17160",
        "Vals de Saintonge",
    ]
    for query in queries:
        url = (
            f"https://news.google.com/rss/search?"
            f"q={requests.utils.quote(query)}&hl=fr&gl=FR&ceid=FR:fr"
        )
        resp = safe_fetch(url)
        if resp is None:
            continue
        feed = feedparser.parse(resp.text)
        for entry in feed.entries[:10]:
            articles.append({
                "title": entry.get("title", ""),
                "url": entry.get("link", ""),
                "source": "Google News",
                "published": entry.get("published", ""),
            })
    return articles


def fetch_sudouest_rss():
    """Fetch articles from SudOuest Charente-Maritime RSS."""
    articles = []
    urls = [
        "https://www.sudouest.fr/charente-maritime/rss.xml",
        "https://www.sudouest.fr/essentiel/rss.xml",
    ]
    for url in urls:
        resp = safe_fetch(url)
        if resp is None:
            continue
        feed = feedparser.parse(resp.text)
        for entry in feed.entries[:20]:
            articles.append({
                "title": entry.get("title", ""),
                "url": entry.get("link", ""),
                "source": "SudOuest",
                "published": entry.get("published", ""),
            })
    return articles


def fetch_francebleu():
    """Scrape headlines from France Bleu Charente-Maritime."""
    articles = []
    url = "https://www.francebleu.fr/nouvelle-aquitaine/charente-maritime-17"
    resp = safe_fetch(url)
    if resp is None:
        return articles
    soup = BeautifulSoup(resp.text, "html.parser")
    for link in soup.select("a[href]"):
        title = link.get_text(strip=True)
        href = link.get("href", "")
        if title and len(title) > 20 and "/infos/" in href:
            full_url = href if href.startswith("http") else f"https://www.francebleu.fr{href}"
            articles.append({
                "title": title,
                "url": full_url,
                "source": "France Bleu",
                "published": "",
            })
    return articles[:15]


def fetch_mairie():
    """Scrape news from Aumagne mairie website."""
    articles = []
    url = "https://www.aumagne.fr/"
    resp = safe_fetch(url)
    if resp is None:
        return articles
    soup = BeautifulSoup(resp.text, "html.parser")
    for link in soup.select("a[href]"):
        title = link.get_text(strip=True)
        href = link.get("href", "")
        if title and len(title) > 15 and href and href != "/":
            full_url = href if href.startswith("http") else f"https://www.aumagne.fr{href}"
            articles.append({
                "title": title,
                "url": full_url,
                "source": "Mairie Aumagne",
                "published": "",
            })
    return articles[:10]


def fetch_vals_de_saintonge():
    """Scrape events/news from Vals de Saintonge website."""
    articles = []
    urls = [
        "https://www.valsdesaintonge.fr/actualites/",
        "https://www.valsdesaintonge.fr/agenda/",
    ]
    for url in urls:
        resp = safe_fetch(url)
        if resp is None:
            continue
        soup = BeautifulSoup(resp.text, "html.parser")
        for link in soup.select("a[href]"):
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if title and len(title) > 15 and href and href != "/":
                full_url = href if href.startswith("http") else f"https://www.valsdesaintonge.fr{href}"
                articles.append({
                    "title": title,
                    "url": full_url,
                    "source": "Vals de Saintonge",
                    "published": "",
                })
    return articles[:15]


# --- Filtering & deduplication ---

def parse_pub_date(published_str):
    """Parse RSS published date string, return datetime or None."""
    if not published_str:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(published_str)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=datetime.timezone.utc)
        return parsed
    except Exception:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
        try:
            parsed = datetime.datetime.strptime(published_str, fmt)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=datetime.timezone.utc)
            return parsed
        except ValueError:
            continue
    return None


def is_recent(article, max_age_hours=48):
    """Check if article was published within the last max_age_hours.
    Articles without a date are kept (benefit of the doubt for scraped sources)."""
    pub = parse_pub_date(article.get("published", ""))
    if pub is None:
        return True
    now = datetime.datetime.now(datetime.timezone.utc)
    return (now - pub).total_seconds() < max_age_hours * 3600


def is_relevant(article):
    """Article must mention a commune in the perimeter AND not mention excluded cities."""
    text = (article["title"] + " " + article.get("url", "")).lower()
    # Exclude articles about far-away cities
    if any(city in text for city in EXCLUDED_CITIES):
        return False
    # Must mention a commune in the perimeter
    mentions_commune = any(c in text for c in COMMUNES)
    return mentions_commune


def classify_article(article):
    """Classify article: 'aumagne', 'alentours', or 'activites'."""
    text = (article["title"] + " " + article.get("url", "")).lower()
    if COMMUNE_AUMAGNE in text:
        return "aumagne"
    if any(k in text for k in KEYWORDS):
        return "activites"
    return "alentours"


def deduplicate(articles, seen_urls):
    """Remove already-seen articles and duplicates by URL."""
    unique = []
    seen = set(seen_urls)
    for a in articles:
        url = a["url"]
        if url and url not in seen:
            seen.add(url)
            unique.append(a)
    return unique


# --- State management ---

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {"last_date": "", "seen_urls": []}


def save_state(state):
    # Keep only the last MAX_SEEN_URLS
    state["seen_urls"] = state["seen_urls"][-MAX_SEEN_URLS:]
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


# --- Telegram ---

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    resp = requests.post(url, json=payload, timeout=10)
    resp.raise_for_status()
    print(f"Telegram sent: {resp.status_code}")


def format_digest(classified):
    """Format the digest message for Telegram."""
    now = datetime.datetime.now(datetime.UTC).strftime("%d %b %Y")
    lines = [f"\U0001F4F0 *News Aumagne & alentours* \u2014 {now}\n"]

    if classified["aumagne"]:
        lines.append("\U0001F3D8\uFE0F *AUMAGNE*")
        for a in classified["aumagne"][:5]:
            lines.append(f"\u2022 [{a['title']}]({a['url']}) _({a['source']})_")
        lines.append("")

    if classified["alentours"]:
        lines.append("\U0001F4CD *ALENTOURS*")
        for a in classified["alentours"][:8]:
            lines.append(f"\u2022 [{a['title']}]({a['url']}) _({a['source']})_")
        lines.append("")

    if classified["activites"]:
        lines.append("\U0001F3AF *ACTIVITES & LOISIRS*")
        for a in classified["activites"][:8]:
            lines.append(f"\u2022 [{a['title']}]({a['url']}) _({a['source']})_")
        lines.append("")

    return "\n".join(lines)


# --- Main ---

def main():
    test_mode = "--test" in sys.argv

    # 1. Fetch from all sources
    print("Fetching from all sources...")
    all_articles = []

    sources = [
        ("Google News", fetch_google_news),
        ("SudOuest", fetch_sudouest_rss),
        ("France Bleu", fetch_francebleu),
        ("Mairie Aumagne", fetch_mairie),
        ("Vals de Saintonge", fetch_vals_de_saintonge),
    ]

    for name, fetcher in sources:
        print(f"  Fetching {name}...")
        try:
            articles = fetcher()
            print(f"    -> {len(articles)} articles")
            all_articles.extend(articles)
        except Exception as e:
            print(f"    -> ERROR: {e}")

    print(f"Total raw articles: {len(all_articles)}")

    # 2. Filter recent (last 48h) and relevant (commune in perimeter)
    recent = [a for a in all_articles if is_recent(a)]
    print(f"Recent articles (last 48h): {len(recent)}")
    relevant = [a for a in recent if is_relevant(a)]
    print(f"Relevant articles: {len(relevant)}")

    # 3. Deduplicate
    state = load_state()
    new_articles = deduplicate(relevant, state["seen_urls"])
    print(f"New articles (after dedup): {len(new_articles)}")

    # 4. Classify
    classified = {"aumagne": [], "alentours": [], "activites": []}
    for a in new_articles:
        cat = classify_article(a)
        classified[cat].append(a)

    total = sum(len(v) for v in classified.values())
    print(f"Classified: Aumagne={len(classified['aumagne'])}, "
          f"Alentours={len(classified['alentours'])}, "
          f"Activites={len(classified['activites'])}")

    # 5. Send or skip
    if test_mode:
        if total == 0:
            now = datetime.datetime.now(datetime.UTC).strftime("%d %b %Y %H:%M UTC")
            message = (
                "\u26A0\uFE0F *Test fausse alerte \u2014 Aumagne News*\n\n"
                f"Aucune nouvelle aujourd'hui, mais le systeme fonctionne.\n"
                f"\u2705 Pipeline OK\n"
                f"\U0001F4C5 {now}"
            )
        else:
            message = "\u26A0\uFE0F *TEST* \u2014 " + format_digest(classified)
        print("Sending test digest...")
        send_telegram(message)
        print("Test digest sent.")
        return

    if total == 0:
        print("No new relevant articles. Skipping.")
        return

    message = format_digest(classified)
    print("Sending digest...")
    send_telegram(message)

    # 6. Update state
    state["last_date"] = datetime.date.today().isoformat()
    state["seen_urls"].extend(a["url"] for a in new_articles)
    save_state(state)
    print("Done.")


if __name__ == "__main__":
    main()
