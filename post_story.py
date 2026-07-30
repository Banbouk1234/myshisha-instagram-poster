#!/usr/bin/env python3
"""
Instagram Auto-Poster for @myshishaecigeu
Posts images from the repo root to Instagram Stories.
Runs via GitHub Actions at 10 AM and 8 PM UAE time daily.
"""

import os
import sys
import json
import time
import requests
from pathlib import Path
from datetime import datetime, timezone

# ── Credentials from GitHub Secrets ──────────────────────────
ACCESS_TOKEN = os.environ.get("ACCESS_TOKEN", "")
APP_ID       = os.environ.get("APP_ID",       "1064773792747496")
APP_SECRET   = os.environ.get("APP_SECRET",   "615d7a1a3cb33bc8529a787ad8fff139")
IG_USER_ID   = os.environ.get("IG_USER_ID",   "17841448557709921")
API_VER      = "v25.0"
BASE_URL     = f"https://graph.facebook.com/{API_VER}"
# ─────────────────────────────────────────────────────────────

STORIES_DIR  = Path(__file__).parent
POSTED_FILE  = STORIES_DIR / ".posted.json"
LOG_FILE     = STORIES_DIR / "post.log"


def log(msg):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def load_posted():
    if POSTED_FILE.exists():
        try:
            return json.loads(POSTED_FILE.read_text())
        except Exception:
            pass
    return []


def save_posted(posted):
    POSTED_FILE.write_text(json.dumps(posted, indent=2))


def get_next_image(posted):
    exts = {".png", ".jpg", ".jpeg", ".PNG", ".JPG", ".JPEG"}
    images = sorted([
        f for f in STORIES_DIR.iterdir()
        if f.suffix in exts and f.name not in posted
    ])
    if not images:
        log("All images posted. Resetting cycle.")
        images = sorted([f for f in STORIES_DIR.iterdir() if f.suffix in exts])
    return images[0] if images else None


def upload_image(image_path):
    """Try multiple public image hosts until one works."""

    # 1. Try 0x0.st
    try:
        log("Trying 0x0.st ...")
        with open(image_path, "rb") as f:
            resp = requests.post(
                "https://0x0.st",
                files={"file": (image_path.name, f)},
                timeout=30
            )
        url = resp.text.strip()
        if resp.ok and url.startswith("https://"):
            log(f"Uploaded to 0x0.st: {url}")
            return url
        log(f"0x0.st failed: {resp.status_code} {resp.text[:80]}")
    except Exception as e:
        log(f"0x0.st error: {e}")

    # 2. Try litterbox.catbox.moe (temporary, different from catbox)
    try:
        log("Trying litterbox.catbox.moe ...")
        with open(image_path, "rb") as f:
            resp = requests.post(
                "https://litterbox.catbox.moe/resources/internals/api.php",
                data={"reqtype": "fileupload", "time": "24h"},
                files={"fileToUpload": (image_path.name, f)},
                timeout=60
            )
        url = resp.text.strip()
        if resp.ok and url.startswith("https://"):
            log(f"Uploaded to litterbox: {url}")
            return url
        log(f"litterbox failed: {resp.status_code} {resp.text[:80]}")
    except Exception as e:
        log(f"litterbox error: {e}")

    # 3. Try file.io
    try:
        log("Trying file.io ...")
        with open(image_path, "rb") as f:
            resp = requests.post(
                "https://file.io/?expires=1d",
                files={"file": (image_path.name, f)},
                timeout=30
            )
        data = resp.json()
        if data.get("success") and data.get("link"):
            url = data["link"]
            log(f"Uploaded to file.io: {url}")
            return url
        log(f"file.io failed: {data}")
    except Exception as e:
        log(f"file.io error: {e}")

    raise RuntimeError("All image hosts failed — cannot get a public URL")


def create_container(image_url):
    log(f"Creating Instagram Stories container with image_url ...")
    resp = requests.post(
        f"{BASE_URL}/{IG_USER_ID}/media",
        data={
            "image_url":    image_url,
            "media_type":   "STORIES",
            "access_token": ACCESS_TOKEN,
        },
        timeout=30
    )
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"Container creation error: {data['error']}")
    container_id = data["id"]
    log(f"Container created: {container_id}")
    return container_id


def wait_ready(container_id, max_wait=120):
    log("Waiting for container to be FINISHED ...")
    deadline = time.time() + max_wait
    while time.time() < deadline:
        resp = requests.get(
            f"{BASE_URL}/{container_id}",
            params={"fields": "status_code", "access_token": ACCESS_TOKEN},
            timeout=15
        )
        status = resp.json().get("status_code", "")
        log(f"  status: {status}")
        if status == "FINISHED":
            return True
        if status == "ERROR":
            raise RuntimeError("Container processing failed with ERROR status")
        time.sleep(5)
    raise RuntimeError("Container did not reach FINISHED in time")


def publish(container_id):
    log("Publishing story ...")
    resp = requests.post(
        f"{BASE_URL}/{IG_USER_ID}/media_publish",
        data={"creation_id": container_id, "access_token": ACCESS_TOKEN},
        timeout=30
    )
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"Publish error: {data['error']}")
    media_id = data.get("id")
    log(f"Published! Media ID: {media_id}")
    return media_id


def main():
    log("=== Instagram Story Poster started ===")

    if not ACCESS_TOKEN:
        log("ERROR: ACCESS_TOKEN is not set. Check GitHub Secrets.")
        sys.exit(1)

    log(f"IG_USER_ID: {IG_USER_ID}")
    log(f"STORIES_DIR: {STORIES_DIR}")

    posted = load_posted()
    log(f"Already posted: {len(posted)} images")

    image = get_next_image(posted)
    if not image:
        log("No images found in repo. Nothing to post.")
        sys.exit(0)

    log(f"Next image: {image.name}")

    try:
        image_url  = upload_image(image)
        container  = create_container(image_url)
        wait_ready(container)
        media_id   = publish(container)

        posted.append(image.name)
        save_posted(posted)
        log(f"Success! Posted {image.name} as story (media_id={media_id})")

    except Exception as e:
        log(f"ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
