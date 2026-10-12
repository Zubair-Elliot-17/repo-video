# PR walkthrough video skill: build guide

A Claude Code skill that turns a GitHub PR (or GitLab MR) into a narrated walkthrough video of 2 minutes or less, rendered on your Mac. Written 2026-10-12, for your personal Mac.

> **Clean build.** This guide is based only on the general idea (a narrated walkthrough video of a PR) and the public docs of open-source tools. It contains no code from other PR-video tools, such as tldraw's `pr-walkthrough`. Keep it that way.

## Start here

Build in this order. Each step ends with something you can see or hear.

| # | Step | Done when | Time |
|---|------|-----------|------|
| 1 | Setup and voice test | `afplay /tmp/pr-video-test.wav` speaks a sentence | 20 min, mostly downloads |
| 2 | One frame | `open frame.png` shows a diff slide with a caption | 30 min |
| 3 | Full video from a hand-written spec | `open out.mp4` plays 2 slides with voice and captions | 45 min |
| 4 | SKILL.md and a real PR | `/pr-video <your PR URL>` produces a video | 30 min |
| 5 | Attach step | The video plays at the top of the PR description | 15 min |

About 2.5 hours in total.

## What it does

- Input: a GitHub PR URL. A GitLab MR URL also works (see step 5).
- Claude reads the full diff and every commit message, then writes a script: 6 to 9 slides of real code and diff, with 210 words of narration or fewer.
- The Mac renders it: a Kokoro voice, slides with captions, and a 1280×720 MP4 of 2 minutes or less.
- Claude opens the video for you and attaches it to the PR only after you say yes.

Privacy: the rendering happens on your Mac. Claude reads the diff the same way it does for any Claude Code task.

## How it works

```
PR URL
  │  gh pr view / gh pr diff
  ▼
Claude writes spec.json  (slides + narration)
  │  make_video.py
  ├─ Kokoro: each sentence → one audio clip (24 kHz)
  ├─ Pillow + Pygments: slide + that sentence as a caption → one PNG frame
  └─ ffmpeg: frames (each shown for the length of its clip) + audio → out.mp4
  ▼
open out.mp4 → you approve → attach to the PR
```

The captions are drawn onto the frames, one sentence at a time. Each frame stays on screen for as long as its sentence's audio lasts, so captions match the voice without Whisper or a subtitle file.

## Files

```
~/.claude/skills/pr-video/
├── SKILL.md        # the instructions Claude follows
├── setup.sh        # one-time install
└── make_video.py   # spec.json → out.mp4
```

## Step 1: Setup and voice test

Prerequisites: Homebrew, Claude Code signed in with your personal account, and `gh` signed in (`brew install gh && gh auth login`).

`setup.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
command -v brew >/dev/null || { echo "Install Homebrew first: https://brew.sh"; exit 1; }
brew install ffmpeg espeak-ng python@3.12
[ -x "$DIR/.venv/bin/python" ] || "$(brew --prefix python@3.12)/bin/python3.12" -m venv "$DIR/.venv"
"$DIR/.venv/bin/pip" install -q kokoro soundfile pygments pillow numpy
"$DIR/.venv/bin/python" - <<'EOF'
from kokoro import KPipeline
import numpy as np, soundfile as sf
pipe = KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M")
audio = np.concatenate([np.asarray(a) for _, _, a in pipe("Setup check. The voice works.", voice="af_heart")])
sf.write("/tmp/pr-video-test.wav", audio, 24000)
EOF
echo "Setup done. Play it: afplay /tmp/pr-video-test.wav"
```

- **Python 3.12:** Kokoro's dependencies can take a while to support a new Python release, so 3.12 is the safe choice. Kokoro's PyPI page lists the versions it supports now.
- **First run:** downloads about 350 MB of model files. After that it works offline. Set `HF_HUB_OFFLINE=1` to skip the update check.
- **Voices:** `af_heart` (US female), `am_michael` (US male), `bm_george` (UK male, needs `lang_code="b"`).

## Step 2: One frame

Each frame has a heading at the top, the code or diff in the middle, and a caption bar at the bottom. Pygments draws the highlighted code as an image, and Pillow places it on a fixed 1280×720 canvas.

```python
import io, textwrap
from PIL import Image, ImageDraw, ImageFont
from pygments import highlight
from pygments.lexers import DiffLexer, get_lexer_by_name
from pygments.formatters import ImageFormatter
from pygments.styles import get_style_by_name

W, H = 1280, 720
STYLE = "github-dark"
BG = get_style_by_name(STYLE).background_color
SANS = "/System/Library/Fonts/Helvetica.ttc"

def code_png(text, lang):
    lexer = DiffLexer() if lang == "diff" else get_lexer_by_name(lang)
    png = highlight(text, lexer, ImageFormatter(
        style=STYLE, font_name="Menlo", font_size=24, line_numbers=False, image_pad=20))
    return Image.open(io.BytesIO(png))

def frame(heading, caption, body=None):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.text((40, 30), heading, font=ImageFont.truetype(SANS, 34), fill="white")
    if body is not None:
        body.thumbnail((W - 80, H - 230))  # shrinks to fit, never enlarges
        img.paste(body, (40, 95))
    d.rectangle([0, H - 110, W, H], fill="black")
    cap = ImageFont.truetype(SANS, 28)
    for i, line in enumerate(textwrap.wrap(caption, 75)[:2]):
        d.text((40, H - 95 + i * 40), line, font=cap, fill="white")
    return img
```

**Check:** save a hunk from any diff as `sample.diff`, then run:

```python
frame("src/upload.py", "Failed uploads now retry twice.", code_png(open("sample.diff").read(), "diff")).save("frame.png")
```

Then run `open frame.png`.

## Step 3: Full video from a hand-written spec

### spec.json format

```json
{
  "slides": [
    {"heading": "PR #42: Retry failed uploads",
     "narration": "This PR makes uploads survive flaky networks. Failed uploads now retry twice before giving up."},
    {"heading": "src/upload.py",
     "lang": "diff",
     "code": "@@ -10,2 +10,4 @@ def upload(path):\n-    return client.put(path)\n+    for attempt in range(3):\n+        ...",
     "narration": "The upload call now runs in a loop. Each failure waits a little longer before the next try."}
  ]
}
```

`code` and `lang` are optional. Title and summary slides don't need them.

### Timing and assembly

Split each slide's narration into sentences. Speak each sentence, and make one frame per sentence. Each frame lasts as long as its audio plus a short pause.

```python
import re, subprocess, numpy as np, soundfile as sf
from kokoro import KPipeline

SR = 24000
GAP = np.zeros(int(0.3 * SR), dtype=np.float32)  # pause after each sentence

def speak(pipe, text, voice="af_heart"):
    return np.concatenate([np.asarray(a) for _, _, a in pipe(text, voice=voice)])

def build(spec, workdir):
    pipe = KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M")
    audio, lines, n = [], [], 0
    for slide in spec["slides"]:
        body = code_png(slide["code"], slide["lang"]) if slide.get("code") else None
        for sentence in re.split(r"(?<=[.!?])\s+", slide["narration"].strip()):
            clip = np.concatenate([speak(pipe, sentence), GAP])
            path = f"{workdir}/f{n:03}.png"
            frame(slide["heading"], sentence, body.copy() if body else None).save(path)
            lines += [f"file '{path}'", f"duration {len(clip) / SR:.3f}"]
            audio.append(clip)
            n += 1
    lines.append(lines[-2])  # ffmpeg concat quirk: list the last file again
    open(f"{workdir}/frames.txt", "w").write("\n".join(lines) + "\n")
    sf.write(f"{workdir}/narration.wav", np.concatenate(audio), SR)
    return sum(len(c) for c in audio) / SR  # total seconds
```

Check the total length before rendering. If it's over 120 seconds, print `too long: <N>s, cut narration` and exit with code 2, so Claude knows to shorten the script. Otherwise:

```bash
ffmpeg -y -f concat -safe 0 -i frames.txt -i narration.wav \
  -vf "fps=30,format=yuv420p" -c:v libx264 -tune stillimage -crf 26 \
  -c:a aac -b:a 128k -shortest -movflags +faststart out.mp4
```

Run it from Python with `subprocess.run([...], check=True)`, and do the work in a `tempfile.mkdtemp()` folder. The command line is `make_video.py spec.json out.mp4`.

**One check to keep:** add `make_video.py --selftest`. It renders a built-in 2-slide spec and asserts that `out.mp4` exists and lasts 120 seconds or less:

```bash
ffprobe -v error -show_entries format=duration -of csv=p=0 out.mp4
```

## Step 4: SKILL.md

A starting draft:

````markdown
---
name: pr-video
description: Make a narrated walkthrough video (2 minutes or less) of a GitHub PR or GitLab MR from its URL, rendered on this Mac with a Kokoro voice, code/diff slides and captions. Shows it to the user and attaches it to the PR only after approval. Use for "/pr-video <url>", "make a PR video" or "walkthrough video for this PR".
---

# PR video

1. **Setup.** If `~/.claude/skills/pr-video/.venv` or `ffmpeg` is missing, run `~/.claude/skills/pr-video/setup.sh`. Tell the user the first run downloads about 350 MB.
2. **Read the PR.** Run `gh pr view <url> --json number,title,body,commits,files` and `gh pr diff <url>`. Read the whole diff and every commit message before writing anything.
3. **Write the script** to `$TMPDIR/pr-video/<number>/spec.json`:
   ```json
   {"slides": [{"heading": "...", "narration": "...", "lang": "diff", "code": "..."}]}
   ```
   - 6 to 9 slides, 210 words of narration or fewer in total, every sentence under 20 words.
   - Slide 1: what changed and why. Last slide: what a reviewer should check.
   - Code slides: copy hunks word for word from the diff. 18 lines or fewer, 90 characters or fewer per line. Skip lockfiles and generated files.
   - Explain intent and risk. Don't read code aloud.
4. **Render:** `~/.claude/skills/pr-video/.venv/bin/python ~/.claude/skills/pr-video/make_video.py spec.json out.mp4`. Exit code 2 means the video is too long: cut narration and run it again.
5. **Show:** run `open out.mp4`, then ask "Attach this to the PR?" Do nothing else without a yes.
6. **Attach** (only after a yes):
   - GitHub: run `open <url>` and `open -R out.mp4`. Tell the user to drag the file to the top of the PR description, because GitHub has no API for attachments.
   - GitLab: upload the file and put the returned markdown at the top of the description (see the build guide, step 5).
````

**Check:** run `/pr-video <URL of one of your PRs>` in Claude Code.

## Step 5: Attach to the PR

**GitHub:** GitHub has no public API for adding attachments to a description. The skill opens the PR and shows the file in Finder. You drag it to the top of the description, and GitHub hosts it as an inline player. Free plans allow videos up to 10 MB. A 2-minute video of still slides at `-crf 26` is usually a few MB.

**GitLab:** upload the file, then put the returned markdown at the top of the description. `GITLAB_TOKEN` is a personal access token with `api` scope. `PROJECT_ID` is on the project's main page.

```bash
MD=$(curl -s -H "PRIVATE-TOKEN: $GITLAB_TOKEN" -F "file=@out.mp4" \
  "https://gitlab.com/api/v4/projects/$PROJECT_ID/uploads" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["markdown"])')
OLD=$(glab mr view "$MR" -R "$REPO" -F json | python3 -c 'import json,sys; print(json.load(sys.stdin)["description"] or "")')
glab mr update "$MR" -R "$REPO" --description "$MD"$'\n\n'"$OLD"
```

## Left out on purpose

- **Whisper and word-level subtitles:** the audio length of each sentence already gives caption timing. Add Whisper only if you want each word highlighted as it's spoken.
- **Language-aware highlighting inside diffs:** the diff lexer colours only the + and − lines. Add it if diffs are hard to read.
- **Music, transitions and animation.**

## Licences

All of these are fine for personal use: Kokoro-82M (Apache-2.0), Pygments (BSD-2-Clause), Pillow (MIT-CMU), ffmpeg (LGPL/GPL), espeak-ng (GPL-3.0), and for live-site clips Playwright (Apache-2.0). numpy and soundfile are BSD-3-Clause.
