#!/usr/bin/env bash
# extensions/chrome-collector/build.sh — 크롬 확장 ZIP 패키징

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_DIR="${SCRIPT_DIR}/../../dist"
ZIP_NAME="kohgane-chrome-collector-v$(grep '"version"' "${SCRIPT_DIR}/manifest.json" | grep -oE '[0-9]+\.[0-9]+\.[0-9]+').zip"

mkdir -p "${OUTPUT_DIR}"

echo "📦 코가네 퍼센티 수집기 빌드 시작..."

cd "${SCRIPT_DIR}"
zip -r "${OUTPUT_DIR}/${ZIP_NAME}" \
  manifest.json \
  background.js \
  content_script.js \
  popup.html \
  popup.js \
  options.html \
  options.js \
  icons/ \
  README.md \
  --exclude "*.DS_Store" \
  --exclude "build.sh"

echo "✅ 빌드 완료: ${OUTPUT_DIR}/${ZIP_NAME}"
echo ""
echo "크롬 웹스토어 또는 개발자 모드에서 로드하세요:"
echo "  chrome://extensions/ → 개발자 모드 ON → 압축 해제된 확장 프로그램 로드 → ${SCRIPT_DIR}"
