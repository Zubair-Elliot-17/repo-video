#!/usr/bin/env python3
"""spec.json -> narrated 1280x720 MP4 (1080x1920 TikTok style with "gameplay"). Usage: make_video.py spec.json out.mp4 | --selftest"""
import glob, hashlib, urllib.request
import io, json, os, re, subprocess, sys, tempfile, textwrap
import numpy as np, soundfile as sf
from PIL import Image, ImageColor, ImageDraw, ImageFont
from pygments import highlight
from pygments.lexers import DiffLexer, TextLexer, get_lexer_by_name
from pygments.formatters import ImageFormatter
from pygments.styles import get_style_by_name
from pygments.util import ClassNotFound

W, H = 1280, 720
STYLE = "github-dark"
BG = get_style_by_name(STYLE).background_color
SANS = "/System/Library/Fonts/Helvetica.ttc"
IMPACT = "/System/Library/Fonts/Supplemental/Impact.ttf"
SR = 24000
GAP = np.zeros(int(0.3 * SR), dtype=np.float32)  # pause after each sentence
MAX_SECONDS = 120
CLIP_FPS = 15  # frames sampled from screen-recording clips
VOICE = os.environ.get("REPO_VIDEO_VOICE", "af_heart")
MAX_SENTENCE = 140  # longer captions would be cut off at two lines
CLIP_TYPES = (".webm", ".mp4", ".mov")
TALL_W, TALL_H = 1080, 1920  # TikTok layout: full-screen gameplay, code card on top, one big word at a time
# Free-licensed (CC BY 3.0) clips with the credit burned in; downloaded once, then cached.
GAMEPLAY_URL = "https://github.com/Zubair-Elliot-17/repo-video/releases/download/gameplay-v2/"
GAMEPLAY = {"minecraft": "fa88673c9590370e1085d967e681b4f61d8fa9eb7d6ef3c82c12456933d9e55d",
            "kart": "deafcce6333eb1ac9f0bed3be3b15b4faca0eb4fd1be128f1bb419e9ac3f7aa9"}
GAMEPLAY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gameplay")
# Common credential shapes; a hit stops the render so a key never ends up in a video.
SECRET = re.compile(r"AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_\w{30,}|glpat-[\w-]{20,}"
                    r"|xox[abpr]-[\w-]{10,}|sk-[A-Za-z0-9_-]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY")


def code_png(text, lang):
    if lang == "diff":
        lexer = DiffLexer()
    else:
        try:
            lexer = get_lexer_by_name(lang or "text")
        except ClassNotFound:
            lexer = TextLexer()
    png = highlight(text, lexer, ImageFormatter(
        style=STYLE, font_name="Menlo", font_size=24, line_numbers=False, image_pad=20, line_pad=8))  # room for underscores under diff highlights
    return Image.open(io.BytesIO(png))


def fit(d, text, font, width):
    if d.textlength(text, font=font) <= width:
        return text
    left = "/" in text.split(" ")[0]  # file paths lose their start, so the file name stays
    while text and d.textlength(text + "…", font=font) > width:
        text = text[1:] if left else text[:-1]
    return "…" + text if left else text + "…"


def frame(heading, caption, body=None, center=False):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    head = ImageFont.truetype(SANS, 34)
    d.text((40, 30), fit(d, heading, head, W - 80), font=head, fill="white")
    if body is not None:
        body.thumbnail((W - 80, H - 230))  # shrinks to fit, never enlarges
        img.paste(body, ((W - body.width) // 2 if center else 40, 95))
    d.rectangle([0, H - 110, W, H], fill="black")
    cap = ImageFont.truetype(SANS, 28)
    for i, line in enumerate(textwrap.wrap(caption, 75)[:2]):
        d.text((40, H - 95 + i * 40), line, font=cap, fill="white")
    return img


def tall_frame(heading, body, word):
    img = Image.new("RGBA", (TALL_W, TALL_H), (0, 0, 0, 0))  # transparent, laid over the gameplay
    d = ImageDraw.Draw(img)
    head = ImageFont.truetype(SANS, 40)
    if body is not None:
        body.thumbnail((TALL_W - 120, 700))
    top, card_h = 150, 90 + (body.height + 20 if body is not None else 0)
    d.rounded_rectangle([40, top, TALL_W - 40, top + card_h], 28, fill=ImageColor.getrgb(BG) + (235,))
    d.text((70, top + 25), fit(d, heading, head, TALL_W - 140), font=head, fill="white")
    if body is not None:
        img.paste(body, ((TALL_W - body.width) // 2, top + 90))
    if word:
        size = 170
        while size > 60 and d.textlength(word, font=ImageFont.truetype(IMPACT, size)) > TALL_W - 100:
            size -= 10
        d.text((TALL_W // 2, 1200), word.upper(), font=ImageFont.truetype(IMPACT, size), anchor="mm",
               fill=(255, 230, 0), stroke_width=12, stroke_fill="black")
    return img


def tall_frames(heading, body, shots, pos, words, secs, workdir, n, lines):
    # A new frame whenever the spoken word (or the clip frame) changes, timed by Kokoro's word timestamps.
    starts = [0.0] + [t for _, t in words[1:]]
    cuts = set(starts) | ({j / CLIP_FPS for j in range(round(secs * CLIP_FPS))} if shots else set())
    cuts = sorted(t for t in cuts if t < secs)
    for i, t in enumerate(cuts):
        word = words[max(j for j, s in enumerate(starts) if s <= t)][0] if words else ""
        card = Image.open(shots[min(pos + int(t * CLIP_FPS), len(shots) - 1)]) if shots else (body.copy() if body else None)
        path = f"{workdir}/f{n:05}.png"
        tall_frame(heading, card, word).save(path)
        lines += [f"file '{path}'", f"duration {(cuts[i + 1] if i + 1 < len(cuts) else secs) - t:.4f}"]
        n += 1
    return n


def validate(spec):
    slides = spec.get("slides") if isinstance(spec, dict) else None
    if not isinstance(slides, list) or not slides:
        raise ValueError("spec needs a non-empty 'slides' list")
    if "gameplay" in spec:
        game = str(spec["gameplay"])
        if game not in GAMEPLAY and (not game.lower().endswith(CLIP_TYPES) or not os.path.isfile(game)):
            raise ValueError(f"gameplay must be {' or '.join(GAMEPLAY)}, or an existing {'/'.join(CLIP_TYPES)} file")
    for i, s in enumerate(slides, 1):
        if not isinstance(s, dict) or not str(s.get("heading", "")).strip():
            raise ValueError(f"slide {i}: missing 'heading'")
        if not str(s.get("narration", "")).strip():
            raise ValueError(f"slide {i}: missing 'narration'")
        if "code" in s and not isinstance(s["code"], str):
            raise ValueError(f"slide {i}: 'code' must be a string")
        if "video" in s:
            video = str(s["video"])
            if not video.lower().endswith(CLIP_TYPES) or not os.path.isfile(video):
                raise ValueError(f"slide {i}: video must be an existing {'/'.join(CLIP_TYPES)} file")
            if float(s.get("start", 0)) >= duration(video):
                raise ValueError(f"slide {i}: start is past the end of the clip")
        for sentence in sentences(s["narration"]):
            if len(sentence) > MAX_SENTENCE:
                raise ValueError(f"slide {i}: sentence over {MAX_SENTENCE} characters, split it: {sentence[:40]}…")
        hit = SECRET.search(f"{s['heading']} {s.get('code', '')} {s['narration']}")
        if hit:
            raise ValueError(f"slide {i}: looks like a secret ({hit.group()[:8]}…), remove or mask it")


def sentences(text):
    return [t for t in re.split(r"(?<=[.!?])\s+", text.strip()) if t.strip()]


def speak(pipe, text):
    """Audio plus (word, start seconds) for each spoken word."""
    audio, words, t = [], [], 0.0
    for r in pipe(text, voice=VOICE):
        a = np.asarray(r.audio)
        words += [(w.text, t + w.start_ts) for w in (r.tokens or [])
                  if w.start_ts is not None and any(c.isalnum() for c in w.text)]
        audio.append(a)
        t += len(a) / SR
    return np.concatenate(audio), words


def clip_frames(video, start, outdir):
    os.makedirs(outdir)
    subprocess.run(["ffmpeg", "-v", "error", "-protocol_whitelist", "file", "-ss", str(start), "-i", video,
                    "-vf", f"fps={CLIP_FPS}", f"{outdir}/%05d.png"], check=True)
    frames = sorted(glob.glob(f"{outdir}/*.png"))
    if not frames:
        raise ValueError(f"no frames in {video} after {start}s")
    return frames


def build(spec, workdir, tall=False):
    from kokoro import KPipeline  # slow import, only needed here
    pipe = KPipeline(lang_code="b" if VOICE.startswith("b") else "a", repo_id="hexgrad/Kokoro-82M")
    audio, lines, n = [], [], 0
    for k, slide in enumerate(spec["slides"]):
        body = code_png(slide["code"], slide.get("lang")) if slide.get("code") else None
        shots = clip_frames(slide["video"], slide.get("start", 0), f"{workdir}/clip{k}") if slide.get("video") else None
        pos = 0  # next clip frame; the clip keeps playing across the slide's sentences
        for sentence in sentences(slide["narration"]):
            speech, words = speak(pipe, sentence)
            clip = np.concatenate([speech, GAP])
            secs = len(clip) / SR
            if tall:
                n = tall_frames(slide["heading"], body, shots, pos, words, secs, workdir, n, lines)
                pos += round(secs * CLIP_FPS)
            elif shots:
                count = max(1, round(secs * CLIP_FPS))
                for j in range(count):
                    shot = Image.open(shots[min(pos, len(shots) - 1)])  # hold the last frame if the clip ends
                    path = f"{workdir}/f{n:05}.png"
                    frame(slide["heading"], sentence, shot, center=True).save(path)
                    # last frame takes the remainder so audio and video stay in sync
                    dur = secs - (count - 1) / CLIP_FPS if j == count - 1 else 1 / CLIP_FPS
                    lines += [f"file '{path}'", f"duration {dur:.4f}"]
                    pos += 1
                    n += 1
            else:
                path = f"{workdir}/f{n:05}.png"
                frame(slide["heading"], sentence, body.copy() if body else None).save(path)
                lines += [f"file '{path}'", f"duration {secs:.3f}"]
                n += 1
            audio.append(clip)
    lines.append(lines[-2])  # ffmpeg concat quirk: list the last file again
    with open(f"{workdir}/frames.txt", "w") as f:
        f.write("\n".join(lines) + "\n")
    sf.write(f"{workdir}/narration.wav", np.concatenate(audio), SR)
    return sum(len(c) for c in audio) / SR


def render(spec, out):
    validate(spec)
    out = os.path.abspath(out)
    with tempfile.TemporaryDirectory(prefix="repo-video-") as work:
        seconds = build(spec, work, tall="gameplay" in spec)
        if seconds > MAX_SECONDS:
            print(f"too long: {seconds:.0f}s, cut narration")
            sys.exit(2)
        encode(work, out, spec.get("gameplay"))
    print(f"{out} ({seconds:.0f}s)")
    return out


def gameplay_clip(name):
    path = os.path.join(GAMEPLAY_DIR, f"{name}.mp4")
    if not os.path.isfile(path):
        print(f"downloading {name} gameplay (once)…", file=sys.stderr)
        with urllib.request.urlopen(GAMEPLAY_URL + f"{name}.mp4", timeout=60) as r:
            data = r.read()
        if hashlib.sha256(data).hexdigest() != GAMEPLAY[name]:
            raise RuntimeError(f"{name} gameplay download failed its checksum")
        os.makedirs(GAMEPLAY_DIR, exist_ok=True)
        with open(path + ".part", "wb") as f:
            f.write(data)
        os.replace(path + ".part", path)  # never leave a half-written clip in the cache
    return path


def encode(work, out, gameplay=None):
    video = ["-vf", "fps=30,format=yuv420p", "-tune", "stillimage"]
    if gameplay in GAMEPLAY:
        gameplay = gameplay_clip(gameplay)
    if gameplay:  # looped and muted, full screen; narration stays the only audio
        video = ["-protocol_whitelist", "file", "-stream_loop", "-1", "-i", gameplay, "-filter_complex",
                 f"[2:v]fps=30,scale={TALL_W}:{TALL_H}:force_original_aspect_ratio=increase,"
                 f"crop={TALL_W}:{TALL_H},setsar=1[g];[0:v]fps=30,format=rgba[o];"
                 "[g][o]overlay=shortest=1,format=yuv420p[v]", "-map", "[v]", "-map", "1:a"]
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                    "-i", f"{work}/frames.txt", "-i", f"{work}/narration.wav",
                    *video, "-c:v", "libx264",
                    "-crf", "26", "-c:a", "aac", "-b:a", "128k", "-shortest",
                    "-movflags", "+faststart", out], check=True)


def duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", path], capture_output=True, text=True, check=True)
    return float(r.stdout)


def selftest():
    clip = os.path.join(tempfile.mkdtemp(), "clip.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=30:duration=2",
                    clip], check=True)
    spec = {"slides": [
        {"heading": "Live site", "video": clip, "start": 0.5,
         "narration": "This slide plays a screen recording. It holds the last frame when the clip ends."},
        {"heading": "Self test", "narration": "This is the self test. It has two slides."},
        {"heading": "src/upload.py", "lang": "diff",
         "code": "@@ -10,2 +10,4 @@\n-    return client.put(path)\n+    for attempt in range(3):\n+        ...",
         "narration": "The upload now retries. Done."}]}
    bad = [{"heading": "x"},
           {"heading": "x", "narration": "word " * 40},
           {"heading": "x", "narration": "Key.", "code": "aws = 'AKIAABCDEFGHIJKLMNOP'"},
           {"heading": "x", "narration": "Clip.", "video": clip, "start": 5}]
    for slide in bad:
        try:
            validate({"slides": [slide]})
            raise AssertionError(f"validate accepted {slide}")
        except ValueError:
            pass
    out = render(spec, os.path.join(tempfile.mkdtemp(), "out.mp4"))
    d = duration(out)
    assert os.path.getsize(out) > 0 and 0 < d <= MAX_SECONDS, d
    game = render({**spec, "gameplay": clip}, os.path.join(tempfile.mkdtemp(), "tall.mp4"))
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=width,height",
                        "-of", "csv=p=0", game], capture_output=True, text=True, check=True)
    assert r.stdout.strip() == f"{TALL_W},{TALL_H}", r.stdout
    assert abs(duration(game) - d) < 0.5, (duration(game), d)  # looped gameplay must not stretch the video
    try:
        validate({**spec, "gameplay": "/nope.mp4"})
        raise AssertionError("validate accepted a missing gameplay file")
    except ValueError:
        pass
    validate({**spec, "gameplay": "minecraft"})  # presets need no file until render
    print(f"selftest ok: {d:.1f}s")


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        selftest()
    elif len(sys.argv) == 3:
        try:
            with open(sys.argv[1]) as f:
                spec = json.load(f)
            validate(spec)
        except (OSError, ValueError) as e:  # JSONDecodeError is a ValueError
            sys.exit(f"bad spec: {e}")
        render(spec, sys.argv[2])
    else:
        sys.exit(__doc__)
