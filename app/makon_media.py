"""Keep visual uploads inside the renderer's existing safe media directory."""
from pathlib import Path
from uuid import UUID

from app.utils import utils


def visual_upload_directory(task_id: str) -> Path:
    """Allocate per-task media without broadening the renderer's read permissions."""
    identifier = str(UUID(task_id))
    base = Path(utils.storage_dir("local_videos", create=True)).resolve()
    directory = base / "makon" / identifier
    if not directory.resolve().is_relative_to(base):
        raise ValueError("The local visual directory cannot escape the media sandbox.")
    directory.mkdir(parents=True, exist_ok=True)
    return directory.resolve()
