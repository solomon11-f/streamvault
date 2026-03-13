from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import importlib.util
import pathlib
import sys
import types
from typing import Any

APP_DIR = pathlib.Path(__file__).resolve().parent
SCRAPER_PATH = APP_DIR / "video_scraper_v3.py"


def _install_tkinter_stubs() -> None:
    if 'tkinter' in sys.modules:
        return

    tk = types.ModuleType('tkinter')
    ttk = types.ModuleType('tkinter.ttk')
    scrolledtext = types.ModuleType('tkinter.scrolledtext')
    filedialog = types.ModuleType('tkinter.filedialog')
    messagebox = types.ModuleType('tkinter.messagebox')

    class _Dummy:
        def __init__(self, *args, **kwargs):
            pass

        def __call__(self, *args, **kwargs):
            return None

        def __getattr__(self, name: str):
            return self

    tk.Tk = _Dummy
    tk.Frame = _Dummy
    tk.Label = _Dummy
    tk.Button = _Dummy
    tk.Entry = _Dummy
    tk.StringVar = _Dummy
    tk.BooleanVar = _Dummy
    tk.IntVar = _Dummy
    tk.END = "end"
    tk.BOTH = tk.X = tk.Y = tk.LEFT = tk.RIGHT = tk.TOP = tk.BOTTOM = 0
    tk.N = tk.S = tk.E = tk.W = tk.NE = tk.NW = tk.SE = tk.SW = tk.CENTER = 0

    ttk.Frame = ttk.Label = ttk.Button = ttk.Entry = ttk.Checkbutton = ttk.Combobox = ttk.Progressbar = _Dummy
    scrolledtext.ScrolledText = _Dummy
    filedialog.askopenfilename = lambda *a, **k: ""
    messagebox.showinfo = lambda *a, **k: None
    messagebox.showerror = lambda *a, **k: None
    messagebox.askyesno = lambda *a, **k: False

    sys.modules['tkinter'] = tk
    sys.modules['tkinter.ttk'] = ttk
    sys.modules['tkinter.scrolledtext'] = scrolledtext
    sys.modules['tkinter.filedialog'] = filedialog
    sys.modules['tkinter.messagebox'] = messagebox


_install_tkinter_stubs()

spec = importlib.util.spec_from_file_location('video_scraper_v3_module', SCRAPER_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f'Could not load scraper from {SCRAPER_PATH}')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

if not hasattr(module, 'ScraperEngine'):
    raise RuntimeError('video_scraper_v3.py does not expose ScraperEngine')


def _log(*args: Any, **kwargs: Any) -> None:
    pass


def _status(*args: Any, **kwargs: Any) -> None:
    pass


engine = module.ScraperEngine(_log, _status)
app = FastAPI(title='StreamVault Extract API')


class ExtractRequest(BaseModel):
    url: str
    show_browser: bool = False


def _normalize_results(results: Any) -> dict[str, Any]:
    if isinstance(results, dict):
        if 'stream' in results or 'sources' in results:
            sources = results.get('sources') or []
            stream = results.get('stream') or (sources[0].get('url') if sources and isinstance(sources[0], dict) else None)
            return {
                'stream': stream,
                'sources': sources,
                'subtitles': results.get('subtitles') or [],
                'headers': results.get('headers') or {},
                'anilistID': results.get('anilistID'),
                'malID': results.get('malID'),
                'server': results.get('server'),
                'category': results.get('category'),
            }
        results = [results]

    if not isinstance(results, list):
        raise HTTPException(status_code=500, detail='Unexpected scraper result shape')

    urls: list[str] = []
    for item in results:
        if isinstance(item, str):
            urls.append(item)
            continue
        if not isinstance(item, dict):
            continue
        for key in ('url', 'stream', 'src', 'video', 'video_url', 'm3u8', 'mp4'):
            value = item.get(key)
            if isinstance(value, str) and value.startswith('http'):
                urls.append(value)
                break

    if not urls:
        raise HTTPException(status_code=404, detail='No playable stream found')

    def _is_m3u8(u: str) -> bool:
        return '.m3u8' in u.lower()

    best = next((u for u in urls if _is_m3u8(u)), urls[0])
    sources = [{'url': u, 'isM3U8': _is_m3u8(u), 'type': 'hls' if _is_m3u8(u) else 'file'} for u in urls]
    return {
        'stream': best,
        'sources': sources,
        'subtitles': [],
        'headers': {},
        'anilistID': None,
        'malID': None,
        'server': None,
        'category': None,
    }


@app.get('/health')
def health() -> dict[str, bool]:
    return {'ok': True}


@app.post('/extract')
def extract(body: ExtractRequest) -> dict[str, Any]:
    try:
        results = engine.scrape(body.url, body.model_dump())
        return _normalize_results(results)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
