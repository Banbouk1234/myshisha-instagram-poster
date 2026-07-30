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
STORIES_DIR = Path(__file__).parent / "stories"
POSTED_FILE = STORIES_DIR / ".posted.json"
LOG_FILE    = STORIES_DIR / "post.log"
VALID_EXT   = {".jpg", ".jpeg", ".png", ".mp4", ".mov"}


# ── Logging ─────────────────────────────────────────────

def log(msg: str):
    ts   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    STORIES_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


# ── Token management ──────────────────────────────────────────

def get_token() -> str:
    return ACCESS_TOKEN


def refresh_token() -> str:
    token = get_token()
    log("Refreshing access token ...")
    try:
        r = requests.get(
            f"{BASE_URL}/oauth/access_token",
            params={
                "grant_type":        "fb_exchange_token",
                "client_id":         APP_ID,
                "client_secret":     APP_SECRET,
                "fb_exchange_token": token,
            },
            timeout=30,
        )
        data = r.json()
        if "access_token" in data:
            days = int(data.get("expires_in", 0)) // 86400
            log(f"Token refreshed - valid for ~{days} days. Update the ACCESS_TOKEN secret in GitHub.")
            return data["access_token"]
        else:
            log(f"Token refresh failed: {data}")
    except Exception as e:
        log(f"Token refresh error: {e}")
    return token


# ── Image queue ───────────────────────────────────────────────

def load_posted() -> list:
    if POSTED_FILE.exists():
        return json.loads(POSTED_FILE.read_text())
    return []


def save_posted(lst: list):
    STORIES_DIR.mkdir(parents=True, exist_ok=True)
    POSTED_FILE.write_text(json.dumps(lst, indent=2))


def get_next_image() -> Path | None:
    STORIES_DIR.mkdir(parents=True, exist_ok=True)
    posted    = load_posted()
    all_files = sorted(
        f for f in STORIES_DIR.iterdir()
        if f.is_file() and f.suffix.lower() in VALID_EXT
    )
    if not all_files:
        return None

    unposted = [f for f in all_files if f.name not in posted]
    if not unposted:
        log("All images posted - restarting cycle.")
        save_posted([])
        unposted = all_files

    return unposted[0]


# ── Upload ────────────────────────────────────────────────────

def upload_image_to_host(file_path: Path) -> str:
    """Upload image to catbox.moe for a direct public URL."""
    mime = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png",
    }.get(file_path.suffix.lower(), "image/jpeg")

    with open(file_path, "rb") as fh:
        r = requests.post(
            "https://catbox.moe/user/api.php",
            data={"reqtype": "fileupload"},
            files={"fileToUpload": (file_path.name, fh, mime)},
            timeout=60,
        )
    url = r.text.strip()
    if not url.startswith("https://"):
        raise RuntimeError(f"Image hosting upload failed: {url!r}")
    log(f"  Image hosted at: {url}")
    return url


def upload_video_resumable(file_path: Path, token: str) -> str:
    """Upload video via Facebook Resumable Upload. Returns fb:// handle."""
    mime = {".mp4": "video/mp4", ".mov": "video/quicktime"}.get(
        file_path.suffix.lower(), "video/mp4"
    )
    file_size = file_path.stat().st_size
    app_token = f"{APP_ID}|{APP_SECRET}"

    r = requests.post(
        f"{BASE_URL}/{APP_ID}/uploads",
        params={"access_token": app_token, "file_type": mime, "file_length": file_size},
        timeout=30,
    )
    data = r.json()
    if "id" not in data:
        raise RuntimeError(f"Upload session failed: {data}")
    session_id = data["id"]
    log("  Upload session created")

    with open(file_path, "rb") as fh:
        raw = fh.read()

    r = requests.post(
        f"{BASE_URL}/{session_id}",
        headers={"Authorization": f"OAuth {app_token}", "file_offset": "0", "Content-Type": mime},
        data=raw,
        timeout=120,
    )
    data = r.json()
    if "h" not in data:
        raise RuntimeError(f"File upload failed: {data}")
    h = data["h"]
    if not h or "invalid" in str(h):
        raise RuntimeError(f"Invalid upload handle: {h!r}")
    log("  Upload handle obtained")
    return h


# ── Instagram API ───────────────────────────────────────────────

def create_container(media_url: str, is_video: bool, token: str) -> str:
    url_key = "video_url" if is_video else "image_url"
    params  = {
        "access_token": token,
        "media_type":   "STORIES",
        url_key:        media_url,
    }
    r    = requests.post(f"{BASE_URL}/{IG_USER_ID}/media", params=params, timeout=30)
    data = r.json()
    if "id" not in data:
        raise RuntimeError(f"Container creation failed: {data}")
    return data["id"]


def wait_ready(container_id: str, token: str, timeout: int = 180):
    deadline = time.time() + timeout
    while time.time() < deadline:
        r    = requests.get(
            f"{BASE_URL}/{container_id}",
            params={"access_token": token, "fields": "status_code"},
            timeout=15,
        )
        code = r.json().get("status_code", "")
        if code == "FINISHED":
            return
        if code == "ERROR":
            raise RuntimeError(f"Container error: {r.json()}")
        time.sleep(5)
    raise RuntimeError("Container timed out waiting to be FINISHED")


def publish(container_id: str, token: str) -> str:
    r    = requests.post(
        f"{BASE_URL}/{IG_USER_ID}/media_publish",
        params={"access_token": token, "creation_id": container_id},
        timeout=30,
    )
    data = r.json()
    if "id" not in data:
        raise RuntimeError(f"Publish failed: {data}")
    return data["id"]


# ── Main ──────────────────────────────────────────────────────

def post_story(token: str | None = None, retry: bool = True) -> bool:
    log("=" * 55)
    log("Starting Instagram post ...")

    token = token or get_token()
    if not token:
        log("No ACCESS_TOKEN found. Set the GitHub Secret.")
        return False

    img = get_next_image()
    if img is None:
        log("No images found in stories/ folder.")
        log("    Upload .jpg / .png / .mp4 files to the stories/ folder in GitHub.")
        return False

    log(f"Posting: {img.name}")
    is_video = img.suffix.lower() in {".mp4", ".mov"}

    try:
        log("  Uploading ...")
        if is_video:
            handle    = upload_video_resumable(img, token)
            media_url = f"fb://{handle}"
        else:
            media_url = upload_image_to_host(img)

        log("  Creating media container ...")
        container_id = create_container(media_url, is_video, token)

        log("  Waiting for media to be ready ...")
        wait_ready(container_id, token)

        log("  Publishing ...")
        post_id = publish(container_id, token)

        log(f"Posted! Instagram post ID: {post_id}")

        posted = load_posted()
        posted.append(img.name)
        save_posted(posted)
        return True

    except RuntimeError as e:
        log(f"Error: {e}")
        if retry and ("token" in str(e).lower() or "190" in str(e)):
            log("Attempting token refresh and retry ...")
            new_tok = refresh_token()
            return post_story(token=new_tok, retry=False)
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    STORIES_DIR.mkdir(parents=True, exist_ok=True)

    if args.refresh:
        refresh_token()
    else:
        ok = post_story()
        sys.exit(0 if ok else 1)
