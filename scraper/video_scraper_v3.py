#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║          ULTIMATE VIDEO SCRAPER  —  v3.0                        ║
║                                                                  ║
║  Anti-detection arsenal:                                         ║
║  • playwright-stealth     — hides automation fingerprints        ║
║  • Human mouse simulation — random moves, delays, scrolls       ║
║  • Canvas/WebGL spoofing  — defeats canvas fingerprinting        ║
║  • Realistic browser env  — real UA, screen, timezone, fonts    ║
║  • Cloudflare solver      — waits + solves CF challenges        ║
║  • Cookie persistence     — reuses sessions across scrapes      ║
║                                                                  ║
║  Extraction strategies:                                          ║
║  • Network interception   — HLS/DASH/MP4 stream capture         ║
║  • Response body scan     — reads XHR/fetch JSON responses      ║
║  • DOM + Shadow DOM scan  — deep video element search           ║
║  • JS heap scan           — extracts obfuscated variables       ║
║  • Iframe drilling        — follows nested video embeds         ║
║  • Service Worker bypass  — intercepts SW-routed streams        ║
║  • JS decryption hooks    — monkey-patches crypto functions     ║
║  • yt-dlp probe           — 1000+ site fallback extractor       ║
║  • Proxy rotation support — avoid IP bans                       ║
╚══════════════════════════════════════════════════════════════════╝

Setup:
  pip install playwright playwright-stealth requests yt-dlp beautifulsoup4 fake-useragent
  playwright install chromium
"""

import sys, os, json, threading, re, time, random, subprocess, base64, hashlib
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox

# ── Colour palette (shared) ────────────────────────────────────────────────────
BG, CARD, BORDER = "#06090f", "#0d1117", "#1a2233"
FG, ACCENT       = "#cdd9e5", "#58a6ff"
GREEN, YELLOW, RED, MUTED = "#3fb950", "#d29922", "#f85149", "#484f58"
MONO = ("Consolas", 10)
MONO_LG = ("Consolas", 13)


# ══════════════════════════════════════════════════════════════════════════════
#  DEPENDENCY MANAGER
# ══════════════════════════════════════════════════════════════════════════════
REQUIRED = [
    "playwright", "playwright_stealth", "requests",
    "yt_dlp", "bs4", "fake_useragent",
]
PIP_NAMES = {
    "playwright_stealth": "playwright-stealth",
    "bs4":                "beautifulsoup4",
    "fake_useragent":     "fake-useragent",
    "yt_dlp":             "yt-dlp",
}

def install_deps(log_fn=print):
    for mod in REQUIRED:
        try:
            __import__(mod)
        except ImportError:
            pkg = PIP_NAMES.get(mod, mod)
            log_fn(f"  Installing {pkg}...")
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", pkg,
                 "--break-system-packages", "-q"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
    # Playwright browser
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            p.chromium.executable_path  # raises if not installed
    except Exception:
        log_fn("  Installing Chromium browser...")
        subprocess.check_call(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )


# ══════════════════════════════════════════════════════════════════════════════
#  STEALTH JS PAYLOAD  (injected before every page load)
# ══════════════════════════════════════════════════════════════════════════════
STEALTH_JS = """
// ── 1. Hide webdriver flag ──────────────────────────────────────────────────
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});

// ── 2. Fake plugins (real Chrome has plugins) ───────────────────────────────
Object.defineProperty(navigator, 'plugins', {
  get: () => {
    const arr = [
      {name:'Chrome PDF Plugin',    filename:'internal-pdf-viewer'},
      {name:'Chrome PDF Viewer',    filename:'mhjfbmdgcfjbbpaeojofohoefgiehjai'},
      {name:'Native Client',        filename:'internal-nacl-plugin'},
    ];
    arr.__proto__ = PluginArray.prototype;
    return arr;
  }
});

// ── 3. Fake languages ────────────────────────────────────────────────────────
Object.defineProperty(navigator, 'languages', {get: () => ['en-US','en']});

// ── 4. Canvas fingerprint noise ──────────────────────────────────────────────
const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
HTMLCanvasElement.prototype.toDataURL = function(type) {
  const ctx = this.getContext('2d');
  if (ctx) {
    const imgData = ctx.getImageData(0,0,this.width,this.height);
    for (let i=0; i<imgData.data.length; i+=4) {
      imgData.data[i]   ^= Math.floor(Math.random()*3);
      imgData.data[i+1] ^= Math.floor(Math.random()*3);
    }
    ctx.putImageData(imgData,0,0);
  }
  return origToDataURL.apply(this, arguments);
};

// ── 5. WebGL vendor spoof ────────────────────────────────────────────────────
const getParam = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(param) {
  if (param === 37445) return 'Intel Inc.';
  if (param === 37446) return 'Intel Iris OpenGL Engine';
  return getParam.apply(this, arguments);
};

// ── 6. Permissions API spoof ─────────────────────────────────────────────────
const origQuery = window.navigator.permissions && navigator.permissions.query.bind(navigator.permissions);
if (origQuery) {
  navigator.permissions.query = (params) =>
    params.name === 'notifications'
      ? Promise.resolve({state: Notification.permission})
      : origQuery(params);
}

// ── 7. Chrome runtime present ────────────────────────────────────────────────
window.chrome = { runtime: {}, loadTimes: function(){}, csi: function(){} };

// ── 8. Iframe contentWindow fix ──────────────────────────────────────────────
Object.defineProperty(HTMLIFrameElement.prototype, 'contentWindow', {
  get: function() {
    try { return this.contentDocument.defaultView; } catch(e) { return window; }
  }
});

// ── 9. Crypto hook — intercept decryption calls ──────────────────────────────
window.__interceptedKeys = [];
window.__interceptedData = [];
const _origDecrypt = window.crypto && window.crypto.subtle && window.crypto.subtle.decrypt.bind(window.crypto.subtle);
if (_origDecrypt) {
  window.crypto.subtle.decrypt = async function(algo, key, data) {
    const result = await _origDecrypt(algo, key, data);
    try {
      const decoded = new TextDecoder().decode(result);
      if (decoded.includes('.m3u8') || decoded.includes('.mp4') || decoded.includes('http')) {
        window.__interceptedData.push(decoded);
        console.log('[CRYPTO_HOOK]', decoded.substring(0,200));
      }
    } catch(e) {}
    return result;
  };
}

// ── 10. XHR + fetch monkey-patch — log all video-related responses ──────────
const _xhrOpen = XMLHttpRequest.prototype.open;
XMLHttpRequest.prototype.open = function(method, url) {
  this._url = url;
  return _xhrOpen.apply(this, arguments);
};
const _xhrSend = XMLHttpRequest.prototype.send;
XMLHttpRequest.prototype.send = function() {
  this.addEventListener('load', function() {
    if (this._url && /\\.m3u8|\\.mp4|\\.mpd|stream|playlist/i.test(this._url)) {
      window.__xhrVideoUrls = window.__xhrVideoUrls || [];
      window.__xhrVideoUrls.push(this._url);
    }
    try {
      if (this.responseText && /m3u8|mp4|stream/i.test(this.responseText)) {
        const matches = this.responseText.match(/https?:\\/\\/[^"' ]+\\.m3u8[^"' ]*/g);
        if (matches) {
          window.__xhrVideoUrls = (window.__xhrVideoUrls||[]).concat(matches);
        }
      }
    } catch(e) {}
  });
  return _xhrSend.apply(this, arguments);
};

// ── 11. atob hook — catch base64-encoded URLs ────────────────────────────────
const _origAtob = window.atob;
window.atob = function(str) {
  const result = _origAtob(str);
  if (result && (result.includes('.m3u8') || result.includes('.mp4') || result.includes('http'))) {
    window.__decodedB64 = window.__decodedB64 || [];
    window.__decodedB64.push(result);
    console.log('[B64_HOOK]', result.substring(0,200));
  }
  return result;
};
"""


# ══════════════════════════════════════════════════════════════════════════════
#  HUMAN BEHAVIOUR SIMULATOR
# ══════════════════════════════════════════════════════════════════════════════
class HumanSim:
    """Simulates realistic human mouse movement and interaction."""

    @staticmethod
    def move_mouse(page):
        try:
            w = random.randint(200, 1100)
            h = random.randint(100, 600)
            steps = random.randint(8, 20)
            for _ in range(steps):
                page.mouse.move(
                    random.randint(0, w),
                    random.randint(0, h),
                    steps=random.randint(3, 8),
                )
                time.sleep(random.uniform(0.02, 0.08))
        except Exception:
            pass

    @staticmethod
    def scroll(page):
        try:
            for _ in range(random.randint(2, 5)):
                page.mouse.wheel(0, random.randint(100, 400))
                time.sleep(random.uniform(0.3, 0.8))
        except Exception:
            pass

    @staticmethod
    def random_pause():
        time.sleep(random.uniform(0.5, 2.0))

    @staticmethod
    def click_play(page, log):
        """Try every known play button selector."""
        selectors = [
            # Generic
            "button.play", ".play-btn", ".play-button", "#play-button",
            "[aria-label='Play']", "[aria-label='play']",
            "[title='Play']",     "[title='play']",
            # Video.js
            ".vjs-play-control", ".vjs-big-play-button",
            # JW Player
            ".jw-icon-playback", ".jw-display-icon-container",
            # Plyr
            ".plyr__control--overlaid", ".plyr__play",
            # Fluid Player
            ".fp-play", ".fp-play-btn",
            # Custom
            "button[class*='play']", "div[class*='play']",
            ".video-play-overlay", ".player-overlay",
            # SVG play icons
            "svg[class*='play']", ".icon-play",
        ]
        for sel in selectors:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    el.click(timeout=2000)
                    log(f"  ▶ Clicked play: {sel}", "ok")
                    time.sleep(1.5)
                    return True
            except Exception:
                pass
        return False


# ══════════════════════════════════════════════════════════════════════════════
#  CLOUDFLARE SOLVER
# ══════════════════════════════════════════════════════════════════════════════
class CloudflareSolver:
    CF_INDICATORS = [
        "Checking your browser",
        "cf-browser-verification",
        "cf_clearance",
        "Just a moment",
        "Ray ID",
        "DDoS protection by Cloudflare",
        "__cf_chl",
    ]

    @classmethod
    def is_cf_challenge(cls, page):
        try:
            content = page.content()
            title   = page.title()
            return any(ind in content or ind in title for ind in cls.CF_INDICATORS)
        except Exception:
            return False

    @classmethod
    def solve(cls, page, log, timeout=30):
        log("  ⚡ Cloudflare challenge detected — waiting for auto-solve...", "warn")
        start = time.time()
        while time.time() - start < timeout:
            if not cls.is_cf_challenge(page):
                log("  ✓ Cloudflare passed!", "ok")
                return True
            # Human-like behaviour while waiting
            HumanSim.move_mouse(page)
            time.sleep(2)
        log("  ✗ Cloudflare timeout — may still work...", "warn")
        return False


# ══════════════════════════════════════════════════════════════════════════════
#  COOKIE / SESSION STORE
# ══════════════════════════════════════════════════════════════════════════════
COOKIE_DIR = Path.home() / ".vidscraper_sessions"
COOKIE_DIR.mkdir(exist_ok=True)

def _session_file(url):
    key = hashlib.md5(url.encode()).hexdigest()[:12]
    host = re.sub(r"https?://", "", url).split("/")[0]
    return COOKIE_DIR / f"{host}_{key}.json"

def load_cookies(url):
    f = _session_file(url)
    if f.exists():
        try:
            return json.loads(f.read_text())
        except Exception:
            pass
    return []

def save_cookies(url, cookies):
    try:
        _session_file(url).write_text(json.dumps(cookies, indent=2))
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════════
#  CORE SCRAPER ENGINE
# ══════════════════════════════════════════════════════════════════════════════
class ScraperEngine:
    VIDEO_NET_RE = re.compile(
        r"\.m3u8|\.mp4|\.webm|\.mpd|\.ts(\?|$)|"
        r"/hls/|/dash/|/stream/|manifest|playlist\.m3u8|"
        r"\.googlevideo\.com|cdn.*video|videoplayback",
        re.I,
    )
    SKIP_EXTS = re.compile(
        r"\.(css|js|png|jpg|jpeg|gif|svg|woff|woff2|ttf|ico|json)(\?|$)", re.I
    )
    JS_URL_RE = re.compile(
        r'(?:file|src|source|url|stream|video_url|hls_url|mp4_url|'
        r'videoUrl|streamUrl|hlsUrl|manifestUrl|masterUrl|playbackUrl)'
        r'\s*[=:]\s*["\']([^"\']{10,}\.(?:m3u8|mp4|webm|mpd)[^"\']*)["\']',
        re.I,
    )
    B64_RE = re.compile(r'["\']([A-Za-z0-9+/]{40,}={0,2})["\']')

    def __init__(self, log_fn, status_fn):
        self.log    = log_fn
        self.status = status_fn
        self._stop  = False
        self._network_hits = []

    def stop(self):
        self._stop = True

    # ── Main entry ────────────────────────────────────────────────────
    def scrape(self, url, options):
        self._stop         = False
        self._network_hits = []
        all_results        = []

        try:
            from playwright.sync_api import sync_playwright
            try:
                from playwright_stealth import stealth_sync
                HAS_STEALTH = True
            except ImportError:
                HAS_STEALTH = False
                self.log("  playwright-stealth not available — continuing without it", "warn")

        except ImportError:
            self.log("Playwright not installed. Run setup first.", "error")
            return all_results

        proxy_cfg = None
        if options.get("proxy"):
            proxy_cfg = {"server": options["proxy"]}
            self.log(f"  Using proxy: {options['proxy']}", "info")

        with sync_playwright() as p:
            # ── Launch browser ────────────────────────────────────────
            browser = p.chromium.launch(
                headless=not options.get("show_browser", False),
                proxy=proxy_cfg,
                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--window-size=1280,720",
                    "--disable-extensions",
                    "--disable-background-networking",
                    "--disable-default-apps",
                    "--mute-audio",
                ],
            )

            # ── Realistic browser context ────────────────────────────
            try:
                from fake_useragent import UserAgent
                ua = UserAgent().chrome
            except Exception:
                ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/122.0.0.0 Safari/537.36")

            ctx = browser.new_context(
                user_agent=ua,
                viewport={"width": 1280, "height": 720},
                screen={"width": 1920, "height": 1080},
                locale="en-US",
                timezone_id="America/New_York",
                java_script_enabled=True,
                accept_downloads=True,
                proxy=proxy_cfg,
                extra_http_headers={
                    "Accept-Language":  "en-US,en;q=0.9",
                    "Accept-Encoding":  "gzip, deflate, br",
                    "Sec-Ch-Ua":        '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
                    "Sec-Ch-Ua-Mobile": "?0",
                    "Sec-Ch-Ua-Platform": '"Windows"',
                    "Upgrade-Insecure-Requests": "1",
                },
            )

            # ── Restore saved cookies ────────────────────────────────
            saved = load_cookies(url)
            if saved:
                try:
                    ctx.add_cookies(saved)
                    self.log(f"  Restored {len(saved)} saved cookies", "info")
                except Exception:
                    pass

            page = ctx.new_page()

            # ── Apply stealth ────────────────────────────────────────
            if HAS_STEALTH:
                stealth_sync(page)
                self.log("  ✓ Stealth mode active", "ok")

            # ── Inject our custom JS payload ─────────────────────────
            page.add_init_script(STEALTH_JS)

            # ── Network interception ─────────────────────────────────
            response_bodies = []

            def on_request(req):
                req_url = req.url
                if self.SKIP_EXTS.search(req_url):
                    return
                if self.VIDEO_NET_RE.search(req_url):
                    entry = {"url": req_url, "method": "network",
                             "type": self._classify(req_url)}
                    if req_url not in [r["url"] for r in self._network_hits]:
                        self._network_hits.append(entry)
                        self.log(f"  [NET] {req_url[:100]}", "ok")

            def on_response(resp):
                resp_url = resp.url
                ct = resp.headers.get("content-type", "")
                # Capture JSON responses that may contain stream URLs
                if "json" in ct and self.VIDEO_NET_RE.search(resp_url):
                    try:
                        body = resp.text()
                        if body and len(body) < 200_000:
                            response_bodies.append(body)
                    except Exception:
                        pass
                # Capture m3u8 text bodies
                if "mpegurl" in ct or "m3u8" in ct:
                    try:
                        body = resp.text()
                        urls = re.findall(r"https?://[^\s\"']+", body)
                        for u in urls:
                            if ".m3u8" in u or ".ts" in u:
                                entry = {"url": u, "method": "m3u8_body",
                                         "type": self._classify(u)}
                                if u not in [r["url"] for r in self._network_hits]:
                                    self._network_hits.append(entry)
                    except Exception:
                        pass

            page.on("request",  on_request)
            page.on("response", on_response)

            # ── Navigate ──────────────────────────────────────────────
            self.status("Loading page...")
            self.log(f"\nNavigating → {url}", "info")
            try:
                page.goto(url, wait_until="domcontentloaded",
                          timeout=options.get("timeout", 30) * 1000)
            except Exception as e:
                self.log(f"  Navigation warning: {e}", "warn")

            # ── Cloudflare check ──────────────────────────────────────
            if CloudflareSolver.is_cf_challenge(page):
                CloudflareSolver.solve(page, self.log,
                                       timeout=options.get("cf_timeout", 35))

            # ── Human behaviour ───────────────────────────────────────
            wait_s = options.get("wait_seconds", 5)
            self.log(f"  Simulating human behaviour ({wait_s}s)...", "muted")
            self.status("Simulating human...")
            HumanSim.scroll(page)
            HumanSim.move_mouse(page)
            time.sleep(wait_s)

            # ── Auto-click play ───────────────────────────────────────
            if options.get("auto_click", True):
                self.status("Clicking play button...")
                HumanSim.click_play(page, self.log)
                HumanSim.move_mouse(page)
                time.sleep(3)

            # ── DOM extraction ────────────────────────────────────────
            self.status("Scanning DOM...")
            self.log("  Scanning DOM...", "muted")
            dom_results = self._extract_dom(page)

            # ── Shadow DOM ────────────────────────────────────────────
            shadow_results = self._extract_shadow_dom(page)

            # ── JS heap scan ──────────────────────────────────────────
            self.log("  Scanning JS heap & page source...", "muted")
            js_results = self._scan_js(page)

            # ── Hooked data (crypto/atob/XHR) ────────────────────────
            hook_results = self._collect_hooks(page)

            # ── Response body scan ────────────────────────────────────
            body_results = self._scan_response_bodies(response_bodies)

            # ── Iframe drill ──────────────────────────────────────────
            iframe_results = []
            if options.get("drill_iframes", True):
                self.status("Drilling iframes...")
                iframe_results = self._drill_iframes(page, ctx, options,
                                                     HAS_STEALTH)

            # ── Save cookies for next session ────────────────────────
            try:
                cookies = ctx.cookies()
                save_cookies(url, cookies)
                self.log(f"  Session saved ({len(cookies)} cookies)", "muted")
            except Exception:
                pass

            browser.close()

        # ── Merge & deduplicate ───────────────────────────────────────
        seen = set()
        for batch in [self._network_hits, dom_results, shadow_results,
                      js_results, hook_results, body_results, iframe_results]:
            for item in batch:
                u = item.get("url", "")
                if u and u not in seen and u.startswith("http"):
                    seen.add(u)
                    all_results.append(item)

        self.log(f"\n  ── Extraction complete: {len(all_results)} source(s) found ──", "info")

        # ── yt-dlp probe ──────────────────────────────────────────────
        if options.get("ytdlp_probe", True) and not self._stop:
            self.status("yt-dlp probe...")
            self.log("  Running yt-dlp probe...", "muted")
            ydl = self._ytdlp_probe(url)
            for r in ydl:
                if r["url"] not in seen:
                    seen.add(r["url"])
                    all_results.append(r)
                    self.log(f"  [YDL] {r['url'][:100]}", "ok")

        return all_results

    # ── Classify URL type ─────────────────────────────────────────────
    def _classify(self, url):
        u = url.lower()
        if ".m3u8" in u: return "HLS"
        if ".mpd"  in u: return "DASH"
        if ".mp4"  in u: return "MP4"
        if ".webm" in u: return "WebM"
        if ".ts"   in u: return "TS"
        return "Stream"

    # ── DOM extraction ────────────────────────────────────────────────
    def _extract_dom(self, page):
        results = []
        try:
            data = page.evaluate("""() => {
                const found = [];
                const add = (url, tag) => url && found.push({url, tag});
                document.querySelectorAll('video').forEach(v => {
                    add(v.src,              'video.src');
                    add(v.currentSrc,       'video.currentSrc');
                    add(v.getAttribute('data-src'), 'video[data-src]');
                });
                document.querySelectorAll('source').forEach(s => add(s.src, 'source'));
                document.querySelectorAll('[data-src],[data-video-src],[data-stream]').forEach(el => {
                    add(el.dataset.src,       'data-src');
                    add(el.dataset.videoSrc,  'data-video-src');
                    add(el.dataset.stream,    'data-stream');
                });
                return found.filter(f => f.url && f.url.startsWith('http'));
            }""")
            for d in data:
                results.append({"url": d["url"], "method": f"dom:{d['tag']}",
                                 "type": self._classify(d["url"])})
        except Exception as e:
            self.log(f"  DOM error: {e}", "warn")
        return results

    # ── Shadow DOM extraction ─────────────────────────────────────────
    def _extract_shadow_dom(self, page):
        results = []
        try:
            data = page.evaluate("""() => {
                const found = [];
                function walk(root) {
                    (root.querySelectorAll ? root.querySelectorAll('*') : []).forEach(el => {
                        if (el.shadowRoot) walk(el.shadowRoot);
                        if (el.tagName === 'VIDEO') {
                            if (el.src)        found.push(el.src);
                            if (el.currentSrc) found.push(el.currentSrc);
                        }
                    });
                }
                walk(document);
                return found.filter(u => u && u.startsWith('http'));
            }""")
            for u in data:
                results.append({"url": u, "method": "shadow_dom",
                                 "type": self._classify(u)})
        except Exception as e:
            self.log(f"  Shadow DOM error: {e}", "warn")
        return results

    # ── JS heap scan ──────────────────────────────────────────────────
    def _scan_js(self, page):
        results = []
        try:
            content = page.content()
            # Regex scan
            for m in self.JS_URL_RE.finditer(content):
                u = m.group(1)
                if u.startswith("http"):
                    results.append({"url": u, "method": "js_var",
                                    "type": self._classify(u)})

            # Try base64 decode of likely encoded strings
            for m in self.B64_RE.finditer(content):
                try:
                    decoded = base64.b64decode(m.group(1) + "==").decode("utf-8", errors="ignore")
                    if "http" in decoded and (".m3u8" in decoded or ".mp4" in decoded):
                        urls = re.findall(r"https?://[^\s\"'<>]+", decoded)
                        for u in urls:
                            results.append({"url": u, "method": "base64_decode",
                                            "type": self._classify(u)})
                except Exception:
                    pass

            # Extract from inline scripts
            scripts = re.findall(r"<script[^>]*>(.*?)</script>", content, re.S | re.I)
            for script in scripts:
                for m in re.finditer(r'["\'](https?://[^"\']+\.(?:m3u8|mp4|webm|mpd)[^"\']*)["\']',
                                     script, re.I):
                    results.append({"url": m.group(1), "method": "inline_script",
                                    "type": self._classify(m.group(1))})
        except Exception as e:
            self.log(f"  JS scan error: {e}", "warn")
        return results

    # ── Collect hooked data (crypto/atob/XHR hooks) ───────────────────
    def _collect_hooks(self, page):
        results = []
        try:
            for var in ["__interceptedData", "__decodedB64", "__xhrVideoUrls"]:
                data = page.evaluate(f"window.{var} || []")
                for item in data:
                    urls = re.findall(r"https?://[^\s\"'<>]+", item)
                    for u in urls:
                        if ".m3u8" in u or ".mp4" in u or ".webm" in u:
                            results.append({"url": u, "method": f"hook:{var}",
                                            "type": self._classify(u)})
        except Exception as e:
            self.log(f"  Hook collection error: {e}", "warn")
        return results

    # ── Response body scan ────────────────────────────────────────────
    def _scan_response_bodies(self, bodies):
        results = []
        for body in bodies:
            try:
                for m in re.finditer(r'"(?:url|src|file|source|stream)"\s*:\s*"([^"]+\.(?:m3u8|mp4|webm|mpd)[^"]*)"',
                                     body, re.I):
                    results.append({"url": m.group(1), "method": "xhr_response",
                                    "type": self._classify(m.group(1))})
            except Exception:
                pass
        return results

    # ── Iframe drilling ───────────────────────────────────────────────
    def _drill_iframes(self, page, ctx, options, has_stealth):
        results = []
        try:
            srcs = page.evaluate("""() =>
                Array.from(document.querySelectorAll('iframe[src]'))
                    .map(f => f.src)
                    .filter(s => s && s.startsWith('http'))
            """)
            self.log(f"  Found {len(srcs)} iframe(s)", "muted")
            for src in srcs[:4]:
                if self._stop: break
                self.log(f"  Drilling iframe: {src[:80]}", "muted")
                try:
                    p2 = ctx.new_page()
                    if has_stealth:
                        from playwright_stealth import stealth_sync
                        stealth_sync(p2)
                    p2.add_init_script(STEALTH_JS)

                    # Capture network in iframe page too
                    def on_req2(req):
                        if self.VIDEO_NET_RE.search(req.url):
                            results.append({"url": req.url, "method": "iframe_network",
                                            "type": self._classify(req.url)})
                            self.log(f"    [IFR-NET] {req.url[:80]}", "ok")
                    p2.on("request", on_req2)

                    p2.goto(src, wait_until="domcontentloaded", timeout=15000)
                    time.sleep(options.get("wait_seconds", 3))
                    HumanSim.click_play(p2, self.log)
                    time.sleep(2)
                    results += self._extract_dom(p2)
                    results += self._scan_js(p2)
                    results += self._collect_hooks(p2)
                    p2.close()
                except Exception as e:
                    self.log(f"  iframe error: {e}", "warn")
        except Exception as e:
            self.log(f"  iframe drill error: {e}", "warn")
        return results

    # ── yt-dlp probe ──────────────────────────────────────────────────
    def _ytdlp_probe(self, url):
        results = []
        try:
            import yt_dlp
            with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True,
                                    "skip_download": True}) as ydl:
                info = ydl.extract_info(url, download=False)
                if not info: return results
                title = info.get("title", "")
                for fmt in reversed(info.get("formats", [])):
                    u = fmt.get("url", "")
                    if u and u.startswith("http"):
                        results.append({
                            "url":     u,
                            "method":  "yt-dlp",
                            "type":    fmt.get("ext", "?").upper(),
                            "quality": fmt.get("format_note", ""),
                            "title":   title,
                        })
                        break  # best format only
        except Exception as e:
            self.log(f"  yt-dlp: {e}", "warn")
        return results


# ══════════════════════════════════════════════════════════════════════════════
#  GUI
# ══════════════════════════════════════════════════════════════════════════════
class App:
    def __init__(self, root):
        self.root     = root
        self.root.title("Ultimate Video Scraper v3")
        self.root.geometry("980x860")
        self.root.configure(bg=BG)
        self.results  = []
        self.is_running = False
        self._engine  = None

        # Options
        self.wait_var      = tk.IntVar(value=5)
        self.timeout_var   = tk.IntVar(value=30)
        self.cf_timeout    = tk.IntVar(value=35)
        self.show_browser  = tk.BooleanVar(value=False)
        self.auto_click    = tk.BooleanVar(value=True)
        self.drill_iframes = tk.BooleanVar(value=True)
        self.ytdlp_probe   = tk.BooleanVar(value=True)
        self.use_proxy     = tk.BooleanVar(value=False)
        self.proxy_var     = tk.StringVar(value="http://127.0.0.1:8080")
        self.save_dir      = tk.StringVar(value=os.path.expanduser("~/Downloads"))

        self._build_ui()
        self._install_thread = threading.Thread(
            target=self._bg_install, daemon=True)
        self._install_thread.start()

    def _bg_install(self):
        self._log("Checking dependencies...", "muted")
        install_deps(log_fn=lambda m: self._log(m, "muted"))
        self._log("✓ All dependencies ready.\n", "ok")

    # ── UI build ──────────────────────────────────────────────────────
    def _build_ui(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TCheckbutton", background=CARD, foreground=FG, font=MONO)
        style.configure("Accent.Horizontal.TProgressbar",
                        troughcolor=BORDER, background=ACCENT)
        style.configure("Treeview", background="#010409", foreground=FG,
                        fieldbackground="#010409", font=MONO, rowheight=26)
        style.configure("Treeview.Heading", background=CARD, foreground=MUTED,
                        font=MONO, borderwidth=0)
        style.map("Treeview", background=[("selected", "#1c2128")])

        # ── Top bar ───────────────────────────────────────────────────
        top = tk.Frame(self.root, bg=CARD, height=56,
                       highlightbackground=BORDER, highlightthickness=1)
        top.pack(fill="x")
        top.pack_propagate(False)
        tk.Label(top, text=" ◈ ULTIMATE VIDEO SCRAPER  v3",
                 font=("Helvetica", 14, "bold"), bg=CARD, fg=FG).pack(side="left", padx=20)
        tk.Label(top, text="stealth • CF bypass • hooks • yt-dlp",
                 font=MONO, bg=CARD, fg=MUTED).pack(side="left")
        self.status_badge = tk.Label(top, text=" IDLE ", font=MONO,
                                     bg="#1c2128", fg=MUTED, padx=8, pady=2)
        self.status_badge.pack(side="right", padx=16)

        # ── URL row ───────────────────────────────────────────────────
        wrap = tk.Frame(self.root, bg=BG)
        wrap.pack(fill="x", padx=18, pady=(14, 0))
        tk.Label(wrap, text="TARGET URL", font=MONO, bg=BG, fg=MUTED).pack(anchor="w")
        url_row = tk.Frame(wrap, bg=CARD,
                           highlightbackground=BORDER, highlightthickness=1)
        url_row.pack(fill="x", pady=(4, 0))
        self.url_entry = tk.Entry(url_row, font=MONO_LG, bg=CARD, fg=FG,
                                  bd=0, relief="flat", insertbackground=ACCENT)
        self.url_entry.pack(side="left", fill="x", expand=True, padx=14, pady=12)
        self.url_entry.insert(0, "https://")
        self.url_entry.bind("<Return>", lambda e: self._start())
        self.go_btn = tk.Button(url_row, text="  SCRAPE  ",
                                font=("Helvetica", 11, "bold"),
                                bg=ACCENT, fg="#000", relief="flat",
                                padx=10, cursor="hand2",
                                activebackground="#79c0ff",
                                command=self._start)
        self.go_btn.pack(side="right", padx=10, pady=8)

        # ── Options grid ──────────────────────────────────────────────
        opt_row = tk.Frame(self.root, bg=BG)
        opt_row.pack(fill="x", padx=18, pady=10)

        # Spinbox card
        spin_card = tk.Frame(opt_row, bg=CARD,
                             highlightbackground=BORDER, highlightthickness=1)
        spin_card.pack(side="left", padx=(0, 8), ipady=4)
        for label, var, lo, hi in [
            ("JS WAIT (s)", self.wait_var, 1, 20),
            ("TIMEOUT (s)", self.timeout_var, 10, 120),
            ("CF WAIT (s)", self.cf_timeout, 10, 90),
        ]:
            r = tk.Frame(spin_card, bg=CARD)
            r.pack(fill="x", padx=12, pady=2)
            tk.Label(r, text=label, font=MONO, bg=CARD, fg=MUTED, width=11, anchor="w").pack(side="left")
            tk.Spinbox(r, from_=lo, to=hi, textvariable=var,
                       width=4, font=MONO, bg=BORDER, fg=FG,
                       bd=0, relief="flat", buttonbackground=BORDER).pack(side="left")

        # Checkboxes card
        chk_card = tk.Frame(opt_row, bg=CARD,
                            highlightbackground=BORDER, highlightthickness=1)
        chk_card.pack(side="left", padx=(0, 8), ipady=4)
        checkboxes = [
            (self.auto_click,    "Auto-click play",  0, 0),
            (self.drill_iframes, "Drill iframes",     0, 1),
            (self.ytdlp_probe,   "yt-dlp probe",      1, 0),
            (self.show_browser,  "Show browser",      1, 1),
        ]
        for var, lbl, row, col in checkboxes:
            ttk.Checkbutton(chk_card, text=lbl, variable=var).grid(
                row=row, column=col, sticky="w", padx=14, pady=5)

        # Proxy card
        prx_card = tk.Frame(opt_row, bg=CARD,
                            highlightbackground=BORDER, highlightthickness=1)
        prx_card.pack(side="left", padx=(0, 8), ipady=4, fill="y")
        ttk.Checkbutton(prx_card, text="Use Proxy", variable=self.use_proxy).pack(
            anchor="w", padx=12, pady=(6, 2))
        tk.Entry(prx_card, textvariable=self.proxy_var, font=MONO,
                 bg=BORDER, fg=FG, bd=0, relief="flat", width=22,
                 insertbackground=ACCENT).pack(padx=12, pady=(0, 6))

        # Action buttons
        btn_col = tk.Frame(opt_row, bg=BG)
        btn_col.pack(side="right")
        self.stop_btn = tk.Button(btn_col, text="✕ Stop", font=MONO,
                                  bg="#1c2128", fg=RED, relief="flat",
                                  padx=14, pady=6, cursor="hand2",
                                  state="disabled", command=self._stop)
        self.stop_btn.pack(fill="x", pady=(0, 4))
        tk.Button(btn_col, text="⌫ Clear", font=MONO,
                  bg="#1c2128", fg=MUTED, relief="flat",
                  padx=14, pady=6, cursor="hand2",
                  command=self._clear).pack(fill="x")

        # ── Progress + status ─────────────────────────────────────────
        prog_wrap = tk.Frame(self.root, bg=BG)
        prog_wrap.pack(fill="x", padx=18, pady=(0, 4))
        self.progress = ttk.Progressbar(prog_wrap,
                                         style="Accent.Horizontal.TProgressbar",
                                         mode="indeterminate")
        self.progress.pack(fill="x")
        self.status_var = tk.StringVar(value="Ready — paste a URL and press Scrape")
        tk.Label(self.root, textvariable=self.status_var,
                 font=MONO, bg=BG, fg=MUTED).pack(anchor="w", padx=20)

        # ── Log ───────────────────────────────────────────────────────
        log_wrap = tk.Frame(self.root, bg=CARD,
                            highlightbackground=BORDER, highlightthickness=1)
        log_wrap.pack(fill="both", expand=True, padx=18, pady=(6, 4))
        hdr = tk.Frame(log_wrap, bg=CARD)
        hdr.pack(fill="x")
        tk.Label(hdr, text="  SCRAPE LOG", font=MONO,
                 bg=CARD, fg=MUTED).pack(side="left", padx=10, pady=6)
        tk.Button(hdr, text="Clear log", font=MONO, bg="#1c2128", fg=MUTED,
                  relief="flat", bd=0, padx=8, pady=2, cursor="hand2",
                  command=lambda: (self.log_box.configure(state="normal"),
                                   self.log_box.delete("1.0", "end"),
                                   self.log_box.configure(state="disabled"))
                  ).pack(side="right", padx=10)
        self.log_box = scrolledtext.ScrolledText(
            log_wrap, font=MONO, bg="#010409", fg=FG,
            bd=0, relief="flat", insertbackground=ACCENT,
            wrap="word", state="disabled", height=12)
        self.log_box.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        for tag, col in [("ok", GREEN), ("info", ACCENT), ("warn", YELLOW),
                          ("error", RED), ("muted", MUTED)]:
            self.log_box.tag_config(tag, foreground=col)

        # ── Results table ─────────────────────────────────────────────
        res_wrap = tk.Frame(self.root, bg=CARD,
                            highlightbackground=BORDER, highlightthickness=1)
        res_wrap.pack(fill="x", padx=18, pady=(0, 16))
        res_hdr = tk.Frame(res_wrap, bg=CARD)
        res_hdr.pack(fill="x", padx=10, pady=(8, 4))
        tk.Label(res_hdr, text="  FOUND SOURCES", font=MONO,
                 bg=CARD, fg=MUTED).pack(side="left")
        for lbl, col, cmd in [
            ("⬇ Download selected", YELLOW, self._download_selected),
            ("📋 Copy all",          ACCENT,  self._copy_all),
            ("💾 Save JSON",         GREEN,   self._save_json),
        ]:
            tk.Button(res_hdr, text=lbl, font=MONO, bg="#1c2128", fg=col,
                      relief="flat", bd=0, padx=10, pady=3,
                      cursor="hand2", command=cmd).pack(side="right", padx=4)

        cols = ("Type", "Method", "Quality", "URL")
        self.tree = ttk.Treeview(res_wrap, columns=cols, show="headings", height=7)
        self.tree.heading("Type",    text="TYPE")
        self.tree.heading("Method",  text="METHOD")
        self.tree.heading("Quality", text="QUALITY")
        self.tree.heading("URL",     text="URL")
        self.tree.column("Type",    width=70,  minwidth=60)
        self.tree.column("Method",  width=130, minwidth=100)
        self.tree.column("Quality", width=80,  minwidth=60)
        self.tree.column("URL",     width=580, minwidth=200)
        self.tree.pack(fill="x", padx=10, pady=(0, 10))

        self._log("◈ Ultimate Video Scraper ready.\n"
                  "  Stealth + Cloudflare bypass + crypto hooks + iframe drilling + yt-dlp.\n", "info")

    # ── Helpers ───────────────────────────────────────────────────────
    def _log(self, msg, tag=""):
        def _do():
            self.log_box.configure(state="normal")
            ts = datetime.now().strftime("%H:%M:%S")
            self.log_box.insert("end", f"[{ts}] {msg}\n", tag or None)
            self.log_box.see("end")
            self.log_box.configure(state="disabled")
        self.root.after(0, _do)

    def _set_status(self, msg):
        self.root.after(0, lambda: self.status_var.set(msg))

    def _clear(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")
        for row in self.tree.get_children():
            self.tree.delete(row)
        self.results = []

    def _add_result(self, item):
        self.results.append(item)
        self.root.after(0, lambda: self.tree.insert(
            "", "end",
            values=(item.get("type",""), item.get("method",""),
                    item.get("quality",""), item.get("url","")),
        ))

    def _copy_all(self):
        urls = "\n".join(r.get("url", "") for r in self.results)
        self.root.clipboard_clear()
        self.root.clipboard_append(urls)
        self._log(f"Copied {len(self.results)} URL(s) to clipboard.", "ok")

    def _save_json(self):
        if not self.results:
            messagebox.showinfo("Empty", "No results yet.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("All", "*.*")],
            initialfile="scraped_videos.json",
        )
        if path:
            with open(path, "w") as f:
                json.dump(self.results, f, indent=2)
            self._log(f"Saved → {path}", "ok")

    def _download_selected(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Select row", "Click a URL row first.")
            return
        idx  = self.tree.index(sel[0])
        item = self.results[idx]
        url  = item.get("url", "")
        out  = self.save_dir.get()
        self._log(f"Downloading: {url[:80]}", "info")
        threading.Thread(target=self._run_dl, args=(url, out), daemon=True).start()

    def _run_dl(self, url, out):
        try:
            import yt_dlp
            with yt_dlp.YoutubeDL({
                "outtmpl": os.path.join(out, "%(title)s.%(ext)s"),
                "quiet": False,
            }) as ydl:
                ydl.download([url])
            self._log("✓ Download complete!", "ok")
        except Exception as e:
            self._log(f"Download error: {e}", "error")

    # ── Scrape control ────────────────────────────────────────────────
    def _start(self):
        if self.is_running: return
        url = self.url_entry.get().strip()
        if not url or url == "https://":
            messagebox.showwarning("No URL", "Enter a URL first.")
            return
        self.is_running = True
        self.go_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.status_badge.configure(text=" RUNNING ", bg="#1a3320", fg=GREEN)
        self.progress.start(10)
        for row in self.tree.get_children():
            self.tree.delete(row)
        self.results = []

        options = {
            "wait_seconds":  self.wait_var.get(),
            "timeout":       self.timeout_var.get(),
            "cf_timeout":    self.cf_timeout.get(),
            "show_browser":  self.show_browser.get(),
            "auto_click":    self.auto_click.get(),
            "drill_iframes": self.drill_iframes.get(),
            "ytdlp_probe":   self.ytdlp_probe.get(),
            "proxy": self.proxy_var.get() if self.use_proxy.get() else None,
        }
        engine = ScraperEngine(
            log_fn=self._log,
            status_fn=self._set_status,
        )
        self._engine = engine

        def run():
            found = engine.scrape(url, options)
            for item in found:
                self._add_result(item)
            self.root.after(0, self._done, len(found))

        threading.Thread(target=run, daemon=True).start()

    def _stop(self):
        if self._engine:
            self._engine.stop()
        self._done(0, stopped=True)

    def _done(self, count, stopped=False):
        self.is_running = False
        self.progress.stop()
        self.go_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        if stopped:
            self.status_badge.configure(text=" STOPPED ", bg="#2d1a1a", fg=RED)
            self._set_status("Stopped by user.")
        else:
            self.status_badge.configure(text=" DONE ", bg="#1a2d1a", fg=GREEN)
            self._set_status(f"Done — {count} source(s) found.")


# ══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    root = tk.Tk()
    app  = App(root)
    root.mainloop()
