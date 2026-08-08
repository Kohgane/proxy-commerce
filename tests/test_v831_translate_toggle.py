"""tests/test_v831_translate_toggle.py — v83.1 STEP1-2: 한국어 번역 토글 · 게이트 보조(빌드 각인·CI 아티팩트).

STEP1 번역 토글: 팝업·인페이지 수집 카드 양쪽에 '한국어 번역' 토글(기본 ON, chrome.storage.local.kgp_translate
  단일 키 + onChanged 양방향 동기). OFF면 background가 수집 페이로드에 translate:false를 실어 서버 번역 파이프라인을
  건너뛴다 — **원문은 토글과 무관하게 항상 전송·보존**되고 번역본(title_ko 등)만 파생으로 빠진다.
  FAB 부제·title, 카드 문구가 상태에 동기(거짓 라벨 금지: OFF인데 "번역까지 한 번에" 표기 0).
  ※ 이 토글은 '우리' 번역 기능 제어다. 구글 번역 DOM 오염(translated_dom) 무효화 로직(v83 STEP1)과는 별개 — 둘 다 유지.

STEP2 게이트 보조: 확장 ZIP 패키징 단일 소스(src/build_extension.py)로 서버 다운로드·CI 아티팩트·build.sh를 통일하고
  ZIP에 build-info.json(커밋 해시) 각인 → 확장 진단 파일이 git_commit을 실어 '브랜치 빌드 여부'를 커밋 단위로 즉판.
"""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from src.build_extension import INCLUDE_FILES, build_info, build_zip_bytes, resolve_commit

EXT = Path("extensions/chrome-collector")
BG = (EXT / "background.js").read_text(encoding="utf-8")
CS = (EXT / "content_script.js").read_text(encoding="utf-8")
POPUP_JS = (EXT / "popup.js").read_text(encoding="utf-8")
POPUP_HTML = (EXT / "popup.html").read_text(encoding="utf-8")
MANIFEST = json.loads((EXT / "manifest.json").read_text(encoding="utf-8"))


def test_manifest_bumped():
    # 오너가 재로딩해야 토글이 보인다 → 버전 bump가 곧 배포 신호.
    assert MANIFEST["version"] == "1.5.139"


# ── STEP1: 번역 토글 ─────────────────────────────────────────────────────
def test_toggle_present_in_both_surfaces():
    # 팝업.
    assert 'id="translateToggle"' in POPUP_HTML and "한국어 번역" in POPUP_HTML
    assert "kgp_translate" in POPUP_JS
    # 인페이지 수집 카드.
    assert "kgp-cc-translate" in CS and "kgp-cc-opt" in CS
    assert "function kgpRenderCardTranslate(" in CS


def test_default_on_and_single_storage_key():
    # 기본 ON = "=== false일 때만 끈다" 형태(키 없으면 ON).
    assert "!(localData.kgp_translate === false)" in BG
    assert "!(r && r.kgp_translate === false)" in POPUP_JS
    assert "!(r && r.kgp_translate === false)" in CS
    # 두 표면이 같은 키를 쓴다(단일 소스) — 다른 키를 새로 만들지 않았는지.
    for src in (BG, CS, POPUP_JS):
        assert "kgp_translate" in src


def test_bidirectional_sync_via_onchanged():
    # 카드에서 끄면 팝업이, 팝업에서 끄면 카드·FAB 문구가 따라온다.
    assert "changes.kgp_translate" in POPUP_JS
    assert "changes.kgp_translate" in CS
    assert "kgpApplyTranslateCopy();" in CS and "kgpRenderCardTranslate();" in CS


def test_payload_flag_single_gate():
    # 주입 지점이 하나(_kgpWithTranslateFlag) — 단일/벌크 두 전송 경로가 모두 통과.
    assert "function _kgpWithTranslateFlag(" in BG
    assert BG.count("_kgpWithTranslateFlag(meta, settings.translate)") == 2
    # 원문(meta)을 지우지 않는다 — translate 플래그만 덧씌운다(원문 보존 계약).
    assert "Object.assign({}, meta, { translate: false })" in BG
    assert "delete meta.title" not in BG and "meta.title = \"\"" not in BG
    # ON일 때는 페이로드 무변경(서버 기본값 true).
    assert "if (translate !== false) return meta;" in BG


def test_copy_matches_state_no_false_label():
    # OFF인데 "번역까지 한 번에"라고 말하지 않는다(거짓 라벨 금지).
    assert "function kgpApplyTranslateCopy(" in CS
    assert '"고가브릿지로 수집 (한국어 번역 포함)" : "고가브릿지로 수집 (원문 그대로)"' in CS
    assert '"번역까지 한 번에" : "원문 그대로 수집"' in CS
    # 부제가 하드코딩 문자열로 남아 있지 않다(상태와 무관하게 고정되던 옛 라벨 제거).
    assert ">번역까지 한 번에</span>" not in CS
    # 결과 문구는 **서버가 확인한** translated만 근거로 삼는다(가짜 '번역됨' 금지).
    assert "resp.translated ?" in CS and "한국어 번역 완료" in CS


def test_google_translate_dom_logic_untouched():
    # v83 STEP1(구글 번역 DOM 무효화)은 이 토글과 별개 — 그대로 살아 있어야 한다.
    ex = (EXT / "kgp-extractor.js").read_text(encoding="utf-8")
    assert "function _translatedDom(" in ex
    assert "_localeCurrency({ ignoreLang: translatedDom })" in ex
    assert "번역된 페이지 — 원문 기준으로 저장했어요" in CS


# ── STEP2: 게이트 보조(빌드 각인 · 패키징 단일 소스) ──────────────────────
def test_zip_contains_every_declared_script():
    """설치 즉시 깨지는 누락 방지 — manifest가 선언한 스크립트가 ZIP에 전부 있어야 한다.

    회귀 근원: 옛 서버 include 목록엔 kgp-sources.js가, build.sh엔 kgp-*.js 5개가 빠져 있었다.
    """
    data, fname, info = build_zip_bytes()
    z = zipfile.ZipFile(io.BytesIO(data))
    names = set(z.namelist())
    mani = json.loads(z.read("manifest.json"))
    need = {j for cs in mani.get("content_scripts", []) for j in cs.get("js", [])}
    sw = (mani.get("background") or {}).get("service_worker") or ""
    if sw:
        need.add(sw)
    missing = sorted(n for n in need if n not in names)
    assert not missing, f"ZIP에 manifest 선언 스크립트 누락: {missing}"
    assert fname == f"gogasujipgi-v{mani['version']}.zip"
    # 아이콘도 함께(툴바 아이콘 없는 확장 방지).
    assert any(n.startswith("icons/") for n in names)


def test_build_info_stamped_in_zip():
    data, _fname, info = build_zip_bytes()
    z = zipfile.ZipFile(io.BytesIO(data))
    stamped = json.loads(z.read("build-info.json"))
    assert stamped["version"] == MANIFEST["version"]
    assert set(stamped) >= {"version", "commit", "commit_short", "branch", "source", "built_at"}
    # 이 리포는 git 워킹트리이므로 커밋이 잡혀야 한다(CI는 GITHUB_SHA).
    assert stamped["commit"], "커밋 각인 실패"
    assert stamped["commit_short"] == stamped["commit"][:7]
    assert stamped["source"] in {"ci", "render", "env", "git"}


def test_build_info_honest_when_commit_unknown(monkeypatch, tmp_path):
    """커밋을 못 구하면 가짜 해시 대신 빈 값 + source='unknown'(정직)."""
    for k in ("GITHUB_SHA", "RENDER_GIT_COMMIT", "KGP_BUILD_COMMIT"):
        monkeypatch.delenv(k, raising=False)
    info = build_info(tmp_path, "9.9.9")   # git 워킹트리가 아닌 빈 디렉토리
    assert info["commit"] == "" and info["commit_short"] == ""
    assert info["source"] == "unknown"
    commit, source = resolve_commit(tmp_path)
    assert commit == "" and source == "unknown"


def test_commit_env_precedence(monkeypatch, tmp_path):
    """명시 오버라이드가 1순위 — PR의 GITHUB_SHA(머지 커밋)보다 브랜치 head SHA가 이겨야 한다."""
    for k in ("KGP_BUILD_COMMIT", "GITHUB_SHA", "RENDER_GIT_COMMIT", "GITHUB_ACTIONS"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("GITHUB_SHA", "a" * 40)
    assert resolve_commit(tmp_path) == ("a" * 40, "ci")
    monkeypatch.setenv("KGP_BUILD_COMMIT", "c" * 40)   # 머지 커밋(GITHUB_SHA) 위에 head SHA
    assert resolve_commit(tmp_path) == ("c" * 40, "env")
    monkeypatch.setenv("GITHUB_ACTIONS", "true")       # CI 안이면 출처 표기는 'ci'
    assert resolve_commit(tmp_path) == ("c" * 40, "ci")
    monkeypatch.delenv("KGP_BUILD_COMMIT")
    monkeypatch.delenv("GITHUB_SHA")
    monkeypatch.setenv("RENDER_GIT_COMMIT", "b" * 40)
    assert resolve_commit(tmp_path) == ("b" * 40, "render")


def test_ci_stamps_branch_head_not_merge_commit():
    """GITHUB_* 는 예약 이름이라 워크플로에서 덮어써도 무시된다 → 전용 키로 넘겨야 한다(실패 재발 방지)."""
    ci = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "KGP_BUILD_COMMIT: ${{ github.event.pull_request.head.sha || github.sha }}" in ci
    assert "KGP_BUILD_BRANCH: ${{ github.head_ref || github.ref_name }}" in ci
    # 예약 이름 덮어쓰기(무시되는 설정)로 되돌아가지 않게 못박음.
    assert "GITHUB_SHA:" not in ci and "GITHUB_REF_NAME:" not in ci


def test_diag_bundle_reports_commit():
    # 진단 파일이 ext_version과 **별개로** git_commit을 싣는다(브랜치 빌드 여부 즉판).
    assert '{ action: "kgpBuildInfo" }' in CS
    assert "git_commit:" in CS
    assert 'msg.action === "kgpBuildInfo"' in BG
    assert "function _kgpBuildInfo(" in BG
    assert 'chrome.runtime.getURL("build-info.json")' in BG
    # 개발 설치(소스 폴더 로드)는 파일이 없다 → 정직 표기.
    assert 'source: "unpacked-dev"' in BG


def test_packaging_single_source_no_drift():
    views = Path("src/seller_console/views.py").read_text(encoding="utf-8")
    build_sh = (EXT / "build.sh").read_text(encoding="utf-8")
    # 서버 라우트·build.sh 모두 단일 소스 경유(각자 파일 목록 보유 금지).
    assert "from src.build_extension import build_zip_bytes" in views
    assert "build_extension_zip.py" in build_sh
    assert "zip -r" not in build_sh
    # 파일 목록은 build_extension 한 곳에만.
    assert "kgp-sources.js" in INCLUDE_FILES and "kgp-extractor.js" in INCLUDE_FILES
    # 로직이 src/에 있어야 배포 이미지(Dockerfile이 scripts/ 전체를 COPY하지 않음)에서 살아 있다.
    assert Path("src/build_extension.py").exists()
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
    assert "COPY src/" in dockerfile


def test_ci_publishes_extension_artifact():
    ci = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "extension-zip:" in ci
    assert "actions/upload-artifact" in ci
    assert "scripts/build_extension_zip.py" in ci
    # 아티팩트를 뽑기만 하지 않고 **검증**한다(선언 스크립트 누락·커밋 각인 없음 → CI 실패).
    assert "manifest 선언 스크립트 누락" in ci
    assert "커밋 각인 없음" in ci
