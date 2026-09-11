from unittest.mock import patch
from uuid import uuid4

import pytest
from PIL import Image

from app.makon_media import visual_upload_directory
from app.models.schema import MaterialInfo
from app.services import video
from app.utils import file_security, utils


class TestMakonMedia:
    def test_saved_visual_is_accepted_by_real_preprocessor(self, tmp_path):
        with patch.object(utils, "storage_dir", return_value=str(tmp_path)):
            directory = visual_upload_directory(str(uuid4()))
            image = directory / "frame.png"
            Image.new("RGB", (1080, 1920)).save(image)
            assert file_security.resolve_path_within_directory(str(tmp_path), str(image)) == str(image)
            with patch.object(video, "render_image_zoom_video", return_value=str(image) + ".mp4") as render:
                result = video.preprocess_video([MaterialInfo(provider="local", url=str(image))])
            assert len(result) == 1
            render.assert_called_once()
            assert result[0].url == str(image) + ".mp4"

    def test_task_storage_is_not_mistaken_for_visual_storage(self, tmp_path):
        with patch.object(utils, "storage_dir", return_value=str(tmp_path / "local_videos")):
            directory = visual_upload_directory(str(uuid4()))
            assert directory.is_relative_to(tmp_path / "local_videos")
            assert directory.parent.name == "makon"
            with pytest.raises(ValueError):
                visual_upload_directory("../../private")

    def test_outside_visuals_still_rejected(self, tmp_path):
        outside = tmp_path / "private.png"
        Image.new("RGB", (1080, 1920)).save(outside)
        with patch.object(utils, "storage_dir", return_value=str(tmp_path / "local_videos")):
            assert video.preprocess_video([MaterialInfo(provider="local", url=str(outside))]) == []
