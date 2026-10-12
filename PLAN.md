# repo-video plan

Build the skill from `BUILD-GUIDE.md`, plus a project overview mode. Name: `/repo-video`.

## Modes (auto-detected from the argument)

| Argument | Mode |
|---|---|
| `github.com/<o>/<r>/pull/<n>` | PR walkthrough (guide steps 1–5) |
| `gitlab.com/.../-/merge_requests/<n>` | MR walkthrough (`glab`) |
| `github.com/<o>/<r>` (no `/pull/`) | Overview: `gh repo clone <o>/<r> <tmp> -- --depth 1` |
| local folder path | Overview of that folder |
| nothing | Overview of the current folder |

## Overview mode

Claude reads: README, manifest (package.json, pyproject.toml, go.mod, Cargo.toml...), `git ls-files` tree, entry points, the 3–5 most important modules, `git log --oneline -20`. Same spec.json and renderer as PR mode.
Slides (6–9, 210 words or fewer): what it is and who it's for → how to run it → structure (a trimmed tree as a `text` slide) → 3–5 key files with real excerpts → how a request/data flows → where to start contributing.
Attach step: none. The video is saved next to the spec, and Claude opens it.

## Files

`SKILL.md`, `setup.sh`, `make_video.py` in this repo, symlinked to `~/.claude/skills/repo-video`.

## Additions beyond the guide

- Spec validation (slides list, non-empty narration) with a clear error, exit 1.
- Unknown `lang` falls back to plain text instead of crashing.
- Over-wide headings are shortened with an ellipsis.

## Acceptance

1. `make_video.py --selftest` passes (mp4 exists, 120 s or less).
2. Spec over 120 s → exit 2 with `too long: <N>s, cut narration`.
3. `/repo-video <a PR URL>` makes a video and asks before attaching.
4. `/repo-video ~/claude-work/projects/<some repo>` makes an overview video.
5. `/repo-video https://github.com/<o>/<r>` clones and makes an overview video.
