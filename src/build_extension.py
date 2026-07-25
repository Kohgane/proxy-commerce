#!/usr/bin/env python3
"""src/build_extension.py — v83.1 STEP2: 확장 ZIP 패키징 단일 소스.

서버 다운로드(/seller/extension/download)와 CI 아티팩트가 **같은 함수**로 ZIP을 만든다. 예전엔 서버 라우트와
extensions/chrome-collector/build.sh가 각자 파일 목록을 들고 있어 drift가 났다(build.sh는 kgp-*.js 5개가 빠져
있어 그 ZIP으로 설치하면 추출기가 통째로 없는 확장이 나왔다). 여기 하나만 고치면 양쪽이 같이 고쳐진다.

**위치가 src/인 이유:** Dockerfile이 `src/`는 COPY하지만 `scripts/`는 start_render.sh·migrate만 COPY한다.
scripts/에 두면 배포 이미지에서 import가 깨져 다운로드 라우트가 죽는다(#423 재발 방지). CLI 래퍼만 scripts/에 둔다.

빌드 각인(STEP2): ZIP 안에 `build-info.json`(commit·built_at·version·source)을 넣는다. 확장이 진단 파일에
이 값을 실어 주므로, 채팅 채점에서 **오너가 어느 빌드를 깔았는지**(브랜치 빌드인지 스토어 구버전인지)를
버전 문자열만이 아니라 커밋 단위로 즉판할 수 있다. 커밋을 못 구하면 빈 값 + source로 정직하게 표기한다.

CLI: python scripts/build_extension_zip.py [출력경로.zip]
"""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple
import zipfile

EXT_DIRNAME = Path("extensions/chrome-collector")

# ZIP 루트에 들어가는 파일(디렉토리 구조 그대로). manifest.json은 **반드시 루트**여야 크롬이 찾는다.
INCLUDE_FILES = [
    "manifest.json",
    "background.js",
    "kgp-sources.js",
    "kgp-net.js",
    "kgp-extractor.js",
    "kgp-detect.js",
    "kgp-main.js",
    "content_script.js",
    "popup.html",
    "popup.js",
    "options.html",
    "options.js",
    "README.md",
]
INCLUDE_DIRS = ["icons"]


def _run_git(args, cwd: Path) -> str:
    try:
        out = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, timeout=10)
        if out.returncode == 0:
            return (out.stdout or "").strip()
    except Exception:
        pass
    return ""


def resolve_commit(repo_root: Path) -> Tuple[str, str]:
    """(commit, source) 반환. 못 구하면 ('', 'unknown') — 가짜 해시 금지.

    ※ PR 워크플로에서는 GITHUB_SHA 기본값이 GitHub이 만든 **머지 커밋**이라 오너가 브랜치에서 보는 해시와
      다르다 → ci.yml이 head SHA로 덮어쓴다(각인을 눈으로 대조 가능하게).
    """
    for env_key, src in (("GITHUB_SHA", "ci"), ("RENDER_GIT_COMMIT", "render"), ("KGP_BUILD_COMMIT", "env")):
        v = (os.environ.get(env_key) or "").strip()
        if v:
            return v, src
    v = _run_git(["rev-parse", "HEAD"], repo_root)
    if v:
        return v, "git"
    return "", "unknown"


def build_info(repo_root: Path, version: str) -> dict:
    commit, source = resolve_commit(repo_root)
    branch = (os.environ.get("GITHUB_REF_NAME") or "").strip() or _run_git(["rev-parse", "--abbrev-ref", "HEAD"], repo_root)
    return {
        "version": version,
        "commit": commit,                 # 못 구하면 "" (정직 — 채점에서 'unknown 빌드'로 읽힌다)
        "commit_short": commit[:7] if commit else "",
        "branch": branch,
        "source": source,                 # ci | render | env | git | unknown
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def read_version(ext_dir: Path) -> str:
    try:
        return str(json.loads((ext_dir / "manifest.json").read_text(encoding="utf-8")).get("version") or "")
    except Exception:
        return ""


def build_zip_bytes(repo_root: Optional[Path] = None) -> Tuple[bytes, str, dict]:
    """(zip 바이트, 파일명, build_info) 반환."""
    root = Path(repo_root) if repo_root else Path(__file__).resolve().parent.parent
    ext_dir = root / EXT_DIRNAME
    if not ext_dir.is_dir():
        raise FileNotFoundError(f"확장 디렉토리 없음: {ext_dir}")
    version = read_version(ext_dir) or "1"
    info = build_info(root, version)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name in INCLUDE_FILES:
            p = ext_dir / name
            if p.is_file():
                z.write(p, arcname=name)
        for d in INCLUDE_DIRS:
            dp = ext_dir / d
            if dp.is_dir():
                for f in sorted(dp.iterdir()):
                    if f.is_file():
                        z.write(f, arcname=f"{d}/{f.name}")
        # v83.1 STEP2: 빌드 각인(소스 트리는 건드리지 않고 ZIP 안에만 넣는다).
        z.writestr("build-info.json", json.dumps(info, ensure_ascii=False, indent=2))
    return buf.getvalue(), f"gogasujipgi-v{version}.zip", info


def main() -> int:
    data, fname, info = build_zip_bytes()
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("dist") / fname
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    print(f"확장 ZIP: {out} ({len(data)} bytes)")
    print(f"빌드 각인: version={info['version']} commit={info['commit_short'] or '(없음)'} source={info['source']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
