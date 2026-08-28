#!/usr/bin/env bash
# 세션 시작 1단계 — 컨테이너 레포 역행 감지(오너 2026-08-28, 이번 세션 3회 재발).
#
# 증상: 원격 컨테이너가 리포를 옛 커밋으로 되돌려 놓는다(예: #663~#676이 통째로 사라진 상태로 시작).
#       그대로 작업하면 이미 머지된 수리 위에 옛 코드를 얹게 되고, 전체 스위트 숫자도 무효가 된다.
# 감지: HEAD != origin/main. (사람 눈으로는 '최근 머지 파일 부재'로 드러난다 — 예: import 누락.)
# 원칙: **감지·보고만 한다. 자동 reset 금지** — 미커밋 작업을 날릴 수 있다. 판단은 세션이 한다.
set -u
cd "${CLAUDE_PROJECT_DIR:-.}" 2>/dev/null || exit 0
git rev-parse --git-dir >/dev/null 2>&1 || exit 0

git fetch origin main --quiet 2>/dev/null || {
  echo "[레포 동기화 점검] origin fetch 실패 — 네트워크 확인 후 수동으로 git fetch."
  exit 0
}

head_sha=$(git rev-parse HEAD 2>/dev/null)
main_sha=$(git rev-parse origin/main 2>/dev/null)
[ -n "$head_sha" ] && [ -n "$main_sha" ] || exit 0

if [ "$head_sha" = "$main_sha" ]; then
  echo "[레포 동기화 점검] HEAD == origin/main ($(git rev-parse --short HEAD)) — 착수 가능."
  exit 0
fi

behind=$(git rev-list --count HEAD..origin/main 2>/dev/null || echo "?")
ahead=$(git rev-list --count origin/main..HEAD 2>/dev/null || echo "?")
dirty=$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')

echo "[레포 동기화 점검] ⚠️ HEAD != origin/main — **착수 전 재동기화 판단 필요**"
echo "  HEAD        : $(git log --oneline -1 2>/dev/null)"
echo "  origin/main : $(git log --oneline -1 origin/main 2>/dev/null)"
echo "  뒤처짐 ${behind}커밋 / 앞섬 ${ahead}커밋 / 미커밋 변경 ${dirty}건"
if [ "$behind" != "0" ] && [ "$ahead" = "0" ] && [ "$dirty" = "0" ]; then
  echo "  → 순수 역행(앞선 커밋·미커밋 변경 0). 재동기화 안전:"
  echo "    git fetch origin main && git reset --hard origin/main && git checkout -B <작업브랜치> origin/main"
else
  echo "  → 앞선 커밋 또는 미커밋 변경이 있다. **reset 금지** — 무엇을 살릴지 먼저 확인할 것."
fi
exit 0
