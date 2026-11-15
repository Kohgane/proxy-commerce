"""감독 11-15 kg-a1 실행 결과 — 버그 2건.

1. 윈도우 clone이면 .sh가 CRLF → `set: pipefail` 실패 → `.gitattributes`에 *.sh·*.sql(+systemd 유닛) eol=lf
2. setup_pg16.sh 6단계가 제목만 찍고 iptables 규칙을 안 넣음 — `set -euo pipefail` 아래 「맞는 줄 없음」 grep(1)이 파이프를
   실패시켜 조용히 종료. → `firewall_5432.sh`(함수) + **넣은 뒤 검증**(규칙 존재 · 첫 REJECT 앞 · rules.v4 저장), 빠지면 실패.

가짜 iptables(상태 파일)로 OCI 우분투 기본 INPUT(맨 끝 REJECT)을 흉내 낸다.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import textwrap

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
A1 = os.path.join(ROOT, "ops", "oracle_a1")
CIDRS = ["74.220.52.0/24", "74.220.60.0/24"]

OCI_BASE = [
    "-m state --state RELATED,ESTABLISHED -j ACCEPT",
    "-p icmp -j ACCEPT",
    "-i lo -j ACCEPT",
    "-p udp -m udp --sport 123 -j ACCEPT",
    "-p tcp -m state --state NEW -m tcp --dport 22 -j ACCEPT",
    "-j REJECT --reject-with icmp-host-prohibited",
]

FAKE_IPTABLES = textwrap.dedent(r'''
    import json, os, sys
    st = os.environ["FAKE_IPT_STATE"]
    rules = json.load(open(st))

    def canon(tok):
        if "-s" not in tok:
            return " ".join(tok)
        d = dict(zip(tok[::1], tok[1::1]))
        out = ["-s", d["-s"], "-p", d.get("-p", "all")]
        if "--state" in tok:
            out += ["-m", "state", "--state", d["--state"]]
        if "--dport" in tok:
            out += ["-m", "tcp", "--dport", d["--dport"]]
        return " ".join(out + ["-j", d["-j"]])

    a = sys.argv[1:]
    if os.path.basename(sys.argv[0]) == "iptables-save":
        print("*filter")
        for r in rules:
            print("-A INPUT " + r)
        print("COMMIT")
        sys.exit(0)
    op = a[0]
    if op == "-S":
        print("-P INPUT ACCEPT")
        for r in rules:
            print("-A INPUT " + r)
        sys.exit(0)
    if op == "-D":
        c = canon(a[2:])
        if c not in rules:
            sys.exit(1)
        rules.remove(c)
    elif op == "-I":
        if os.environ.get("FAKE_IPT_BROKEN") == "1":
            sys.exit(0)                                  # 「성공」이라 말하고 아무것도 안 넣는다
        pos, c = int(a[2]), canon(a[3:])
        if os.environ.get("FAKE_IPT_APPEND") == "1":
            rules.append(c)                              # REJECT 뒤로 가 버리는 경우
        else:
            rules.insert(pos - 1, c)
    elif op == "-C":
        sys.exit(0 if canon(a[2:]) in rules else 1)
    json.dump(rules, open(st, "w"))
''')


@pytest.fixture
def fw(tmp_path):
    if not shutil.which("bash"):
        pytest.skip("bash 없음")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("bash", "grep", "awk", "sed", "tr", "sort", "dirname", "mkdir", "cat", "readlink"):
        p = shutil.which(name)
        assert p, name
        os.symlink(p, bin_dir / name)
    shim = tmp_path / "fake_iptables.py"
    shim.write_text(FAKE_IPTABLES)
    for name in ("iptables", "iptables-save"):
        f = bin_dir / name
        f.write_text(f'#!{sys.executable}\nimport sys; sys.argv[0] = "{name}"\nexec(open("{shim}").read())\n')
        f.chmod(0o755)
    ufw = bin_dir / "ufw"                                    # CI 러너에 ufw가 있어도 결과가 같게 — 꺼진 ufw
    ufw.write_text("#!/bin/sh\necho 'Status: inactive'\n")
    ufw.chmod(0o755)
    state = tmp_path / "state.json"

    def run(rules, **env):
        state.write_text(json.dumps(rules))
        e = {"PATH": str(bin_dir), "FAKE_IPT_STATE": str(state), "RULES_V4": str(tmp_path / "rules.v4"), **env}
        cmd = f'set -euo pipefail; . "{A1}/firewall_5432.sh"; kgp_fw_5432 {" ".join(CIDRS)}; echo DONE'
        p = subprocess.run(["bash", "-c", cmd], env=e, capture_output=True, text=True, timeout=60)
        saved = (tmp_path / "rules.v4").read_text() if (tmp_path / "rules.v4").exists() else ""
        return p, json.loads(state.read_text()), saved
    return run


def _pos(rules, cidr):
    return next(i for i, r in enumerate(rules) if f"-s {cidr} " in r and "--dport 5432" in r)


def test_fresh_oci_host_gets_both_rules_before_reject_and_saved(fw):
    p, rules, saved = fw(list(OCI_BASE))
    assert p.returncode == 0, p.stderr
    assert "DONE" in p.stdout and p.stdout.count("✔") == 2               # 예전엔 제목만 찍고 여기 못 왔다
    rej = next(i for i, r in enumerate(rules) if "-j REJECT" in r)
    assert all(_pos(rules, c) < rej for c in CIDRS)
    assert all(f"-s {c} " in saved for c in CIDRS) and saved.count("--dport 5432") == 2


def test_rerun_over_owners_manual_rule_is_idempotent(fw):
    manual = ["-s 74.220.52.0/24 -p tcp -m tcp --dport 5432 -j ACCEPT",
              "-s 74.220.60.0/24 -p tcp -m tcp --dport 5432 -j ACCEPT"]   # 오너가 INPUT 1번에 손으로 넣은 것
    p, rules, _ = fw(manual + OCI_BASE)
    assert p.returncode == 0, p.stderr
    assert sum("--dport 5432" in r for r in rules) == 2                 # 중복 0
    p2, rules2, _ = fw(rules)
    assert p2.returncode == 0 and rules2 == rules


def test_insert_that_silently_does_nothing_fails_loudly(fw):
    p, rules, _ = fw(list(OCI_BASE), FAKE_IPT_BROKEN="1")
    assert p.returncode != 0 and "DONE" not in p.stdout
    assert "규칙이 없어요" in p.stderr and "6단계 실패" in p.stderr
    assert not any("--dport 5432" in r for r in rules)


def test_rule_landing_after_reject_fails(fw):
    p, _, _ = fw(list(OCI_BASE), FAKE_IPT_APPEND="1")
    assert p.returncode != 0 and "REJECT" in p.stderr and "앞이 아니에요" in p.stderr


def test_setup_script_uses_the_verified_function():
    s = open(os.path.join(A1, "setup_pg16.sh"), encoding="utf-8").read()
    assert "firewall_5432.sh" in s and 'kgp_fw_5432 "${CIDRS[@]}"' in s
    assert "iptables -I" not in s                                       # 검증 없는 예전 길이 남지 않게
    f = open(os.path.join(A1, "firewall_5432.sh"), encoding="utf-8").read()
    for line in f.splitlines():                                          # 「없을 수도 있는」 grep은 파이프 안에서 || true
        if "| grep" in line and "while" in line:
            assert "|| true" in line, line


def test_gitattributes_forces_lf_for_shell_and_sql():
    ga = open(os.path.join(ROOT, ".gitattributes"), encoding="utf-8").read()
    for rule in ("*.sh text eol=lf", "*.sql text eol=lf", "fixtures/realpages/** -text"):
        assert rule in ga
    if shutil.which("git"):
        out = subprocess.run(["git", "check-attr", "eol", "--", "ops/oracle_a1/setup_pg16.sh",
                              "ops/oracle_a1/firewall_5432.sh", "src/db/schema_stage20.sql"],
                             cwd=ROOT, capture_output=True, text=True).stdout
        assert out.count("eol: lf") == 3, out
