"""Makon-specific, dependency-light helpers for a review-first video workspace."""
from __future__ import annotations

import io
import json
import math
import re
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
from uuid import uuid4

MAX_UPLOAD_BYTES = 200 * 1024 * 1024
MAX_SUBTITLE_BYTES = 1024 * 1024
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}
VISUAL_EXTENSIONS = {".mp4", ".mov", ".mkv", ".jpg", ".jpeg", ".png"}
LANGUAGES = {"uz-UZ": "Uzbek (Latin)", "en-US": "English", "ru-RU": "Russian"}


@dataclass(frozen=True)
class Preset:
    title: str
    description: str
    language: str
    topic: str
    direction: str
    duration: int = 20
    upload_audio: bool = False
    local_visuals: bool = False


PRESETS = {
    "music_ad": Preset(
        "Makon Music · Gift ad",
        "A strong opening, a personal gift, and a direct-message call to action.",
        "uz-UZ", "A personal anniversary gift for your wife",
        "Write an emotional but believable ad for a personalized song. Open with a specific gift problem, not a company introduction. End by asking viewers to message the team. Do not imply a famous artist performs the song.",
    ),
    "song_reel": Preset(
        "Makon Music · Song showcase",
        "Upload a finished Suno song, select an excerpt, and use your own visuals.",
        "uz-UZ", "A personalized song for someone special",
        "Describe the supplied song without inventing lyrics or claiming a real customer reaction. The uploaded song remains the soundtrack; do not replace it with speech.",
        30, True, True,
    ),
    "visual": Preset(
        "Makon Visual · Design reveal",
        "Show your actual before-and-after images in the order you upload them.",
        "uz-UZ", "A room redesign, before and after",
        "Write a short interior-design reveal. Describe only changes stated in the brief. Do not present stock footage or AI concept images as a completed client project. Ask viewers to message Makon Visual about their room.",
        20, False, True,
    ),
    "story": Preset(
        "General · Story / explainer",
        "Keep the original topic-to-video workflow for English-language content.",
        "en-US", "An everyday idea explained simply",
        "Write an engaging short explainer. Make the opening specific. Do not invent statistics, studies, quotes or news. Do not add Makon branding or a sales pitch unless the brief requests it.",
        30,
    ),
}


def build_script_direction(preset_id: str, language: str, seconds: int,
                           basic_price: int = 50000, pro_price: int = 100000,
                           room_price: int = 400000) -> str:
    if preset_id not in PRESETS or language not in LANGUAGES:
        raise ValueError("Select a supported preset and content language.")
    if not 5 <= seconds <= 90:
        raise ValueError("Target duration must be between 5 and 90 seconds.")
    if any(not isinstance(p, int) or p < 0 for p in (basic_price, pro_price, room_price)):
        raise ValueError("Prices must be non-negative whole UZS amounts.")
    preset = PRESETS[preset_id]
    budget = max(8, round(seconds * 2.1))
    brand = ""
    if preset_id == "music_ad":
        brand = (f"User-configured offer: Makon Music, Uzbekistan. Basic {basic_price:,} UZS; "
                 f"Pro {pro_price:,} UZS. Mention a price only if the brief asks for it. "
                 "Never invent delivery deadlines, discounts or guarantees.")
    elif preset_id == "visual":
        brand = (f"User-configured offer: Makon Visual, {room_price:,} UZS per room. "
                 "Mention this price only if the brief requests it.")
    return (f"{preset.direction}\n{brand}\nWrite only the spoken script in {LANGUAGES[language]}, "
            f"approximately {budget} words for a {seconds}-second target. "
            "This is a writing target, not a guaranteed audio duration. "
            "Use natural spoken language. No stage directions, headings, markdown, "
            "fake testimonials, invented facts or fabricated social proof. "
            "For Uzbek use Latin script, natural Uzbek phrasing, and so'm for prices.").strip()


def estimate_speech_seconds(text: str) -> int:
    """A writing aid, deliberately not presented as audio timing."""
    return round(len(re.findall(r"\b[\w’ʻʼ']+\b", text, re.UNICODE)) / 2.1)


def persist_upload(directory: Path, filename: str, content: bytes,
                   allowed: set[str]) -> Path:
    extension = Path(filename.replace("\\", "/")).suffix.lower()
    if extension not in allowed:
        raise ValueError("Unsupported file type. Use one of: " + ", ".join(sorted(allowed)))
    if not content or len(content) > MAX_UPLOAD_BYTES:
        raise ValueError("Each upload must be non-empty and no larger than 200 MB.")
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"upload-{uuid4().hex}{extension}"
    destination.write_bytes(content)
    return destination


_TIME = r"(?P<{name}>\d{{2}}:[0-5]\d:[0-5]\d,\d{{3}})"
_TIMELINE = re.compile(_TIME.format(name="start") + r"\s+-->\s+" + _TIME.format(name="end"))


def _seconds(stamp: str) -> float:
    h, m, tail = stamp.split(":")
    s, ms = tail.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def validate_srt(text: str, max_duration: float | None = None) -> str:
    """Validate actual timestamps. Never generate guessed lyric timing."""
    if len(text.encode("utf-8")) > MAX_SUBTITLE_BYTES:
        raise ValueError("Subtitle file must be smaller than 1 MB.")
    text = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise ValueError("The subtitle file is empty.")
    if max_duration is not None and (not math.isfinite(max_duration) or max_duration <= 0):
        raise ValueError("Audio duration must be a positive, finite number.")
    previous_end = 0.0
    normalized = []
    for i, block in enumerate(re.split(r"\n\s*\n", text), 1):
        lines = block.splitlines()
        if len(lines) < 3 or not lines[0].strip().isdigit():
            raise ValueError(f"Caption {i}: expected a number, timestamps and text.")
        match = _TIMELINE.fullmatch(lines[1].strip())
        if not match:
            raise ValueError(f"Caption {i}: use HH:MM:SS,mmm --> HH:MM:SS,mmm.")
        start, end = _seconds(match['start']), _seconds(match['end'])
        if end <= start or start < previous_end - 0.001:
            raise ValueError(f"Caption {i}: timestamps must be ordered and must not overlap.")
        if max_duration is not None and end > max_duration + 0.1:
            raise ValueError(f"Caption {i}: ends after the selected audio excerpt. Time captions from 00:00 of the excerpt.")
        words = "\n".join(lines[2:]).strip()
        if not words or len(words) > 1000 or "\x00" in words:
            raise ValueError(f"Caption {i}: text must contain 1–1,000 characters, without NUL bytes.")
        normalized.append(f"{i}\n{match['start']} --> {match['end']}\n{words}")
        previous_end = end
    return "\n\n".join(normalized) + "\n"


def copy_validated_subtitles(task_directory: Path, requested_file: str,
                             audio_duration: float) -> str:
    root = task_directory.resolve()
    source = Path(requested_file)
    if not source.is_absolute():
        source = root / source
    source = source.resolve()
    if not source.is_relative_to(root) or source.suffix.lower() != ".srt":
        raise ValueError("Manual subtitles must be an SRT file inside this task's directory.")
    if not source.is_file() or source.stat().st_size > MAX_SUBTITLE_BYTES:
        raise ValueError("Manual subtitle file is missing or larger than 1 MB.")
    text = validate_srt(source.read_text(encoding="utf-8-sig"), audio_duration)
    destination = root / "subtitle.srt"
    if destination.is_symlink():
        raise ValueError("The subtitle output cannot be a symbolic link.")
    temporary = root / f".subtitle-{uuid4().hex}.tmp"
    try:
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return str(destination)


def trim_audio(source: Path, destination: Path, start: float, duration: float,
               source_duration: float, ffmpeg: str) -> Path:
    for value in (start, duration, source_duration):
        if not math.isfinite(value):
            raise ValueError("Audio times must be finite numbers.")
    if start < 0 or duration <= 0 or start + duration > source_duration + 0.05:
        raise ValueError("The excerpt must fit inside the uploaded audio. Reduce its start time or length.")
    if source.resolve() == destination.resolve():
        raise ValueError("Keep the source audio separate from the excerpt.")
    command = [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
               "-ss", str(start), "-i", str(source.resolve()), "-t", str(duration),
               "-map", "0:a:0", "-vn", "-c:a", "libmp3lame", "-b:a", "192k",
               str(destination.resolve())]
    result = subprocess.run(command, capture_output=True, timeout=120, check=False)
    if result.returncode or not destination.is_file() or not destination.stat().st_size:
        destination.unlink(missing_ok=True)
        raise ValueError("FFmpeg could not read or trim this audio. Try a valid MP3 or WAV file.")
    return destination


def redact_error(message: object, settings: Mapping) -> str:
    text = str(message)
    for key, value in settings.items():
        if any(marker in key.lower() for marker in ("key", "token", "secret", "password")):
            for secret in value if isinstance(value, (list, tuple)) else [value]:
                if isinstance(secret, str) and secret:
                    text = text.replace(secret, "[redacted]")
    text = re.sub(r"(?i)([?&](?:key|api_key|token)=)[^\s&#]+", r"\1[redacted]", text)
    return text[:4000]


def export_pack(task_directory: Path, final_video: Path) -> bytes:
    """Allowlist files; never package config, logs, fonts, keys or other tasks."""
    root = task_directory.resolve()
    video = final_video.resolve()
    if not video.is_relative_to(root) or video.suffix.lower() != ".mp4" or not video.is_file():
        raise ValueError("Select a completed MP4 from this task.")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(video, "video.mp4")
        for filename in ("subtitle.srt", "script.txt", "caption.txt"):
            item = root / filename
            if item.is_file() and item.resolve().is_relative_to(root):
                archive.write(item, filename)
        archive.writestr("README.txt", "Created with Makon Video Studio / MoneyPrinterTurbo.\nReview the video and captions before posting. Confirm rights to music, footage and any depicted people.\n")
    return buffer.getvalue()


def write_project(task_directory: Path, *, title: str, preset: str, language: str,
                  script: str, caption: str) -> None:
    task_directory.mkdir(parents=True, exist_ok=True)
    task_directory.joinpath("script.txt").write_text(script, encoding="utf-8")
    task_directory.joinpath("caption.txt").write_text(caption, encoding="utf-8")
    payload = {"title": title, "preset": preset, "language": language, "schema": 1}
    task_directory.joinpath("makon.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
