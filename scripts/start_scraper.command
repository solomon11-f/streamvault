#!/bin/bash
cd "$(dirname "$0")/../scraper" || exit 1
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
uvicorn api:app --host 127.0.0.1 --port 8000
