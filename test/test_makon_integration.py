from pathlib import Path
from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest

from app.config import config
from app.models.schema import VideoParams
from app.services import task
from test.makon_media_cases import TestMakonMedia

ROOT = Path(__file__).resolve().parents[1]
SRT = "1\n00:00:00,000 --> 00:00:02,000\nA real timed caption.\n"


def test_manual_srt_enters_real_pipeline(tmp_path):
    upload = tmp_path / "uploaded.srt"
    upload.write_text(SRT)
    params = VideoParams(video_subject="Test", custom_subtitle_file=str(upload))
    with patch.object(task.utils, "task_dir", return_value=str(tmp_path)), \
         patch.object(task.voice, "get_audio_duration", return_value=3), \
         patch.object(task.voice, "create_subtitle") as tts, \
         patch.object(task.subtitle, "create") as whisper:
        result = task.generate_subtitle("test", params, "Reference only", None, "audio.wav")
        assert Path(result).read_text() == SRT
        tts.assert_not_called()
        whisper.assert_not_called()


def test_manual_srt_outside_task_rejected(tmp_path):
    upload = tmp_path / "private.srt"
    upload.write_text(SRT)
    root = tmp_path / "task"
    root.mkdir()
    params = VideoParams(video_subject="Test", custom_subtitle_file=str(upload))
    with patch.object(task.utils, "task_dir", return_value=str(root)), \
         patch.object(task.voice, "get_audio_duration", return_value=3):
        with pytest.raises(ValueError):
            task.generate_subtitle("test", params, "", None, "audio.wav")


def test_existing_directory_never_deleted_for_config(tmp_path):
    folder = tmp_path / "config.toml"
    folder.mkdir()
    marker = folder / "important.txt"
    marker.write_text("Keep me")
    with patch.object(config, "config_file", str(folder)):
        with pytest.raises(IsADirectoryError):
            config.load_config()
    assert marker.read_text() == "Keep me"


def test_english_workspace_and_presets_load_without_keys():
    page = AppTest.from_file(str(ROOT / "webui/Makon.py"), default_timeout=45).run()
    assert not page.exception, [str(e.value) for e in page.exception]
    assert page.title[0].value == "Your next video starts here."
    assert [tab.label for tab in page.tabs] == ["Create", "Library", "Settings"]
    workflow = next(w for w in page.selectbox if w.key == "preset")
    workflow.set_value("song_reel").run()
    assert not page.exception, [str(e.value) for e in page.exception]
    assert page.session_state["audio_mode"] == "Upload a finished song / voiceover"
    assert page.session_state["captions"] == "Off"
    assert next(b for b in page.button if b.label == "Render my video").disabled
    next(w for w in page.selectbox if w.key == "preset").set_value("story").run()
    assert not page.exception
    assert page.session_state["language"] == "en-US"


def test_launcher_targets_makon_and_defaults_local():
    for filename in ("webui.sh", "webui.bat"):
        content = (ROOT / filename).read_text()
        assert "Makon.py" in content
        assert "127.0.0.1" in content
