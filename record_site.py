#!/usr/bin/env python3
"""Record a browser session as a 1280x720 clip. Usage: record_site.py steps.json out.webm

steps.json is a list of steps, run in order:
  {"goto": url}  {"click": selector}  {"fill": selector, "text": str}
  {"wait": ms}   {"wait_for": selector, "timeout": ms}  {"scroll": px}
Selectors are Playwright selectors, e.g. "text=Analyse" or "textarea".
Prints the seconds into the clip when the first goto finished loading, so the
spec can skip the blank start with "start".
"""
import json, os, shutil, sys, tempfile, time
from playwright.sync_api import sync_playwright

# shortcut: one shared profile so big assets (e.g. an in-browser model) stay cached between recordings
PROFILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".browser-profile")
SIZE = {"width": 1280, "height": 720}
KEYS = {"goto", "click", "fill", "wait", "wait_for", "scroll"}


def validate(steps):
    if not isinstance(steps, list) or not steps:
        raise ValueError("steps must be a non-empty list")
    for i, s in enumerate(steps, 1):
        if not isinstance(s, dict) or len(KEYS & s.keys()) != 1:
            raise ValueError(f"step {i}: needs exactly one of {sorted(KEYS)}")
        if "goto" in s and not str(s["goto"]).startswith(("http://", "https://")):
            raise ValueError(f"step {i}: goto needs an http(s) URL")
        if "fill" in s and not isinstance(s.get("text"), str):
            raise ValueError(f"step {i}: fill needs 'text'")


def run(page, s):
    if "goto" in s:
        page.goto(s["goto"], wait_until="load")  # big background downloads never reach networkidle
    elif "click" in s:
        page.click(s["click"])
    elif "fill" in s:
        page.fill(s["fill"], s["text"])
    elif "wait" in s:
        page.wait_for_timeout(int(s["wait"]))
    elif "wait_for" in s:
        page.wait_for_selector(s["wait_for"], timeout=int(s.get("timeout", 60000)))
    elif "scroll" in s:
        for _ in range(10):  # ten small wheel steps read as a smooth scroll on video
            page.mouse.wheel(0, int(s["scroll"]) / 10)
            page.wait_for_timeout(60)


def record(steps, out):
    validate(steps)
    vids = tempfile.mkdtemp(prefix="repo-video-rec-")
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE, headless=True, viewport=SIZE, record_video_dir=vids, record_video_size=SIZE)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        t0, start = time.monotonic(), None
        try:
            for s in steps:
                run(page, s)
                if start is None and "goto" in s:
                    start = time.monotonic() - t0
            page.wait_for_timeout(500)
        finally:
            video = page.video
            ctx.close()  # the video file is only complete after close
        shutil.move(video.path(), out)
    shutil.rmtree(vids, ignore_errors=True)
    print(f"{os.path.abspath(out)} start={start or 0:.1f}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    try:
        with open(sys.argv[1]) as f:
            steps = json.load(f)
        validate(steps)
    except (OSError, ValueError) as e:
        sys.exit(f"bad steps: {e}")
    record(steps, sys.argv[2])
