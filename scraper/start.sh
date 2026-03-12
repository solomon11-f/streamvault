#!/bin/bash

pip install -r requirements.txt
playwright install chromium

uvicorn api:app --host 0.0.0.0 --port 8000