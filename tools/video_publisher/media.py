"""Use local videos without copying them through the browser."""
from contextlib import contextmanager
from pathlib import Path
import tempfile

VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".avi"}


def local_video(raw: str) -> Path:
    path = Path(raw.strip().strip("\"'")).expanduser().resolve()
    if not path.is_file():
        raise ValueError("本机视频路径不存在或不是文件。")
    if path.suffix.lower() not in VIDEO_EXTENSIONS:
        raise ValueError("请选择 mp4、mov、m4v、webm 或 avi 视频。")
    return path


@contextmanager
def video_path(filename: str, data: bytes, local_path: str = ""):
    if local_path:
        yield str(local_video(local_path))
        return
    with tempfile.NamedTemporaryFile(suffix=Path(filename).suffix, delete=False) as handle:
        handle.write(data)
        path = Path(handle.name)
    try:
        yield str(path)
    finally:
        path.unlink(missing_ok=True)
