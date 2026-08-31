"""Audio file handling: probing, playback transcoding, video audio extraction.

Uploads keep their original file (transcribed losslessly) and get a small
seekable MP3 alongside for the browser player — MediaRecorder's raw WebM has no
duration header, so seeking in it is broken.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

# Extensions the browser can already play and seek reliably: no transcode needed.
PLAYABLE = {".mp3", ".m4a", ".aac", ".wav", ".ogg", ".oga", ".flac"}

_CREATE_NO_WINDOW = 0x08000000  # keep ffmpeg console windows from flashing on Windows


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        creationflags=_CREATE_NO_WINDOW,
    )


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def probe_duration(path: Path) -> float | None:
    """Length in seconds via ffprobe, or None if it can't be determined."""
    if shutil.which("ffprobe") is None:
        return None
    proc = _run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json",
            str(path),
        ]
    )
    if proc.returncode != 0:
        return None
    try:
        return float(json.loads(proc.stdout)["format"]["duration"])
    except (KeyError, ValueError, json.JSONDecodeError):
        return None


def make_playback_copy(source: Path, dest_dir: Path) -> Path | None:
    """Mono 22 kHz MP3 for the audio player. Returns None if ffmpeg is missing
    or the source is already a seekable playable format."""
    if source.suffix.lower() in PLAYABLE or not ffmpeg_available():
        return None

    dest = dest_dir / "playback.mp3"
    proc = _run(
        [
            "ffmpeg", "-y", "-i", str(source),
            "-vn",                      # drop video: screen recordings become audio
            "-ac", "1", "-ar", "22050", "-b:a", "64k",
            str(dest),
        ]
    )
    if proc.returncode != 0 or not dest.exists():
        return None
    return dest
