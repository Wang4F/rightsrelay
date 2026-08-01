"""Download the pinned Piper demo voice and verify both file hashes."""

from __future__ import annotations

import hashlib
import os
import shutil
import time
import urllib.request
from pathlib import Path

REVISION = "9f967d15e9ccdf43078586d1476ee70f314401bd"
VOICE = "en_US-libritts_r-medium"
BASE_URL = (
    f"https://huggingface.co/rhasspy/piper-voices/resolve/{REVISION}/en/en_US/libritts_r/medium"
)
FILES = {
    f"{VOICE}.onnx": "10bb85e071d616fcf4071f369f1799d0491492ab3c5d552ec19fb548fac13195",
    f"{VOICE}.onnx.json": "b471dc60d2d8335e819c393d196d6fbf792817f40051257b269878505bc9afb3",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, destination: Path, expected_sha256: str) -> None:
    if destination.is_file() and sha256(destination) == expected_sha256:
        print(f"verified cached voice file: {destination.name}")
        return

    temporary = destination.with_suffix(destination.suffix + ".part")
    for attempt in range(1, 4):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "RightsRelay/0.1"})
            with (
                urllib.request.urlopen(request, timeout=90) as response,
                temporary.open("wb") as output,
            ):
                shutil.copyfileobj(response, output)
            actual = sha256(temporary)
            if actual != expected_sha256:
                raise RuntimeError(
                    f"SHA-256 mismatch for {destination.name}: expected "
                    f"{expected_sha256}, received {actual}"
                )
            os.replace(temporary, destination)
            print(f"downloaded and verified: {destination.name}")
            return
        except Exception:
            temporary.unlink(missing_ok=True)
            if attempt == 3:
                raise
            time.sleep(attempt * 2)


def main() -> None:
    destination_dir = Path(os.environ.get("RIGHTSRELAY_MODEL_DIR", ".models")).resolve()
    destination_dir.mkdir(parents=True, exist_ok=True)
    for filename, expected in FILES.items():
        download(f"{BASE_URL}/{filename}", destination_dir / filename, expected)


if __name__ == "__main__":
    main()
