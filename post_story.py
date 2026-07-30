#!/usr/bin/env python3
"""
Instagram Auto-Poster for @myshishaecigeu
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Posts images/videos from the stories/ folder to Instagram.
Runs automatically via GitHub Actions at 10 AM and 8 PM (UAE time) every day.


TO ADD NEW STORIES:
  Upload your images to the stories/ folder in this GitHub repo.
  They will be posted in alphabetical order, one per scheduled run.
"""


import os
import sys
import json
import time
import argparse
import requests
from pathlib import Path
from datetime import datetime


# ──────────────────────────────────────────────────────────────
# CREDENTIALS — loaded from GitHub Secrets (environment variables)
# ──────────────────────────────────────────────────────────────
ACCESS_TOKEN = os.environ.get("ACCESS_TOKEN", "")
APP_ID       = os.environ.get("APP_ID",       "1064773792747496")
APP_SECRET   = os.environ.get("APP_SECRET",   "615d7a1a3cb33bc8529a787ad8fff139")
IG_USER_ID   = os.environ.get("IG_USER_ID",   "17841448557709921")
API_VER      = "v25.0"
BASE_URL     = f"https://graph.facebook.com/{API_VER}"
# ──────────────────────────────────────────────────────────────


# Stories folder is relative to the script (inside the GitHub repo)
STORIES_DIR = Path(__file__).parent  # images go in repo root
POSTED_FILE = STORIES_DIR / ".posted.json"
LOG_FILE    = STORIES_DIR / "post.log"
