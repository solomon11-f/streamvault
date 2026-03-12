
# StreamVault Complete

This package gives you a working local StreamVault setup with:

- your full gold/black StreamVault UI
- a Node backend that stores users, settings, and videos
- email verification support through Gmail SMTP
- an admin anime finder for HiAnime / AniWatch-style searching
- a Python scraper API that wraps your uploaded `Video Scraper v3.py`

## What still needs your setup

I cannot create your external accounts for you. You need to do these parts yourself:

1. Install Node.js and Python on your Mac
2. Install Playwright Chromium for the scraper
3. Add your Gmail SMTP values into `.env` if you want real email sending
4. If you later want Supabase, use the SQL file in `supabase/schema.sql`

## Local launch on Mac

Open **two Terminal windows**.

### Terminal A — scraper

```bash
cd ~/Downloads/streamvault_complete/scraper
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
uvicorn api:app --host 127.0.0.1 --port 8000
```

You should see the scraper API start on port 8000.

### Terminal B — backend and app

```bash
cd ~/Downloads/streamvault_complete/backend
cp .env.example .env
npm install
node server.js
```

Then open:

```text
http://localhost:3000
```

## Default local login

Entry code:

```text
1234
```

Admin email:

```text
admin@streamvault.com
```

Admin password:

```text
admin123
```

## Gmail SMTP setup

Edit `backend/.env`.

```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_SECURE=false
SMTP_USER=your_gmail@gmail.com
SMTP_PASS=your_16_char_app_password
SMTP_FROM=your_gmail@gmail.com
```

If SMTP is not configured, signup still works in **dev mode** and the app will show the verification code in a prompt flow.

## Supabase setup

This project runs locally without Supabase.

If you want Supabase later, create a project and run the SQL in:

```text
supabase/schema.sql
```

That file gives you a schema you can migrate to once you want cloud storage instead of the local JSON store in `backend/data/store.json`.

## Deploy later

- Backend: Render
- Scraper: Railway
- Frontend: served by backend right now, or move `frontend/` to Cloudflare Pages later

## Notes

- The scraper depends on the target site still matching the selectors and anti-bot conditions.
- HiAnime / AniWatch pages change often, so provider search and episode discovery may need occasional selector updates.
- Your original `Video Scraper v3.py` is included and wrapped; the GUI version is preserved.
