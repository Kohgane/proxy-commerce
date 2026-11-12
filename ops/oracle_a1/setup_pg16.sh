#!/usr/bin/env bash
# ops/oracle_a1/setup_pg16.sh — 오라클 A1(ARM · Always Free)에 PostgreSQL 16 + TLS + 「Render 아웃바운드 IP만」 5432.
#
# 오너 긴급 2026-11-12: Supabase 무료 조직 402(전송량) → DB를 A1으로. 오라클 무료 아웃바운드 10TB/월.
# 옆 마이크로(instance-20260824-1457)는 다른 세션 것 — 이 스크립트는 **A1에서만** 돌린다.
#
# 쓰는 법(A1에서 root로):
#   sudo RENDER_CIDRS="1.2.3.4/32,5.6.7.0/24" bash setup_pg16.sh
#   - RENDER_CIDRS: Render 대시보드 › 서비스 › Connect › Outbound 의 IP(싱가포르) 전부, 쉼표로. 없으면 멈춘다.
#   - 비밀번호는 만들어서 /root/.kgp_db_pass(600)에만 둔다 — 화면·로그·채팅에 찍지 않는다.
# 다시 돌려도 된다(멱등): 이미 있으면 건너뛰고 규칙만 다시 맞춘다.
set -euo pipefail

DB_NAME="${DB_NAME:-gogadb}"
DB_USER="${DB_USER:-kgp_app}"
PASS_FILE="${PASS_FILE:-/root/.kgp_db_pass}"
: "${RENDER_CIDRS:?RENDER_CIDRS 가 비었어요 — Render 대시보드 Outbound IP를 쉼표로 넣어 주세요}"

[ "$(id -u)" = 0 ] || { echo "root로 돌려 주세요(sudo)"; exit 1; }
[ "$(uname -m)" = aarch64 ] || echo "주의: aarch64가 아니에요($(uname -m)) — A1이 맞는지 확인"
. /etc/os-release

echo "== 1) PostgreSQL 16 설치 ($ID $VERSION_ID)"
if ! command -v /usr/pgsql-16/bin/postgres >/dev/null 2>&1 && ! [ -x /usr/lib/postgresql/16/bin/postgres ]; then
  case "$ID" in
    ol|rhel|centos|rocky|almalinux)
      dnf install -y "https://download.postgresql.org/pub/repos/yum/reporpms/EL-${VERSION_ID%%.*}-aarch64/pgdg-redhat-repo-latest.noarch.rpm"
      dnf -qy module disable postgresql || true
      dnf install -y postgresql16-server postgresql16 openssl
      /usr/pgsql-16/bin/postgresql-16-setup initdb
      ;;
    ubuntu|debian)
      apt-get update -y && apt-get install -y curl ca-certificates gnupg openssl
      install -d /usr/share/postgresql-common/pgdg
      curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc
      echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt ${VERSION_CODENAME}-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list
      apt-get update -y && apt-get install -y postgresql-16
      ;;
    *) echo "모르는 OS: $ID"; exit 1 ;;
  esac
fi

if [ -d /var/lib/pgsql/16/data ]; then
  PGDATA=/var/lib/pgsql/16/data; CONF_DIR=$PGDATA; SVC=postgresql-16
else
  PGDATA=/var/lib/postgresql/16/main; CONF_DIR=/etc/postgresql/16/main; SVC=postgresql
fi

echo "== 2) TLS 인증서(자체 서명 · 10년) — Render는 sslmode=require(암호화만, 인증서 검증 안 함)"
if [ ! -f "$PGDATA/server.crt" ]; then
  openssl req -new -x509 -days 3650 -nodes -subj "/CN=kgp-a1-db" \
    -keyout "$PGDATA/server.key" -out "$PGDATA/server.crt" >/dev/null 2>&1
  chown postgres:postgres "$PGDATA/server.key" "$PGDATA/server.crt"
  chmod 600 "$PGDATA/server.key"
fi

echo "== 3) postgresql.conf"
CONF="$CONF_DIR/postgresql.conf"
sed -i '/^# kgp-begin/,/^# kgp-end/d' "$CONF"
cat >> "$CONF" <<CONFEOF
# kgp-begin (ops/oracle_a1/setup_pg16.sh)
listen_addresses = '*'
ssl = on
ssl_cert_file = '$PGDATA/server.crt'
ssl_key_file = '$PGDATA/server.key'
ssl_min_protocol_version = 'TLSv1.2'
password_encryption = 'scram-sha-256'
max_connections = 60
shared_buffers = 512MB
log_connections = on
# kgp-end
CONFEOF

echo "== 4) pg_hba.conf — 원격은 hostssl + scram, Render CIDR만"
HBA="$CONF_DIR/pg_hba.conf"
sed -i '/^# kgp-begin/,/^# kgp-end/d' "$HBA"
{
  echo "# kgp-begin (ops/oracle_a1/setup_pg16.sh)"
  IFS=',' read -ra CIDRS <<< "$RENDER_CIDRS"
  for c in "${CIDRS[@]}"; do
    c="$(echo "$c" | tr -d ' ')"
    [ -n "$c" ] && echo "hostssl $DB_NAME $DB_USER $c scram-sha-256"
  done
  echo "# kgp-end"
} >> "$HBA"

systemctl enable --now "$SVC"
systemctl restart "$SVC"

echo "== 5) 사용자·DB (비밀번호는 $PASS_FILE 에만)"
if [ ! -s "$PASS_FILE" ]; then
  umask 077; openssl rand -base64 33 | tr -d '/+=\n' > "$PASS_FILE"
fi
PW="$(cat "$PASS_FILE")"
sudo -u postgres psql -v ON_ERROR_STOP=1 -q <<SQL
DO \$\$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '$DB_USER') THEN
    CREATE ROLE $DB_USER LOGIN;
  END IF;
END \$\$;
ALTER ROLE $DB_USER WITH LOGIN PASSWORD '$PW';
SQL
sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" | grep -q 1 \
  || sudo -u postgres createdb -O "$DB_USER" "$DB_NAME"
sudo -u postgres psql -d "$DB_NAME" -qc "CREATE EXTENSION IF NOT EXISTS pgcrypto; CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\";"
unset PW

echo "== 6) 호스트 방화벽 — 5432는 Render CIDR만"
if command -v firewall-cmd >/dev/null 2>&1 && systemctl is-active --quiet firewalld; then
  firewall-cmd --permanent --list-rich-rules | grep 'port="5432"' | while read -r rule; do
    firewall-cmd --permanent --remove-rich-rule="$rule" >/dev/null || true      # 예전 CIDR 규칙은 지우고 다시 넣는다
  done
  for c in "${CIDRS[@]}"; do
    c="$(echo "$c" | tr -d ' ')"; [ -n "$c" ] || continue
    firewall-cmd --permanent --add-rich-rule="rule family=\"ipv4\" source address=\"$c\" port port=\"5432\" protocol=\"tcp\" accept" >/dev/null
  done
  firewall-cmd --reload >/dev/null
  echo "firewalld: $(firewall-cmd --list-rich-rules | grep -c 5432) 규칙"
else
  # 오라클 우분투 이미지: iptables 규칙 파일(/etc/iptables/rules.v4)이 맨 끝 REJECT — 그 앞에 넣는다
  iptables -S INPUT | grep -- '--dport 5432' | sed 's/^-A/-D/' | while read -r rule; do iptables $rule || true; done
  for c in "${CIDRS[@]}"; do
    c="$(echo "$c" | tr -d ' ')"; [ -n "$c" ] || continue
    pos="$(iptables -L INPUT --line-numbers -n | awk '/REJECT/{print $1; exit}')"   # 맨 끝 REJECT 바로 앞
    iptables -I INPUT "${pos:-1}" -p tcp -s "$c" --dport 5432 -m state --state NEW -j ACCEPT
  done
  command -v netfilter-persistent >/dev/null 2>&1 && netfilter-persistent save || iptables-save > /etc/iptables/rules.v4
  echo "iptables: $(iptables -S INPUT | grep -c -- '--dport 5432') 규칙"
fi

echo
echo "끝. 남은 것(오너 · OCI 콘솔): VCN › 보안 목록(또는 NSG) 수신 규칙에 TCP 5432 · 원본 = 위 Render CIDR 각각(0.0.0.0/0 금지)."
echo "연결 문자열 모양(비밀번호는 $PASS_FILE): postgresql://$DB_USER:<비밀번호>@<A1 공인 IP>:5432/$DB_NAME?sslmode=require"
