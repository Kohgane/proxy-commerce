#!/usr/bin/env bash
# ops/oracle_a1/backup_daily.sh — A1에서 매일 pg_dump · 로컬 7일 보관 · 외부 사본 1곳(암호화).
#
# 한 곳에 몰지 않는다: ① A1 디스크 /var/backups/kgp/daily(7일) ② 외부 = GitHub 비공개 저장소(기본) 또는 HF 비공개 데이터셋.
# 외부로 나가는 건 **암호화본만**(openssl AES-256 · 키 /root/.kgp_backup_key — 오너가 오프라인에 사본 하나 보관).
# 환경(파일 /etc/kgp-backup.env, 600):
#   DB_URL_FILE=/root/.kgp_local_url    # A1 로컬 접속 문자열(postgresql:///gogadb 등)
#   OFFSITE=github|hf|none
#   GIT_DIR=/var/backups/kgp/offsite-repo   # github: 배포 키로 push 되는 비공개 저장소 클론
#   HF_REPO=<user>/kgp-db-backup            # hf: huggingface-cli 로그인된 상태
set -euo pipefail
[ -f "${KGP_BACKUP_ENV:-/etc/kgp-backup.env}" ] && . "${KGP_BACKUP_ENV:-/etc/kgp-backup.env}"
: "${DB_URL_FILE:=/root/.kgp_local_url}"
KEEP_DAYS="${KEEP_DAYS:-7}"
DIR="${BACKUP_DIR:-/var/backups/kgp/daily}"; mkdir -p "$DIR"; chmod 700 "$DIR"
KEY="${BACKUP_KEY_FILE:-/root/.kgp_backup_key}"
[ -s "$KEY" ] || { umask 077; openssl rand -base64 48 > "$KEY"; echo "새 백업 키를 만들었어요: $KEY — 오프라인 사본 하나 꼭 보관"; }

STAMP="$(date -u +%Y%m%d)"
OUT="$DIR/gogadb_$STAMP.dump"
pg_dump --format=custom --no-owner --no-acl "$(head -n1 "$DB_URL_FILE")" --file="$OUT"
pg_restore --list "$OUT" >/dev/null                     # 덤프가 읽히는지(깨진 파일을 보관하지 않게)
find "$DIR" -name 'gogadb_*.dump' -mtime +"$((KEEP_DAYS - 1))" -delete
echo "로컬: $(ls "$DIR" | wc -l)개 · 오늘 $(du -h "$OUT" | cut -f1)"

ENC="$OUT.enc"
openssl enc -aes-256-cbc -pbkdf2 -salt -in "$OUT" -out "$ENC" -pass "file:$KEY"
case "${OFFSITE:-none}" in
  github)
    : "${GIT_DIR:?GIT_DIR 필요}"
    cp "$ENC" "$GIT_DIR/"
    ( cd "$GIT_DIR" && ls -1t gogadb_*.dump.enc | tail -n +$((KEEP_DAYS + 1)) | xargs -r git rm -q --cached --ignore-unmatch \
        && ls -1t gogadb_*.dump.enc | tail -n +$((KEEP_DAYS + 1)) | xargs -r rm -f \
        && git add gogadb_*.dump.enc && git commit -qm "backup $STAMP" && git push -q )
    echo "외부(GitHub 비공개): 올림" ;;
  hf)
    : "${HF_REPO:?HF_REPO 필요}"
    huggingface-cli upload "$HF_REPO" "$ENC" "daily/$(basename "$ENC")" --repo-type dataset --private >/dev/null
    echo "외부(HF 비공개 데이터셋): 올림" ;;
  none) echo "외부 사본: 꺼짐(OFFSITE=none) — 한 곳에만 있음, 켜 주세요" ;;
esac
rm -f "$ENC"
