import io
import math
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.makon import (
    AUDIO_EXTENSIONS, PRESETS, build_script_direction, copy_validated_subtitles,
    estimate_speech_seconds, export_pack, persist_upload, redact_error,
    trim_audio, validate_srt, write_project,
)

SRT = "1\n00:00:00,000 --> 00:00:01,500\nSiz uchun qo'shiq.\n\n2\n00:00:01,500 --> 00:00:03,000\nMakon Music\n"


@pytest.mark.parametrize("preset", PRESETS)
@pytest.mark.parametrize("language", ["uz-UZ", "en-US", "ru-RU"])
def test_presets_and_languages(preset, language):
    prompt = build_script_direction(preset, language, 20)
    assert "42 words" in prompt
    assert "not a guaranteed audio duration" in prompt
    assert len(prompt) <= 2000


def test_editable_offer_not_unrequested_price():
    prompt = build_script_direction("music_ad", "uz-UZ", 30, 60000, 120000)
    assert "60,000" in prompt and "120,000" in prompt
    assert "only if the brief asks" in prompt
    assert "Makon Music" not in build_script_direction("story", "en-US", 20)


@pytest.mark.parametrize("seconds", [0, 4, 91])
def test_bad_target(seconds):
    with pytest.raises(ValueError):
        build_script_direction("music_ad", "uz-UZ", seconds)


def test_speech_estimate_empty():
    assert estimate_speech_seconds("") == 0
    assert estimate_speech_seconds("one two three four five six") == 3


def test_srt_preserves_real_timings():
    assert validate_srt("\ufeff" + SRT.replace("\n", "\r\n"), 3) == SRT


@pytest.mark.parametrize("bad", ["", "some lyrics", SRT.replace("01,500", "00,000", 1),
    SRT.replace("00:00:01,500 -->", "00:00:01,000 -->"),
    SRT.replace("00:00:03,000", "00:00:61,000"), SRT.replace("Makon", "\x00Makon")])
def test_bad_srt_rejected(bad):
    with pytest.raises(ValueError):
        validate_srt(bad, 3)


def test_srt_must_fit_excerpt():
    with pytest.raises(ValueError, match="after"):
        validate_srt(SRT, 2)
    with pytest.raises(ValueError):
        validate_srt(SRT, math.nan)


def test_manual_subtitles_contained_and_atomic(tmp_path):
    task = tmp_path / "task"
    task.mkdir()
    source = task / "upload.srt"
    source.write_text(SRT)
    result = copy_validated_subtitles(task, str(source), 3)
    assert Path(result).read_text() == SRT
    assert not list(task.glob("*.tmp"))
    outside = tmp_path / "private.srt"
    outside.write_text(SRT)
    with pytest.raises(ValueError, match="inside"):
        copy_validated_subtitles(task, str(outside), 3)
    with pytest.raises(ValueError, match="inside"):
        copy_validated_subtitles(task, "../private.srt", 3)


def test_symlink_escape_blocked(tmp_path):
    task = tmp_path / "task"
    task.mkdir()
    outside = tmp_path / "outside.srt"
    outside.write_text(SRT)
    try:
        (task / "link.srt").symlink_to(outside)
    except OSError:
        pytest.skip("Symlinks unavailable on this platform")
    with pytest.raises(ValueError):
        copy_validated_subtitles(task, "link.srt", 3)


def test_upload_ignores_client_path(tmp_path):
    target = persist_upload(tmp_path, "../../secret.wav", b"data", AUDIO_EXTENSIONS)
    assert target.parent == tmp_path and target.name.startswith("upload-")
    for filename, data in [("song.exe", b"data"), ("song.mp3", b"")]:
        with pytest.raises(ValueError):
            persist_upload(tmp_path, filename, data, AUDIO_EXTENSIONS)


def test_trim_validation_happens_before_subprocess(tmp_path):
    with patch("app.makon.subprocess.run") as run:
        for start, duration in [(-1, 2), (9, 5), (math.nan, 2), (1, 0)]:
            with pytest.raises(ValueError):
                trim_audio(tmp_path / "in.wav", tmp_path / "out.mp3", start, duration, 10, "ffmpeg")
        run.assert_not_called()


def test_export_excludes_secrets_and_paths(tmp_path):
    (tmp_path / "final-1.mp4").write_bytes(b"fake-test-video")
    (tmp_path / "config.toml").write_text('api_key="secret"')
    (tmp_path / "debug.log").write_text("secret")
    (tmp_path / "subtitle.srt").write_text(SRT)
    write_project(tmp_path, title="Example", preset="music_ad", language="uz-UZ", script="My script", caption="My caption")
    with zipfile.ZipFile(io.BytesIO(export_pack(tmp_path, tmp_path / "final-1.mp4"))) as archive:
        assert set(archive.namelist()) == {"video.mp4", "subtitle.srt", "script.txt", "caption.txt", "README.txt"}
        assert b"secret" not in b"".join(archive.read(n) for n in archive.namelist())
    with pytest.raises(ValueError):
        export_pack(tmp_path / "other", tmp_path / "final-1.mp4")


def test_errors_redact_saved_keys():
    assert "PRIVATE" not in redact_error("failed PRIVATE https://example.org/?key=PRIVATE", {"api_key": "PRIVATE"})
    assert "PRIVATE" not in redact_error("failed PRIVATE", {"pexels_api_keys": ["PRIVATE"]})
