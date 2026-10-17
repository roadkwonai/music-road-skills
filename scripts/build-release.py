#!/usr/bin/env python3
"""Build a reproducible, allow-listed skill bundle with only stdlib modules."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import zipfile

VERSION = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
ROOT = Path(__file__).resolve().parents[1]
TOP_FILES = ("README.md", "manifest.json", "LICENSE", "VERSION", "AGENTS.md")
TOP_DIRS = ("skills", "docs", "release", "scripts")

def fail(message: str) -> None:
    raise SystemExit(message)

def load_bundle(root: Path) -> tuple[dict, str]:
    try:
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        version = (root / "VERSION").read_text(encoding="utf-8").strip()
    except (OSError, json.JSONDecodeError) as error:
        fail(f"bundle metadata read failed: {error}")
    if manifest.get("schemaVersion") != 1 or manifest.get("name") != "music-road-skills" or manifest.get("version") != version or not VERSION.fullmatch(version):
        fail("manifest.json and VERSION must contain the same stable version")
    skills = manifest.get("skills")
    if not isinstance(skills, list) or not skills:
        fail("manifest skills must be a non-empty list")
    ids = set()
    for item in skills:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or item["id"] in ids or item.get("path") != f"skills/{item['id']}":
            fail("manifest skill id/path is invalid")
        ids.add(item["id"])
        if not (root / item["path"] / "SKILL.md").is_file():
            fail(f"missing SKILL.md: {item['id']}")
    return manifest, version

def allowed_paths(root: Path, manifest: dict) -> list[Path]:
    files: list[Path] = []
    for name in TOP_FILES:
        item = root / name
        if item.is_symlink() or not item.is_file(): fail(f"missing or symlinked required file: {name}")
        files.append(item)
    if any(root.glob(".env*")):
        fail("private .env files are not packageable")
    for skill in manifest["skills"]:
        if (root / "skills").is_symlink(): fail("symlinked skills directory is not allowed")
        directory = root / skill["path"]
        if directory.is_symlink(): fail(f"symlinked skill is not allowed: {skill['id']}")
        for item in sorted(directory.rglob("*")):
            if "__pycache__" in item.relative_to(root).parts: continue
            if item.is_symlink(): fail(f"symlink is not allowed: {item.relative_to(root)}")
            if any(part.startswith(".env") for part in item.relative_to(root).parts): fail(f"private path is not packageable: {item.relative_to(root)}")
            if item.is_file(): files.append(item)
    for name in ("docs", "release", "scripts"):
        directory = root / name
        if not directory.exists(): continue
        if directory.is_symlink(): fail(f"symlinked directory is not allowed: {name}")
        for item in sorted(directory.rglob("*")):
            if "__pycache__" in item.relative_to(root).parts: continue
            if item.is_symlink(): fail(f"symlink is not allowed: {item.relative_to(root)}")
            if any(part.startswith(".env") for part in item.relative_to(root).parts): fail(f"private path is not packageable: {item.relative_to(root)}")
            if item.is_file(): files.append(item)
    return files

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    root = args.root.resolve(); manifest, version = load_bundle(root)
    output = (args.out or root / "dist").resolve(); output.mkdir(parents=True, exist_ok=True)
    archive = output / f"MusicRoad-Skills-{version}.zip"
    if archive.exists(): fail(f"refusing to overwrite existing artifact: {archive}")
    prefix = f"MusicRoad-Skills-{version}"
    try:
        with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
            for item in allowed_paths(root, manifest):
                relative = item.relative_to(root).as_posix()
                if relative.startswith((".env", ".git/", "dist/")) or "/.env" in relative:
                    fail(f"private path is not packageable: {relative}")
                info = zipfile.ZipInfo(f"{prefix}/{relative}")
                info.date_time = (1980, 1, 1, 0, 0, 0)
                info.external_attr = (stat.S_IFREG | 0o644) << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                bundle.writestr(info, item.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    except Exception:
        archive.unlink(missing_ok=True)
        raise
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    sums = output / "SHA256SUMS.txt"
    if sums.exists(): fail(f"refusing to overwrite existing checksums: {sums}")
    sums.write_text(f"{digest}  {archive.name}\n", encoding="utf-8")
    print(json.dumps({"version": version, "archive": str(archive), "sha256": digest, "checksums": str(sums)}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    sys.exit(main())
