#!/usr/bin/env bash
# extensions/chrome-collector/build.sh — 크롬 확장 ZIP 패키징(래퍼).
#
# v83.1 STEP2: 파일 목록을 여기서 따로 들지 않는다. 예전 버전은 kgp-*.js 5개(추출기·감지·소싱처 레지스트리…)가
# 빠진 목록을 들고 있어서, 이 스크립트로 만든 ZIP을 설치하면 manifest가 선언한 스크립트가 없는 깨진 확장이 나왔다.
# 이제 서버 다운로드·CI 아티팩트와 **같은 단일 소스**(src/build_extension.py)를 호출한다.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

echo "고가수집기 빌드 시작..."
cd "${REPO_ROOT}"
python scripts/build_extension_zip.py

echo ""
echo "크롬 웹스토어 또는 개발자 모드에서 로드하세요:"
echo "  chrome://extensions/ → 개발자 모드 ON → 압축 해제된 확장 프로그램 로드 → ${SCRIPT_DIR}"
