
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Any, Dict, List
import importlib.util
from pathlib import Path
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote, urljoin

app = FastAPI(title="StreamVault Scraper API")
ROOT = Path(__file__).resolve().parent
SCRAPER_FILE = ROOT / "video_scraper_v3.py"

spec = importlib.util.spec_from_file_location("video_scraper_v3", SCRAPER_FILE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
ScraperEngine = module.ScraperEngine

class ExtractRequest(BaseModel):
    url: str
    wait_seconds: int = 5
    timeout: int = 30
    auto_click: bool = True
    drill_iframes: bool = True
    ytdlp_probe: bool = True
    show_browser: bool = False
    cf_timeout: int = 35
    proxy: str | None = None

BASES = {
    "hianime": "https://hianime.to",
    "aniwatch": "https://hianime.to",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}


def log_fn(*args, **kwargs):
    print(*args)


def status_fn(*args, **kwargs):
    print(*args)


def absolute(base: str, href: str | None) -> str:
    return urljoin(base, href or "")


def provider_base(provider: str) -> str:
    return BASES.get((provider or "hianime").lower(), BASES["hianime"])


@app.get('/health')
def health():
    return {"ok": True}


@app.get('/providers/search')
def provider_search(q: str, provider: str = 'hianime'):
    base = provider_base(provider)
    url = f"{base}/search?keyword={quote(q)}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Provider search request failed: {e}")

    soup = BeautifulSoup(r.text, 'html.parser')
    results: List[Dict[str, Any]] = []
    cards = soup.select('.flw-item, .film_list-wrap .flw-item, .film-poster-ahref')
    for card in cards[:20]:
        a = card.select_one('a[href]')
        img = card.select_one('img')
        title_el = card.select_one('.film-name, .dynamic-name, .film-poster-ahref, .film-detail .film-name')
        title = None
        if title_el:
            title = title_el.get_text(' ', strip=True)
        elif a:
            title = a.get('title') or a.get_text(' ', strip=True)
        href = absolute(base, a.get('href') if a else '') if a else ''
        cover = img.get('data-src') or img.get('src') if img else ''
        if title and href:
            results.append({
                'title': title,
                'url': href,
                'cover': cover,
                'provider': provider,
            })
    # fallback: grab any anime-looking links
    if not results:
        for a in soup.select('a[href]'):
            href = absolute(base, a.get('href'))
            text = a.get_text(' ', strip=True)
            if '/watch/' in href and text:
                results.append({'title': text, 'url': href, 'cover': '', 'provider': provider})
            if len(results) >= 20:
                break
    return {'results': results}


@app.get('/providers/episodes')
def provider_episodes(url: str, provider: str = 'hianime'):
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Episode page request failed: {e}")
    soup = BeautifulSoup(r.text, 'html.parser')
    episodes: List[Dict[str, Any]] = []
    seen = set()
    selectors = [
        '#episodes-content a[href]',
        '.ss-list a[href]',
        '.ep-item[href]',
        '.episodes a[href]',
        'a[href*="/watch/"]',
    ]
    for sel in selectors:
        for a in soup.select(sel):
            href = absolute(url, a.get('href'))
            if not href or href in seen:
                continue
            seen.add(href)
            title = a.get('title') or a.get_text(' ', strip=True) or 'Episode'
            num = None
            for attr in ('data-number', 'data-num', 'data-id'):
                if a.get(attr):
                    num = a.get(attr)
                    break
            if num is None:
                import re
                m = re.search(r'(?:ep|episode)\s*(\d+)', title, re.I)
                if m:
                    num = m.group(1)
            episodes.append({'title': title, 'number': num, 'url': href, 'provider': provider})
        if episodes:
            break
    return {'episodes': episodes}


@app.post('/extract')
def extract(body: ExtractRequest):
    engine = ScraperEngine(log_fn, status_fn)
    results = engine.scrape(body.url, body.model_dump())
    if not results:
        return {'best': None, 'results': []}

    def score(item: Dict[str, Any]):
        u = item.get('url', '').lower()
        s = 0
        if '.m3u8' in u: s += 50
        if '.mp4' in u: s += 40
        if 'master' in u or 'playlist' in u: s += 15
        if '1080' in u: s += 10
        if '720' in u: s += 8
        if item.get('method', '').startswith('network'): s += 5
        return s

    ordered = sorted(results, key=score, reverse=True)
    return {'best': ordered[0], 'results': ordered}
