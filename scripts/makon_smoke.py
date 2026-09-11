"""Render a real synthetic test MP4 through the production pipeline without API keys."""
from __future__ import annotations
import json
import math
import shutil
import struct
import subprocess
import sys
import wave
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PIL import Image, ImageDraw, ImageFont
from app.config import config
from app.makon import export_pack, trim_audio, write_project
from app.makon_media import visual_upload_directory
from app.models.schema import MaterialInfo, VideoParams
from app.services import state as sm, task, voice
from app.utils import utils


def main():
    destination = ROOT / "validation"
    destination.mkdir(exist_ok=True)
    task_id = str(uuid4())
    directory = Path(utils.task_dir(task_id))
    original = directory / "technical-tone.wav"
    with wave.open(str(original), "wb") as output:
        output.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
        output.writeframes(b"".join(struct.pack("<h", int(1600 * math.sin(2*math.pi*220*t/24000))) for t in range(6*24000)))
    excerpt = trim_audio(original, directory / "excerpt.mp3", 1, 4, voice.get_audio_duration(str(original)), utils.get_ffmpeg_binary())
    font_path = ROOT / "resource/fonts/BeVietnamPro-Bold.ttf"
    font = ImageFont.truetype(str(font_path), 66)
    small = ImageFont.truetype(str(font_path), 33)
    image = Image.new("RGB", (1080, 1920), "#f5f6f2")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((75, 145, 1005, 1410), radius=40, fill="#183d30")
    draw.text((135, 220), "MAKON / VIDEO STUDIO", fill="#adcfab", font=small)
    for i, line in enumerate(["Your music.", "Your story.", "Your final say."]):
        draw.text((135, 570+i*110), line, fill="white", font=font)
    draw.text((120, 1500), "TECHNICAL DEMO / NO AI GENERATED AUDIO", fill="#385947", font=small)
    draw.text((120, 1560), "Local image + trimmed tone + timed captions", fill="#385947", font=small)
    visual = visual_upload_directory(task_id) / "test-card.png"
    image.save(visual)
    srt = directory / "uploaded.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:02,000\nMakon Video Studio\n\n2\n00:00:02,000 --> 00:00:04,000\nReal export. Manual timing.\n", encoding="utf-8")
    params = VideoParams(video_subject="Makon technical validation", video_script="Reference text, not a voiceover.",
        video_source="local", video_materials=[MaterialInfo(provider="local", url=str(visual))],
        custom_audio_file=str(excerpt), custom_subtitle_file=str(srt), voice_name="", bgm_type="", bgm_volume=0,
        subtitle_enabled=True, font_name=font_path.name, font_size=58, stroke_width=2,
        subtitle_position="custom", custom_position=65, video_aspect="9:16", video_concat_mode="sequential",
        video_clip_duration=4, n_threads=2)
    write_project(directory, title="Technical validation — not an ad", preset="song_reel", language="en-US",
                  script=params.video_script, caption="Technical test only: synthetic title card and tone.")
    with config.runtime_config_lock():
        config.app.update({"upload_post_enabled": False, "upload_post_auto_upload": False, "open_task_folder_on_completion": False})
        with patch.object(task.llm, "generate_script", side_effect=AssertionError("Unexpected LLM call")), \
             patch.object(task.llm, "generate_terms", side_effect=AssertionError("Unexpected keyword call")), \
             patch.object(task.voice, "tts", side_effect=AssertionError("Unexpected TTS call")), \
             patch.object(task.subtitle, "create", side_effect=AssertionError("Unexpected Whisper call")):
            result = task.start(task_id, params)
    state = sm.state.get_task(task_id)
    if not result or not result.get("videos"):
        raise AssertionError(f"Production render failed: {state}")
    video = Path(result["videos"][0])
    probe = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(video)]))
    stream = next(s for s in probe["streams"] if s["codec_type"] == "video")
    assert (stream["width"], stream["height"]) == (1080, 1920)
    assert any(s["codec_type"] == "audio" for s in probe["streams"])
    assert 3.8 <= float(probe["format"]["duration"]) <= 4.3
    assert (directory / "subtitle.srt").read_text() == srt.read_text()
    subprocess.run([utils.get_ffmpeg_binary(), "-v", "error", "-i", str(video), "-f", "null", "-"], check=True)
    shutil.copy2(video, destination / "makon-technical-demo.mp4")
    (destination / "makon-posting-pack.zip").write_bytes(export_pack(directory, video))
    (destination / "validation.json").write_text(json.dumps({"render": "passed", "width": stream["width"],
        "height": stream["height"], "duration_seconds": float(probe["format"]["duration"]),
        "has_audio": True, "manual_srt": "passed", "paid_api_calls": 0,
        "source": "Synthetic title card and tone; not AI music", "upstream_commit": "436b0e9cc830ef7639e33388917e389cf30d3307"}, indent=2))
    assert (directory / "makon-export.json").is_file()
    fixtures = destination / "fixtures"
    fixtures.mkdir(exist_ok=True)
    for fixture in (original, visual, srt):
        shutil.copy2(fixture, fixtures / fixture.name)
    print("Makon production-pipeline smoke render passed.")


if __name__ == "__main__":
    main()
