"""tests/test_v40s6l_class_home.py — 우리가 쓴 클래스에 집이 있는가.

**잔재 계약은 "있으면 안 되는 것"만 본다.** v2 클래스가 사라졌는지는 세어도,
그 자리에 들어간 새 이름이 **실제로 어딘가에 닿는지는 아무도 안 봤다.**
그 차집합에서 6-l이 이렇게 무너졌다(실측 2026-09-11):

* `pc-badge-muted`를 `pc-pc-badge-muted`로 적었다 — **13곳.** 정의가 없으니 아무 규칙도 안 걸리고,
  DRY_RUN 뱃지가 **알약이 아니라 맨 텍스트**로 떴다. 잔재 계약은 초록이었다(v2 클래스는 실제로 없으니까).
* `bg-light`(배경 유틸)를 `pc-badge-muted`(뱃지 변형)로 치환했다 — 표 셀·인용 블록·토스트가
  **뱃지 옷을 입었다.** 특히 토스트는 `btn-close-white`가 밝은 배경에 얹혀 **닫기 버튼이 사라졌다.**
* `pc-status-warn`(정본은 `-warning`) 1곳 — 경고 상자가 조용히 기본색으로 떴다.
* 규칙 없는 이름 8개가 sourcing.html에 살아 있었다 — **내가 6-i에서 쓴 것들이다.**
  6-k가 `.console-account`에서 잡은 것과 같은 유형: 이름이 있는데 집이 없으면,
  다음 사람은 그 이름을 믿고 쓰다가 아무 일도 안 일어나는 걸 본다.

두 가지를 본다.

**① 우리 네임스페이스 클래스는 CSS 규칙이 있거나 JS 훅이어야 한다.**
   둘 다 아니면 그 이름은 화면에 아무 일도 안 한다 — 오타이거나 유령이다.

**② 변형은 기본형과 함께 온다.** `pc-badge-on`은 `pc-badge` 없이는 색만 있고 알약이 아니고,
   `pc-status-info`는 `pc-status` 없이는 상자가 아니다. 그리고 **뱃지 변형은 뱃지에만** 붙는다.
"""
from __future__ import annotations

import re
from pathlib import Path

TPL = Path("src/seller_console/templates")
CSS_FILES = (Path("src/static/app.css"),
             Path("src/seller_console/static/console.css"),
             Path("src/seller_console/static/seller.css"))
JS_FILES = (Path("src/seller_console/static/seller.js"),)

# 우리가 소유한 접두어만 본다 — 부트스트랩 유틸은 이 계약의 일이 아니다.
OURS = ("pc-", "op-", "ch-", "mk-", "od-", "mc-", "ct-", "rw-", "si-", "kgp-", "fb-", "console-")


def _decl(p: Path) -> str:
    return re.sub(r"/\*.*?\*/", "", p.read_text(encoding="utf-8"), flags=re.S)


def _defined() -> set[str]:
    css = "".join(_decl(p) for p in CSS_FILES)
    return set(re.findall(r"\.([a-zA-Z][\w-]*)", css))


def _hooks() -> str:
    """규칙이 없어도 **제 일을 하는** 이름들.

    ① JS가 선택자·className 문자열로 잡는 것.
    ② **계약이 짚는 표식** — `tests/`가 `index("mc-note-coupang")`처럼 위치를 잡는 데 쓰는 이름.
       이걸 빼먹고 "죽은 이름"이라며 지웠다가 남의 계약을 빨갛게 만들었다(실측 2026-09-11).
       화면에 색을 안 입혀도, 누군가 그 이름으로 자리를 찾고 있으면 그건 살아 있는 이름이다.
    """
    blob = "".join(p.read_text(encoding="utf-8") for p in JS_FILES)
    for p in sorted(TPL.glob("*.html")):
        blob += "\n".join(re.findall(r"<script[^>]*>(.*?)</script>",
                                     p.read_text(encoding="utf-8"), re.S))
    for p in sorted(Path("tests").glob("*.py")):
        blob += p.read_text(encoding="utf-8", errors="ignore")
    return blob


def _classes(html: str):
    """`class="..."` 안의 토큰.

    Jinja 표현식 조각(`{%`·`{{`)은 이름이 아니라 제어문이라 뺀다. 다만 **표현식 안의 이름은 뺄 수 없다** —
    `{{ ' pc-lc-dot--on' if on }}`처럼 조건부로 붙는 클래스도 화면에 나오니까(6-j-2가 배운 것:
    계약이 안 보는 만큼 그린은 거짓이다). 대신 그 이름을 감싼 **따옴표는 이름의 일부가 아니다** —
    안 벗기면 `pc-lc-dot--on'`이 미정의로 잡혀 거짓 경보가 난다(실제로 그랬다).

    같은 이유로 **괄호도 벗긴다** — 중첩 삼항(`('pc-a' if x else 'pc-b')`)을 쓰면 마지막 토큰이
    `pc-b')`로 잡혀 거짓 경보가 났다(실측 2026-09-12, C-F9의 링크 진단 화면).
    벗기면 진짜 이름이 드러나고 그 이름이 그대로 검사된다 — 느슨해지는 게 아니라 정확해진다.
    """
    for m in re.finditer(r'class="([^"]*)"', html):
        for tok in re.split(r"[\s]+", m.group(1)):
            tok = tok.strip("'\"()")
            if tok and "{" not in tok and "}" not in tok and "%" not in tok:
                yield m.group(1), tok


def test_every_class_we_write_has_a_home():
    """★ 이름을 적었는데 규칙도 훅도 없으면, 그 이름은 **화면에서 아무 일도 안 한다.**"""
    defined, hooks = _defined(), _hooks()
    orphans = []
    for p in sorted(TPL.glob("*.html")):
        html = re.sub(r"\{#.*?#\}|<!--.*?-->", "", p.read_text(encoding="utf-8"), flags=re.S)
        for _, tok in _classes(html):
            if tok.startswith(OURS) and tok not in defined and f"{tok}" not in hooks:
                orphans.append(f"{p.name}:{tok}")
    assert not orphans, f"규칙도 JS 훅도 없는 이름(화면에 아무 일도 안 한다): {sorted(set(orphans))}"


def test_standalone_pages_do_not_borrow_app_css_grammar():
    """★ app.css를 **안 싣는** 페이지에 전역 문법을 쓰면 아무 규칙도 안 걸린다.

    실측: `bookmarklet_testpage.html`은 외부 쇼핑몰을 흉내 내는 **독립 페이지**라
    app.css를 일부러 안 싣고 `<style>`에 제 `.card`를 갖고 있다. 기계 치환이 그 마크업을
    `op-card`로 바꿔 놨는데, 로컬 규칙은 여전히 `.card`였다 — **카드가 통째로 벗겨졌다.**
    `op-card`는 app.css에 정의돼 있으니 "집이 있나" 검사로는 절대 안 잡힌다.
    """
    bad = []
    for p in sorted(TPL.glob("*.html")):
        html = p.read_text(encoding="utf-8")
        if "app.css" in html or 'extends "_base' in html or "<!DOCTYPE" not in html:
            continue                      # 전역 CSS를 타는 페이지는 이 계약의 일이 아니다
        local = set(re.findall(r"\.([a-zA-Z][\w-]*)", "".join(
            re.findall(r"<style[^>]*>(.*?)</style>", html, re.S))))
        for _, tok in _classes(re.sub(r"<style.*?</style>", "", html, flags=re.S)):
            if tok.startswith(OURS) and tok not in local:
                bad.append(f"{p.name}:{tok}")
    assert not bad, f"독립 페이지가 전역 문법을 빌려 썼다(그 규칙은 여기 없다): {sorted(set(bad))}"


def test_variants_come_with_their_base():
    """★ 변형만 붙이면 색은 와도 **형태가 안 온다** — 알약이 알약이 아니게 된다."""
    bad = []
    for p in sorted(TPL.glob("*.html")):
        html = re.sub(r"\{#.*?#\}|<!--.*?-->", "", p.read_text(encoding="utf-8"), flags=re.S)
        for attr, tok in _classes(html):
            for base in ("pc-badge", "pc-status"):
                if tok.startswith(base + "-") and base not in re.split(r"[\s{}%]+", attr):
                    bad.append(f"{p.name}:{tok}")
    assert not bad, f"기본형 없이 변형만 붙었다: {sorted(set(bad))}"


def test_badge_variants_are_only_on_badges():
    """★ 배경이 필요하다고 뱃지 변형을 블록에 붙이지 않는다.

    실측: 표 셀·인용 블록·토스트가 `pc-badge-muted`를 입고 **알약이 블록을 삼켰다.**
    조용한 블록의 정본은 `.pc-inset`이다.
    """
    bad = []
    for p in sorted(TPL.glob("*.html")):
        html = re.sub(r"\{#.*?#\}|<!--.*?-->", "", p.read_text(encoding="utf-8"), flags=re.S)
        for attr, tok in _classes(html):
            if not tok.startswith("pc-badge-"):
                continue
            toks = set(re.split(r"[\s{}%]+", attr))
            # 블록 조판·구조 클래스와 한 자리에 있으면 그건 알약이 아니다.
            # `border`·`rounded`는 **뺀다** — 테두리 있는 칩은 정상이다(실측: api_status의 env 칩을
            # 거짓 양성으로 잡았다). 알약과 블록을 가르는 건 테두리가 아니라 **여백과 구조**다.
            if toks & {"p-2", "p-3", "p-4", "toast", "op-card-head", "op-card-body", "col-12"}:
                bad.append(f"{p.name}:{attr.strip()[:60]}")
    assert not bad, f"뱃지가 아닌 것에 뱃지 변형이 붙었다(`pc-inset`이 그 자리다): {bad}"


# ─────────────────────────────────────────────────────────────────────────────
# Stage 6 잔재 래칫 (실측 2026-09-12) — 0이 아니라 **늘지 않음**을 지킨다
# ─────────────────────────────────────────────────────────────────────────────

# v2(부트스트랩) 문법 토큰 — 우리 `op-*`/`pc-*`가 대신하기로 한 것들.
#   `card`·`badge`·`alert`는 우리 CSS에 **홈이 없다**(`op-card`·`pc-badge`만 있다) →
#   맨 이름으로 쓰면 부트스트랩 기본으로 떨어진다 = v2 그대로다.
V2_TOKENS = {"card", "badge", "alert"} | {
    f"bg-{x}" for x in ("light", "white", "secondary", "primary",
                        "success", "danger", "warning", "info")}

# 일부러 전역 문법을 안 쓰는 화면 — 외부 쇼핑몰을 흉내 내야 해서 app.css를 안 싣는다
#   (v3 계약 ④). 여기 `card`는 잔재가 아니라 **그 페이지의 자기 클래스**다.
STANDALONE_PAGES = {"bookmarklet_testpage.html"}

# 실측 상한. **내려갈 때만 고친다** — 올리는 커밋은 곧 잔재를 들여온 커밋이다.
V2_RESIDUE_CEILING = 46


def _v2_residue() -> dict:
    """화면별 v2 토큰 수. **토큰 정확 일치**로 센다 — 정규식 `\\b`로 세지 않는다.

    실측 2026-09-12: `\\bcard\\b`로 셌더니 **350건**이 나왔다. `op-card`를 문 것이다
    (`\\b`는 하이픈을 경계로 본다). 볼트 「정규식이 설명문을 선언으로 읽는다」가 적어 둔
    그 함정을, 그 노트를 쓴 세션에서 또 밟았다 — 그래서 세는 방법 자체를 못 박는다.
    """
    out: dict[str, int] = {}
    for p in sorted(TPL.glob("*.html")):
        if p.name in STANDALONE_PAGES:
            continue
        html = re.sub(r"\{#.*?#\}|<!--.*?-->", "", p.read_text(encoding="utf-8"), flags=re.S)
        n = 0
        for attr in re.findall(r'class="([^"]*)"', html):
            for tok in attr.split():
                if tok.strip("'\"()") in V2_TOKENS:
                    n += 1
        if n:
            out[p.name] = n
    return out


def test_v2_residue_never_grows():
    """★★★ Stage 6은 **미종결**이다. 남은 잔재가 **늘지 않는 것**을 지킨다.

    실측 2026-09-12 — 계약 238개가 초록인데 맨 `badge` 45건이 남아 있었다.
    색 있는 `badge bg-success`는 잡았고 **색을 뺀 맨 `badge`는 재는 계약이 없었다**:
    계약이 모집단을 「색이 있느냐」로 좁혀서, 안 재는 것이 결함이 아니라 무(無)가 됐다.

    0을 요구하지 않는 이유: 뱃지마다 의미가 달라 `pc-badge-*` 매핑은 **화면별 판단**이고
    기계 치환하면 색이 뜻을 잃는다. 그래서 지금은 **상한**만 걸어 둔다 —
    새 화면이 v2 문법을 또 들여오는 것만 막고, 줄이는 일은 별 트랙으로 한다.
    """
    residue = _v2_residue()
    total = sum(residue.values())
    assert total <= V2_RESIDUE_CEILING, (
        f"v2 잔재가 늘었다 {total} > {V2_RESIDUE_CEILING}: {residue}\n"
        "새 화면에 맨 card/badge/alert/bg-* 를 쓰지 말고 op-*/pc-* 를 쓸 것.")
    if total < V2_RESIDUE_CEILING:
        raise AssertionError(
            f"잔재가 {total}로 줄었다(상한 {V2_RESIDUE_CEILING}). "
            f"V2_RESIDUE_CEILING을 {total}로 내려 래칫을 조일 것. 남은 곳: {residue}")


def test_the_fake_prefix_from_6l_stays_dead():
    """★★ `pc-pc-*` — 기계 치환이 만든 **규칙 없는 이름**. 다시 들어오면 안 된다.

    실측 선례(6-l): 13곳에 뿌려졌고 뱃지가 맨 텍스트로 떴는데 잔재 계약은 초록이었다.
    """
    bad = {p.name: p.read_text(encoding="utf-8").count("pc-pc-")
           for p in TPL.glob("*.html") if "pc-pc-" in p.read_text(encoding="utf-8")}
    assert not bad, f"접두어가 겹친 가짜 클래스가 돌아왔다: {bad}"
