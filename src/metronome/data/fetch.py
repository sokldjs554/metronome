"""Download pinned sources and verify their SHA-256 before anything reads them."""

from __future__ import annotations

import hashlib
import shutil
import urllib.request
from pathlib import Path

from metronome.data.sources import SOURCES, Source


class ChecksumMismatch(RuntimeError):
    pass


def sha256_of(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def _download(url: str, dest: Path, timeout: float = 600.0) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "metronome/0.1 (+pinned dataset fetch)"})
    with urllib.request.urlopen(req, timeout=timeout) as resp, tmp.open("wb") as out:
        shutil.copyfileobj(resp, out)
    tmp.replace(dest)


def fetch(key: str, raw_dir: Path, local_dir: Path | None = None, *, force: bool = False) -> Path:
    """Return the verified raw file for `key`, downloading (or copying from `local_dir`) if needed.

    The returned path is only ever handed back if its SHA-256 matches the pinned value. A stale or
    tampered file is deleted and the function raises rather than returning it.
    """
    source: Source = SOURCES[key]
    dest = raw_dir / source.filename
    if dest.exists() and not force:
        if sha256_of(dest) == source.sha256:
            return dest
        dest.unlink()
    if local_dir is not None and (local_dir / source.filename).exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(local_dir / source.filename, dest)
    else:
        _download(source.url, dest)
    digest = sha256_of(dest)
    if digest != source.sha256:
        dest.unlink(missing_ok=True)
        raise ChecksumMismatch(
            f"{key}: expected {source.sha256[:12]}…, got {digest[:12]}… — refusing to use it"
        )
    return dest
