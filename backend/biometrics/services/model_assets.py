from __future__ import annotations

from pathlib import Path
from shutil import copyfileobj
from tempfile import NamedTemporaryFile
from urllib.error import URLError
from urllib.request import Request, urlopen

from django.conf import settings

from .exceptions import ModelUnavailableError


def ensure_remote_asset(
    *,
    destination: Path,
    description: str,
    urls: list[str],
) -> Path:
    if destination.exists():
        return destination

    if settings.BIOMETRIC_OFFLINE_MODE:
        raise ModelUnavailableError(
            f"The local {description} asset is missing at {destination}. "
            "Install the model files before running offline; no download was attempted."
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    last_error: Exception | None = None

    for url in urls:
        try:
            request = Request(
                url,
                headers={"User-Agent": "BioFusionAI/1.0"},
            )
            with urlopen(
                request,
                timeout=settings.MODEL_DOWNLOAD_TIMEOUT_SECONDS,
            ) as response:
                with NamedTemporaryFile(
                    delete=False,
                    dir=destination.parent,
                    prefix=f"{destination.stem}_",
                    suffix=".tmp",
                ) as temporary_file:
                    copyfileobj(response, temporary_file)
                    temp_path = Path(temporary_file.name)
            temp_path.replace(destination)
            return destination
        except Exception as exc:  # pragma: no cover - exercised in real runtime
            last_error = exc

    detail = str(last_error) if last_error else "unknown download error"
    raise ModelUnavailableError(
        f"Unable to provision the {description}. Check the model asset path or provisioning settings. Detail: {detail}"
    )


def normalize_path(path_like: str | Path | None) -> Path | None:
    if not path_like:
        return None
    return Path(path_like).expanduser().resolve()
