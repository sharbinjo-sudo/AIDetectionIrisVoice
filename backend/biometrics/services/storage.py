from __future__ import annotations

from contextlib import ExitStack, contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile

from django.conf import settings


@contextmanager
def temporary_upload(uploaded_file, prefix: str, suffix: str):
    temp_dir = Path(settings.MEDIA_ROOT) / "tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)

    with NamedTemporaryFile(
        delete=False,
        dir=temp_dir,
        prefix=prefix,
        suffix=suffix,
    ) as handle:
        for chunk in uploaded_file.chunks():
            handle.write(chunk)
        temp_path = Path(handle.name)

    try:
        yield str(temp_path)
    finally:
        if not settings.RETAIN_PROCESSED_UPLOADS and temp_path.exists():
            temp_path.unlink(missing_ok=True)


@contextmanager
def temporary_uploads(uploaded_files, prefix: str, suffix: str):
    with ExitStack() as stack:
        paths = [
            stack.enter_context(
                temporary_upload(upload, prefix=f"{prefix}{index}_", suffix=suffix)
            )
            for index, upload in enumerate(uploaded_files)
        ]
        yield paths
