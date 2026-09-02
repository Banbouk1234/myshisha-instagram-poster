#!/usr/bin/env python3
"""
Instagram Auto-Poster for @myshishaecigeu
Posts images from the repo to Instagram Stories.
Runs via GitHub Actions at 10 AM and 8 PM UAE time daily.
"""

import os
import sys
import json
import time
import requests
from pathlib import Path
from datetime import datetime, timezone

# ── Credentials from GitHub Secrets (no defaults for secrets) ─
ACCESS_TOKEN = os.environ.get("ACCESS_TOKEN", "")
APP_ID       = os.environ.get("APP_ID",       "1064773792747496")
APP_SECRET   = os.environ.get("APP_SECRET",   "")
IG_USER_ID   = os.environ.get("IG_USER_ID",   "17841448557709921")
GITHUB_REPO  = os.environ.get("GITHUB_REPOSITORY", "Banbouk1234/myshisha-instagram-poster")
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
        posted.clear()
        images = sorted([f for f in STORIES_DIR.iterdir() if f.suffix in exts])
    return images[0] if images else None


def get_public_url(image_path):
    """Return a raw.githubusercontent.com URL for the image.
    Works because this repo is public."""
    filename = image_path.name
    return f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/{filename}"


def create_container(image_url):
    log(f"Creating Instagram Stories container ...")
    log(f"  image_url: {image_url}")
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
    log(f"GITHUB_REPO: {GITHUB_REPO}")

    posted = load_posted()
    log(f"Already posted: {len(posted)} images")

    image = get_next_image(posted)
    if not image:
        log("No images found in repo. Nothing to post.")
        sys.exit(0)

    log(f"Next image: {image.name}")

    try:
        image_url  = get_public_url(image)
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
