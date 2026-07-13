"""Build a versioned AYON addon zip."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import zipfile
from pathlib import Path

import package


ROOT = Path(__file__).parent


def _build_frontend(skip: bool) -> None:
    if skip:
        return
    npm = os.getenv("NPM_EXECUTABLE") or shutil.which("npm") or shutil.which("npm.cmd")
    if npm is None:
        raise RuntimeError("npm is required (or pass --skip-frontend-build)")
    env = os.environ.copy()
    env["PATH"] = os.fspath(Path(npm).parent) + os.pathsep + env.get("PATH", "")
    subprocess.run([npm, "install"], cwd=ROOT / "frontend", env=env, check=True)
    subprocess.run([npm, "run", "build"], cwd=ROOT / "frontend", env=env, check=True)


def _client_zip() -> bytes:
    output = ROOT / "package" / ".client.zip"
    output.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        client_root = ROOT / "client" / package.client_dir
        for path in client_root.rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts:
                archive.write(path, path.relative_to(ROOT / "client"))
        archive.write(ROOT / "client" / "pyproject.toml", "pyproject.toml")
    data = output.read_bytes()
    output.unlink()
    return data


def build(skip_frontend: bool = False) -> Path:
    _build_frontend(skip_frontend)
    output_dir = ROOT / "package"
    output_dir.mkdir(exist_ok=True)
    output = output_dir / f"{package.name}-{package.version}.zip"
    client_data = _client_zip()
    roots = ["server", "public"]
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(ROOT / "package.py", "package.py")
        for root_name in roots:
            root = ROOT / root_name
            if not root.exists():
                continue
            for path in root.rglob("*"):
                if path.is_file() and "__pycache__" not in path.parts:
                    archive.write(path, path.relative_to(ROOT))
        dist = ROOT / "frontend" / "dist"
        if dist.exists():
            for path in dist.rglob("*"):
                if path.is_file():
                    archive.write(path, path.relative_to(ROOT))
        archive.writestr("private/client.zip", client_data)
        archive.write(ROOT / "client" / "pyproject.toml", "private/pyproject.toml")
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-frontend-build", action="store_true")
    args = parser.parse_args()
    print(os.fspath(build(args.skip_frontend_build)))
