# ops/oracle_a1/firewall_5432.sh — setup_pg16.sh 6단계(호스트 방화벽)를 함수로. `source` 해서 쓴다.
#
# 감독 11-15 kg-a1 실행: 6단계가 제목만 찍고 규칙을 안 넣고 끝났다. 원인 = `set -euo pipefail` 아래에서
#   `iptables -S INPUT | grep -- '--dport 5432'`가 **처음엔 맞는 줄이 없어 grep이 1** → 파이프 전체 실패 → 스크립트가 조용히 종료.
#   → 「없을 수도 있는」 grep은 전부 `|| true`로 감싸고, 넣은 뒤 **실제로 들어갔는지 검증** — 하나라도 빠지면 실패(return 1).
#
# 검증(iptables 길): 대역마다 ① `iptables -C`로 규칙 존재 ② INPUT에서 첫 REJECT **앞**에 있음(OCI 우분투는 맨 끝 REJECT라
#   그 뒤 규칙은 효과 없음) ③ 저장 파일(RULES_V4, 기본 /etc/iptables/rules.v4)에도 있음 — 재부팅 뒤 사라지지 않게.
# 순서 판정은 `iptables -S`(줄 순서 = 규칙 순서)로 한다 — `-L -n`의 칸 배치는 iptables 버전마다 달라 쓰지 않는다.

KGP_FW_RULE_ARGS=(-p tcp --dport 5432 -m state --state NEW -j ACCEPT)

_kgp_fw_trim() { echo "$1" | tr -d ' \r'; }

# INPUT 규칙(-A 줄)만, 순서대로
_kgp_fw_input_rules() { { iptables -S INPUT 2>/dev/null || true; } | { grep '^-A INPUT ' || true; }; }

# 첫 REJECT/DROP 규칙 번호(1부터) — 없으면 빈 값
_kgp_fw_first_reject() { _kgp_fw_input_rules | awk '/ -j (REJECT|DROP)( |$)/ {print NR; exit}'; }

# 그 대역의 5432 ACCEPT 규칙 번호 — 없으면 빈 값
_kgp_fw_rule_pos() {
  _kgp_fw_input_rules | awk -v s="-s $1 " '
    index($0 " ", s) && / --dport 5432( |$)/ && / -j ACCEPT( |$)/ {print NR; exit}'
}

kgp_fw_iptables_5432() {   # 쓰는 법: kgp_fw_iptables_5432 74.220.52.0/24 74.220.60.0/24
  local c rule pos rej n missing=0
  local rules_v4="${RULES_V4:-/etc/iptables/rules.v4}"
  # 예전 5432 규칙은 지우고 다시(멱등). 처음이면 지울 게 없다 — grep 1은 정상.
  { iptables -S INPUT | grep -- '--dport 5432' || true; } | sed 's/^-A/-D/' | while read -r rule; do
    # shellcheck disable=SC2086
    iptables $rule || true
  done
  for c in "$@"; do
    c="$(_kgp_fw_trim "$c")"; [ -n "$c" ] || continue
    pos="$(_kgp_fw_first_reject)"                                      # 첫 REJECT 바로 앞(없으면 맨 앞)
    iptables -I INPUT "${pos:-1}" -s "$c" "${KGP_FW_RULE_ARGS[@]}" \
      || echo "실패: iptables -I 명령이 오류로 끝났어요($c) — 아래 검증에서 다시 봐요" >&2
  done
  if command -v netfilter-persistent >/dev/null 2>&1; then
    netfilter-persistent save >/dev/null 2>&1 || true
  fi
  if ! { [ -f "$rules_v4" ] && grep -q -- '--dport 5432' "$rules_v4"; }; then  # netfilter-persistent가 없거나 저장 못 했으면 직접
    mkdir -p "$(dirname "$rules_v4")"
    iptables-save > "$rules_v4"
  fi
  # ── 검증: 하나라도 빠지면 실패
  rej="$(_kgp_fw_first_reject)"
  for c in "$@"; do
    c="$(_kgp_fw_trim "$c")"; [ -n "$c" ] || continue
    if ! iptables -C INPUT -s "$c" "${KGP_FW_RULE_ARGS[@]}" 2>/dev/null; then
      echo "실패: iptables INPUT에 $c → 5432 규칙이 없어요" >&2; missing=1; continue
    fi
    n="$(_kgp_fw_rule_pos "$c")"
    if [ -z "$n" ] || { [ -n "$rej" ] && [ "$n" -ge "$rej" ]; }; then
      echo "실패: $c → 5432 규칙(${n:-?}번)이 REJECT(${rej}번) 앞이 아니에요 — 효과 없음" >&2; missing=1; continue
    fi
    if ! grep -- "-s $c " "$rules_v4" 2>/dev/null | grep -q -- '--dport 5432'; then
      echo "실패: $rules_v4 에 $c → 5432 규칙이 저장되지 않았어요(재부팅하면 사라짐)" >&2; missing=1; continue
    fi
    echo "  ✔ $c → 5432 (INPUT ${n}번 · REJECT ${rej:-없음}번 앞 · $rules_v4 저장)"
  done
  [ "$missing" = 0 ] || { echo "6단계 실패 — 방화벽 규칙을 넣지 못했어요. 위 줄을 보고 고친 뒤 다시 돌려 주세요." >&2; return 1; }
}

kgp_fw_ufw_5432() {        # ufw가 켜져 있으면 같은 대역을 ufw에도(OCI 우분투는 iptables가 실제 문 — 위 함수)
  local c n missing=0
  command -v ufw >/dev/null 2>&1 || return 0
  if [ "${KGP_UFW_ENABLE:-0}" = 1 ] && ! ufw status | grep -q "Status: active"; then
    ufw allow 22/tcp >/dev/null && ufw --force enable >/dev/null
  fi
  if ! ufw status | grep -q "Status: active"; then
    echo "ufw: 꺼져 있음 — iptables 규칙이 문(OCI 기본). 켜려면 KGP_UFW_ENABLE=1"
    return 0
  fi
  { ufw status numbered | grep ' 5432/tcp' || true; } | { grep -o '^\[ *[0-9]*\]' || true; } | tr -d '[] ' | sort -rn \
    | while read -r n; do ufw --force delete "$n" >/dev/null || true; done
  for c in "$@"; do
    c="$(_kgp_fw_trim "$c")"; [ -n "$c" ] || continue
    ufw allow from "$c" to any port 5432 proto tcp >/dev/null
  done
  for c in "$@"; do
    c="$(_kgp_fw_trim "$c")"; [ -n "$c" ] || continue
    if ! ufw status | grep -F "$c" | grep -q '5432/tcp'; then
      echo "실패: ufw에 $c → 5432 규칙이 없어요" >&2; missing=1
    fi
  done
  [ "$missing" = 0 ] || return 1
  echo "ufw: 5432 규칙 $(ufw status | grep -c '5432/tcp')개"
}

kgp_fw_firewalld_5432() {
  local c rule missing=0
  { firewall-cmd --permanent --list-rich-rules | grep 'port="5432"' || true; } | while read -r rule; do
    firewall-cmd --permanent --remove-rich-rule="$rule" >/dev/null || true
  done
  for c in "$@"; do
    c="$(_kgp_fw_trim "$c")"; [ -n "$c" ] || continue
    firewall-cmd --permanent --add-rich-rule="rule family=\"ipv4\" source address=\"$c\" port port=\"5432\" protocol=\"tcp\" accept" >/dev/null
  done
  firewall-cmd --reload >/dev/null
  for c in "$@"; do
    c="$(_kgp_fw_trim "$c")"; [ -n "$c" ] || continue
    if ! firewall-cmd --list-rich-rules | grep -F "source address=\"$c\"" | grep -q 'port="5432"'; then
      echo "실패: firewalld에 $c → 5432 규칙이 없어요" >&2; missing=1
    fi
  done
  [ "$missing" = 0 ] || { echo "6단계 실패 — firewalld 규칙을 넣지 못했어요." >&2; return 1; }
  echo "firewalld: 5432 규칙 $(firewall-cmd --list-rich-rules | grep -c 5432)개"
}

kgp_fw_5432() {            # setup_pg16.sh 6단계 진입점
  if command -v firewall-cmd >/dev/null 2>&1 && systemctl is-active --quiet firewalld 2>/dev/null; then
    kgp_fw_firewalld_5432 "$@"
  else
    kgp_fw_iptables_5432 "$@"
    kgp_fw_ufw_5432 "$@"
  fi
}
