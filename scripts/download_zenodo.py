#!/usr/bin/env python3
"""Download the Zenodo 77 GHz FMCW radar dataset.

DOI: 10.5281/zenodo.5845259

Usage:
    python scripts/download_zenodo.py --out data/raw/zenodo_77ghz
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from pathlib import Path

import requests
from tqdm import tqdm

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DOI = "10.5281/zenodo.5845259"
ZENODO_API = "https://zenodo.org/api/records"
RECORD_ID = "5845259"

# Files we need from the Zenodo record
REQUIRED_FILES = [
    "data_SAAB_SIRS_77GHz_FMCW.npy",
    "ReadMe.txt",
]

CHUNK_SIZE = 8 * 1024 * 1024  # 8 MB


def _resolve_zenodo_files(record_id: str) -> dict[str, dict]:
    """Query the Zenodo API and return {filename: {url, size, checksum}}."""
    url = f"{ZENODO_API}/{record_id}"
    logger.info("Querying Zenodo API: %s", url)
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    files_info: dict[str, dict] = {}
    for f in data.get("files", []):
        name = f.get("key", f.get("filename", ""))
        files_info[name] = {
            "url": f.get("links", {}).get("self", ""),
            "size": f.get("size", 0),
            "checksum": f.get("checksum", ""),  # "md5:abc123..."
        }
    return files_info


def _download_file(
    url: str,
    dest: Path,
    expected_size: int = 0,
    expected_md5: str = "",
    resume: bool = True,
) -> None:
    """Download a file with resume support and optional MD5 check."""
    dest.parent.mkdir(parents=True, exist_ok=True)

    # Resume support
    existing_size = dest.stat().st_size if dest.exists() else 0
    if resume and existing_size > 0 and expected_size and existing_size < expected_size:
        headers = {"Range": f"bytes={existing_size}-"}
        logger.info("Resuming download from byte %d", existing_size)
    elif existing_size > 0 and expected_size and existing_size == expected_size:
        logger.info("File already complete: %s", dest.name)
        if expected_md5:
            _verify_md5(dest, expected_md5)
        return
    else:
        headers = {}
        existing_size = 0

    resp = requests.get(url, headers=headers, stream=True, timeout=60)
    resp.raise_for_status()

    total = int(resp.headers.get("content-length", 0)) + existing_size
    mode = "ab" if existing_size > 0 else "wb"

    with open(dest, mode) as f, tqdm(
        total=total,
        initial=existing_size,
        unit="B",
        unit_scale=True,
        desc=dest.name,
    ) as pbar:
        for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
            if chunk:
                f.write(chunk)
                pbar.update(len(chunk))

    if expected_md5:
        _verify_md5(dest, expected_md5)

    logger.info("Downloaded %s (%.1f MB)", dest.name, dest.stat().st_size / 1e6)


def _verify_md5(path: Path, expected: str) -> None:
    """Verify MD5 checksum."""
    md5 = hashlib.md5()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break
            md5.update(chunk)
    actual = md5.hexdigest()
    if actual != expected:
        logger.warning("MD5 mismatch for %s: expected %s, got %s", path.name, expected, actual)
    else:
        logger.info("MD5 verified: %s", path.name)


def _create_download_manifest(out_dir: Path, files_info: dict) -> None:
    """Write a small JSON manifest after download."""
    manifest = {
        "doi": DOI,
        "record_id": RECORD_ID,
        "files": {},
    }
    for name in REQUIRED_FILES:
        fpath = out_dir / name
        if fpath.exists():
            manifest["files"][name] = {
                "size_bytes": fpath.stat().st_size,
                "md5": files_info.get(name, {}).get("checksum", ""),
            }
    manifest_path = out_dir / "download_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    logger.info("Wrote download manifest: %s", manifest_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Download Zenodo 77 GHz FMCW radar dataset")
    parser.add_argument(
        "--out",
        type=str,
        default="data/raw/zenodo_77ghz",
        help="Output directory (default: data/raw/zenodo_77ghz)",
    )
    parser.add_argument("--no-resume", action="store_true", help="Disable resume (re-download)")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Resolve file URLs from Zenodo API
    try:
        files_info = _resolve_zenodo_files(RECORD_ID)
    except Exception as e:
        logger.error("Failed to query Zenodo API: %s", e)
        sys.exit(1)

    # Download each required file
    for fname in REQUIRED_FILES:
        info = files_info.get(fname)
        if info is None:
            # Try case-insensitive match
            for k, v in files_info.items():
                if k.lower() == fname.lower():
                    info = v
                    break
        if info is None:
            logger.warning("File '%s' not found in Zenodo record. Skipping.", fname)
            continue

        url = info["url"]
        if not url:
            logger.warning("No download URL for '%s'. Skipping.", fname)
            continue

        checksum = info.get("checksum", "")
        md5 = checksum.replace("md5:", "") if checksum.startswith("md5:") else ""

        _download_file(
            url=url,
            dest=out_dir / fname,
            expected_size=info.get("size", 0),
            expected_md5=md5,
            resume=not args.no_resume,
        )

    _create_download_manifest(out_dir, files_info)
    logger.info("Done. Dataset saved to %s", out_dir)


if __name__ == "__main__":
    main()
