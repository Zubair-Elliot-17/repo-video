#!/usr/bin/env bash
# One-time install: ffmpeg, espeak-ng, Python 3.12 venv with Kokoro, then a voice test.
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
command -v brew >/dev/null || { echo "Install Homebrew first: https://brew.sh"; exit 1; }
brew install ffmpeg espeak-ng python@3.12
[ -x "$DIR/.venv/bin/python" ] || "$(brew --prefix python@3.12)/bin/python3.12" -m venv "$DIR/.venv"
"$DIR/.venv/bin/pip" install -q kokoro soundfile pygments pillow numpy playwright
"$DIR/.venv/bin/playwright" install chromium
"$DIR/.venv/bin/python" - <<'PY'
from kokoro import KPipeline
import numpy as np, soundfile as sf
pipe = KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M")
audio = np.concatenate([np.asarray(a) for _, _, a in pipe("Setup check. The voice works.", voice="af_heart")])
sf.write("/tmp/repo-video-test.wav", audio, 24000)
PY
echo "Setup done. Play it: afplay /tmp/repo-video-test.wav"
