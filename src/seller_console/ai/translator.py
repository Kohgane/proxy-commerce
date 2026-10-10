"""src/seller_console/ai/translator.py — 상품 번역 + 마켓별 광고 카피 자동 생성 (Phase 130).

번역 프로바이더 **체인**(v87-W7, 순차 폴백 — 하나 실패하면 다음). 기본 순서(R0, 오너 2026-10-01) — 모든 원문 언어 공통:
1. papago    — NCP Papago NMT (NCP_PAPAGO_CLIENT_ID + NCP_PAPAGO_CLIENT_SECRET). 중·일 → 한 1순위.
               하루 글자 상한 PAPAGO_DAILY_CHAR_LIMIT(기본 100,000 · 0=없음)을 넘으면 그날은 건너뛴다.
2. deepl     — DeepL (DEEPL_API_KEY). 번역만, 카피는 template
3. azure     — Azure Translator (AZURE_TRANSLATOR_KEY + AZURE_TRANSLATOR_REGION). 소스 자동감지
4. openai    — GPT (OPENAI_API_KEY + OPENAI_MODEL=gpt-4o-mini). 번역 + 카피. 서버 월 예산(AI_MONTHLY_BUDGET_USD)에 묶임
5. mymemory  — 무키·무가입 무료, 마지막(TRANSLATE_DISABLE_MYMEMORY=1로 차단)
전부 실패/키 전무 → 원본 유지(stub/-fallback, 정직 실패). `TRANSLATE_CHAIN_ORDER`(쉼표)로 순서·선택 오버라이드
(예전 이름 `TRANSLATE_PROVIDER_CHAIN`도 읽는다 — 새 이름 우선).

ADAPTER_DRY_RUN=1 시 실 API 호출 차단.
"""
from __future__ import annotations

import logging
import os
import re
import threading
from typing import Optional

logger = logging.getLogger(__name__)

# v60 STEP4: AI 초안·키워드 오염어 차단(STEP1 스코프 공유) — 확장 UI 텍스트·챗패널·도메인·수집기 문구.
_CONTAM_RE = re.compile(
    r"(chat\s*history|채팅\s*기록|고가수집|고가브릿지|gogabridj|kgp[-_ ]|확장\s*프로그램|사이드\s*패널|"
    r"sidebar|assistant|copilot|rufus|번역까지\s*한\s*번에|수집\s*중|https?://|www\.|\.com\b|\.co\.[a-z]{2}|"
    r"수집기|브라우저\s*확장)",
    re.I,
)


#: 문체 지시를 **실제로 따를 수 있는** 프로바이더 (D3-4 ④).
#:   사전형·통계형 MT(mymemory·papago·deepl·azure)는 「평서형 종결 금지」 같은 지시를 받을
#:   자리가 없다. 거기에 지시를 보내 놓고 「지시했다」고 적으면 그건 **따른 척**이다.
STYLE_CAPABLE = ("openai",)

#: R0(오너 2026-10-01): 기본 체인 순서 — Papago → DeepL → Azure → OpenAI → MyMemory(마지막).
#:   `TRANSLATE_CHAIN_ORDER`(쉼표)로 바꾼다. MyMemory를 아예 빼려면 순서에서 지우거나 `TRANSLATE_DISABLE_MYMEMORY=1`.
DEFAULT_CHAIN_ORDER = ("papago", "deepl", "azure", "openai", "mymemory")

#: Papago 하루 글자 상한(우리 쪽 비용 가드). 넘으면 그날은 Papago를 건너뛰고 DeepL로 내려간다.
#:   NCP Papago Translation은 **무료 제공량이 없는 종량제**(100만 자 단위 과금 — 검색 결과 기준, 공식 요금 페이지는
#:   이 작업 환경에서 막혀 직접 못 봤다). 그래서 이 값은 「무료 한도」가 아니라 **하루 지출 상한**이다.
#:   0이면 상한 없음(NCP 콘솔의 앱별 일 한도만 남는다). `PAPAGO_DAILY_CHAR_LIMIT`로 조정.
PAPAGO_DAILY_CHAR_LIMIT_DEFAULT = 100000

#: OpenAI 토큰 단가(USD/토큰) — gpt-4o-mini 기준(입력 $0.15/1M · 출력 $0.60/1M, src/ai/copywriter.py와 같은 값).
#:   다른 모델을 OPENAI_MODEL로 쓰면 이 단가는 근사다.
from decimal import Decimal as _Dec
_OPENAI_IN_USD = _Dec("0.00000015")
_OPENAI_OUT_USD = _Dec("0.0000006")


def _is_contaminated(s: str) -> bool:
    """상품 텍스트가 아니라 확장 UI·페이지 크롬 오염어인지(초안·키워드에서 배제)."""
    return bool(s) and bool(_CONTAM_RE.search(str(s)))


# v87-W5: 마켓 페이지 UI 쓰레기(상품 정보가 아님) — 라쿠텐 등 상세에서 스펙/키워드에 섞여 들어와
#   AI 초안을 오염시켰다(오너 TSUMUGI: 不適切な商品を報告·レビュー·お気に入り·送料無料이 초안에 그대로).
#   상품 속성어(サイズ/素材/원산지/색상/무게 등)는 건드리지 않도록 **UI 액션·배너 문구만** 좁게 매칭한다.
_MARKET_UI_JUNK_RE = re.compile(
    r"("
    r"不適切|商品を報告|この商品を報告|通報|問い合わせ|お問い合わせ|"                       # JP: 신고·문의
    r"レビュー|口コミ|お気に入り|ブックマーク|カート|買い物かご|購入手続き|レジ|"           # JP: 리뷰·찜·장바구니·결제
    r"送料無料|あす楽|ポイント\d*\s*倍|楽天ポイント|クーポン|ランキング|売れ筋|再入荷|"     # JP: 배송/포인트/쿠폰/랭킹 배너
    r"楽天市場|ショップを?見る|この商品について|数量|在庫あり|在庫なし|"                    # JP: 몰/재고/수량
    r"리뷰|후기|리뷰\s*쓰기|신고|문의하기|장바구니|찜하기|즐겨찾기|쿠폰|무료\s*배송|배송비\s*무료|랭킹|재입고|재고\s*있음|"  # KO
    r"write\s*a?\s*review|report\s*(this|item)|add\s*to\s*cart|wish\s*list|add\s*to\s*favorites?|free\s*shipping|coupon|in\s*stock|out\s*of\s*stock|ranking"  # EN
    r")",
    re.I,
)


def _is_ui_junk(s: str) -> bool:
    """상품 속성이 아니라 마켓 페이지 UI 액션/배너 문구인지(초안·키워드·스펙에서 배제)."""
    return bool(s) and bool(_MARKET_UI_JUNK_RE.search(str(s)))


# v87-W8 item3: 제목 상용구(라쿠텐 등) — 번역 전 제목에서 제거할 마켓 판촉/배송 상용구.
#   제목 segment 단위로 검사(공백···| 구분). 상품 속성어는 매칭 안 되게 좁게(선물포장/배송/포인트/쿠폰).
_MARKET_TITLE_JUNK_RE = re.compile(
    r"("
    r"楽ギフ|ギフト対応|のし対応|熨斗|ラッピング(無料)?|包装(無料)?|"           # JP: 선물/포장 상용구
    r"あす着|あす楽|翌日配送|即日発送|当日発送|送料無料|送料込|代引|"            # JP: 배송 상용구
    r"ポイント\d*倍|楽天ポイント|買い回り|マラソン|スーパーSALE|"               # JP: 포인트/세일
    r"クーポン|レビュー特典|ランキング\d*位?|\d+冠|"                             # JP: 쿠폰/후기특전/랭킹
    r"무료\s*배송|배송비\s*무료|사은품|쿠폰|적립|"                                # KO 상용구
    r"free\s*shipping|gift\s*wrap(ping)?"                                       # EN 상용구
    r")",
    re.I,
)


# v87-W9 item2: 상용구 변형 내성 — 구분자(_·전각＿·전각공백·【】··) 무시. 楽ギフ 계열은 뒤따르는
#   _包装/包装/対応까지 함께 제거(언더스코어 변형 '楽ギフ_包装' 미제거 재발 방지 — 실증 픽스처).
_GIFT_RUN_RE = re.compile(r"[【\[]?楽ギフ[_＿\s　]*(包装|対応)?[】\]]?", re.I)
_TITLE_SEP_RE = re.compile(r"[\s・|/／　_＿]+")


def strip_market_boilerplate(title: str) -> str:
    """v87-W9 item2: 제목에서 마켓 판촉/배송 상용구를 제거(상품 속성어 보존). 구분자 변형에 내성.
    ① 楽ギフ 런(_包装 등 접미 포함) 직접 제거 ② 구분자 정규화 후 세그먼트 드롭. 전부 제거되면 원문 유지."""
    t = str(title or "").strip()
    if not t:
        return t
    # ① 楽ギフ_包装/楽ギフ包装/【楽ギフ_包装】 등 언더스코어·전각·괄호 변형을 통째로 제거.
    cleaned = _GIFT_RUN_RE.sub(" ", t)
    # ② 구분자(공백·_·전각·・|/) 정규화 후 세그먼트 단위로 상용구 드롭.
    parts = _TITLE_SEP_RE.split(cleaned)
    kept = [p for p in parts if p and not _MARKET_TITLE_JUNK_RE.search(p)]
    out = " ".join(kept).strip(" -_·|/【】[]")
    return out or t


def _is_input_junk(s: str) -> bool:
    """AI 초안 입력에서 버릴 오염(확장 크롬 + 마켓 UI 쓰레기) 통합 판정."""
    return _is_contaminated(s) or _is_ui_junk(s)


def _clean_specs_for_draft(specs) -> list:
    """스펙 표에서 UI 쓰레기 행 제거(라벨 또는 값이 UI 액션/배너면 상품 스펙 아님) — 초안 오염 차단."""
    out = []
    for sp in (specs or []):
        try:
            label, value = str(sp[0] or "").strip(), str(sp[1] or "").strip()
        except Exception:
            continue
        if not label or not value:
            continue
        if _is_input_junk(label) or _is_input_junk(value):
            continue
        out.append([label, value])
    return out


def _clean_keywords_for_draft(keywords) -> list:
    """키워드에서 UI 쓰레기 제거(리뷰/신고/송료무료 등 상품어 아님)."""
    if isinstance(keywords, str):
        keywords = [k.strip() for k in keywords.split(",") if k.strip()]
    out = []
    for k in (keywords or []):
        s = str(k or "").strip()
        if s and len(s) > 1 and s not in out and not _is_input_junk(s):
            out.append(s)
    return out

# 마켓별 카피 톤앤매너 프롬프트 힌트
_MARKET_PROMPTS = {
    "coupang": "핵심 키워드 6개 + bullet list 형식. 간결하고 직접적.",
    "smartstore": "SEO 친화적. 상세 설명. 검색 키워드 포함. 신뢰감 강조.",
    "11st": "짧고 임팩트 있게. 가격 메리트와 특징 강조.",
}


def _dry_run() -> bool:
    return os.getenv("ADAPTER_DRY_RUN", "0") == "1"


# v87-W7: MyMemory langpair용 원문 언어 추정(스크립트 기반 휴리스틱). 한글=ko / 가나=ja /
#   가나 없는 한자=zh-CN / 그 외=en. 정밀 감지가 아니라 무료 MT 소스 지정용(틀리면 체인이 다음으로 폴백).
_BILINGUAL_DIVIDER = "───────── 원문 (Original) ─────────"


def compose_bilingual(ko: str, original: str) -> str:
    """v87-W7 item2: 상세 병기 — 한국어 번역 상단 + 구분선 + 원문 하단. 마켓 등록 시 이 병기본이 나간다.
    원문은 항상 보존(별도 저장 필드는 순수 유지, 병기는 표시·전송 시점에 합성). 둘이 같거나 한쪽이 비면
    중복 없이 하나만."""
    ko = str(ko or "").strip()
    original = str(original or "").strip()
    if not original or ko == original:
        return ko or original
    if not ko:
        return original
    return f"{ko}\n\n{_BILINGUAL_DIVIDER}\n{original}"


def _detect_src_lang(text: str) -> str:
    s = str(text or "")
    if not s.strip():
        return "en"
    has_hangul = any("가" <= c <= "힣" for c in s)
    if has_hangul:
        return "ko"
    has_kana = any(("぀" <= c <= "ゟ") or ("゠" <= c <= "ヿ") for c in s)
    if has_kana:
        return "ja"
    has_han = any("一" <= c <= "鿿" for c in s)
    if has_han:
        return "zh-CN"
    return "en"


def _route_src_lang(text: str) -> str:
    """v87-W9 item1: 체인·프로바이더 소스용 언어 감지 — **라틴 비율 무관**, 가나·한자 1자라도 있으면 ja.
    라쿠텐/아마존JP가 주 소스라 한자 제목(예 '玉渕')도 ja로 라우팅(zh 오판→mymemory 로마자화 방지).
    한글이 있으면 ko(번역 불필요), CJK 없으면 en."""
    s = str(text or "")
    if not s.strip():
        return "en"
    if any("가" <= c <= "힣" for c in s):
        return "ko"
    has_kana = any(("぀" <= c <= "ゟ") or ("゠" <= c <= "ヿ") for c in s)
    has_han = any("一" <= c <= "鿿" for c in s)
    # R0(오너 2026-10-01): 타오바오 제목(가나 0 · 간체자)이 전엔 ja로 판정돼 Papago에 `source=ja`로 갔다
    #   (운영 46건 실측 — 「懒人」→「일레븐」). 가나가 **없고** 간체 전용 글자가 하나라도 있으면 zh.
    #   일본어 한자 제목(玉渕·手帳)은 간체 전용 글자가 없어 ja 그대로.
    if has_han and not has_kana and _SIMPLIFIED_ONLY_RE.search(s):
        return "zh"
    if has_kana or has_han:      # 가나·한자 1자라도 → ja 체인(라틴 비율 무관)
        return "ja"
    return "en"


#: 간체 전용 글자(일본 신자체와 모양이 다른 것만 — 会·号·万·灯처럼 같은 글자는 뺐다). 상품명에 자주 나오는 것 위주.
_SIMPLIFIED_ONLY_RE = re.compile(
    "[们这个发东车说时买卖热无线电门实头长马鱼页质设计级纸维红绿蓝黑现货单气动转简约办务杂带适场轮叠换圆网垫盘懒师乐书"
    "产业专从优关兴养农决净凉减刘则刚创删别劳势华协卫厂厅历压县变吗员听启呜园围图块坚坛垒处备复够夹夺奋妆妇妈娱婴宁宠"
    "审宽对导尔尘尝层岁岛币帅帐帮广庆库应庙废开异弃张弹归录彻忆忧怀态总恶悬惊惯战户扑执扩扫扬扰抚抢护报拟拥拦择挤挥损"
    "据掳摄摆摊撑显晒晓晕暂术杀权杨极构枪标栏树样桥档梦检楼欢欧歼毁毕汇汉汤沟沪泪泼泽洁浆测济浏浑浓涛涝润涨渊渐渔满滚"
    "滤滥灭灵灶灾炼烂烛烦烧焕爱牍牵犹狈猎环玛珐琐瑶畅疗疮疯痒瘫盏盐监盖眯矫码砖础硕确离种积稳穷窍窑窜窝竞笔笋笼筑筛筝"
    "箩篮类粮紧纠纪纫纬纯纱纲纳纵纷纹纺练组绅细织终绊绍经绑结绕绘给络绝统继绩绪续绳绵绸综绽缆缓编缘缝缠缩缴罗罚罢职联"
    "聪肃肠肤肾肿胀胁胶脉脏脑脸腊腾舰舱艰艺节苏苹荐荡荣药莱获莹萝营萧虏虑虽虾蚀蚁蚂蛮蜡衔补衬袄袜袭裤见观规视览觉触誉"
    "订认讨让训议讯记讲许论访证评识诈诉词译试诗诚话诞询该详语误请诸读课谁调谈谊谋谓谢谣谱贝负贡财责贤败账贩贪贫购贯贴"
    "贵贷贸费贺赁资赋赌赎赏赐赔赖赚赛赞赠赶趋跃践踪躯轨轩软轰轴轻载较辅辆辈辉辑输辖边辽达迁过迈运还进远违连迟选递逻遗"
    "邓邮邻郑酱释鉴钉针钓钞钟钢钥钩钮钱钳钻铁铃铅铜铝铭银铺链销锁锅锐错锦键锯镇镜闪闭问闲间闷闹闻阀阁阅队阳阴阵阶际陆"
    "陈陕险随隐难雾韦韧韩顶项顺须顾顿颁颂预领颇颈频颗题颜额风飘飞饭饮饰饱饲饺饼馆驱驶驻驾验骑骗骚鲜鸟鸡鸣鸭鸽鹅鹰黾齐"
    "龙]"
)


# v87-W6 item 2: 번역 실패 다발 조사 — **계측**(호출 n·성공 n·실패 n·사유별). 번역 무료 쿼터 회계와
#   완전히 별개인 읽기 전용 관측 카운터(쿼터 무손대). 프로세스 인메모리 누적, get_translate_stats()로 노출.
# v87-W7a 재개정(branch②): 실패 시 **원 응답 코드·바디를 계측에 적재** — 다음 실패부터 원문 사유가 남게.
#   by_code(사유코드별)·recent(최근 실패 원문: provider·status·body 스니펫)를 추가(쿼터 회계 무손대).
_TR_STATS = {"calls": 0, "ok": 0, "fail": 0, "by_reason": {}, "by_code": {}, "recent": []}
_TR_STATS_LOCK = threading.Lock()
_TR_RECENT_MAX = 25


#: 실제 번역기 이름(체인 단). `-fallback`·`stub`·`none`·`rules`는 번역이 아니다.
REAL_PROVIDERS = ("mymemory", "papago", "deepl", "azure", "openai")


def is_real_translation(provider, error="") -> bool:
    """「실제로 번역됐나」 — 단 하나의 판정. R0 실측: 확장 수집 API가 `("mymemory","openai","deepl")`만 보고
    papago·azure 번역을 「안 됨」으로 저장했다(운영 papago 46건 전부 `translated=false`)."""
    return str(provider or "") in REAL_PROVIDERS and not str(error or "").strip()


def translated_flag(extra: dict) -> bool:
    """저장된 행의 번역 여부 — 저장값이 참이거나, 실제 번역기 이름이 있고 실패 사유가 없으면 참(옛 오기록 보정)."""
    ex = extra or {}
    return bool(ex.get("translated")) or is_real_translation(ex.get("translation_provider"), ex.get("translate_error"))


_PROV_DAY_PREFIX = "translate:provider_day:"
_PAPAGO_DAY_PREFIX = "translate:papago_chars:"


def _utc_day() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def _bump_provider_day(provider: str, ok: bool) -> None:
    """R0: 프로바이더별 **오늘(UTC)** 성공·실패 수를 공유 저장소(app_state)에 +1.

    진단 화면의 「호출 n」은 워커 메모리 카운터라 재시작·다른 워커면 0으로 보였다(오너 실측 「호출 0」 —
    같은 기간 운영 DB엔 papago 번역 46건). 이 수는 워커 둘·재시작에도 남는다. 실패는 조용히(번역을 막지 않는다).
    """
    # Y7-J: AI 상세 초안(`openai-draft`)도 openai 칸에 센다 — 10-09 초안 실패가 이 표에 아예 안 남았다.
    p = (provider or "").replace("-fallback", "").replace("-draft", "").strip().lower()
    if p not in ("mymemory", "papago", "deepl", "azure", "openai"):
        return
    key, field = _PROV_DAY_PREFIX + _utc_day(), f"{p}_{'ok' if ok else 'fail'}"
    try:
        from src.db import pg
        if pg.pg_enabled():
            with pg.tx() as cur:
                cur.execute(
                    "INSERT INTO app_state (key, value, updated_at) VALUES (%s::text, jsonb_build_object(%s::text, 1), now()) "
                    "ON CONFLICT (key) DO UPDATE SET value = jsonb_set(app_state.value, ARRAY[%s::text], "
                    "to_jsonb(COALESCE((app_state.value->>%s::text)::int, 0) + 1)), updated_at = now()",
                    (key, field, field, field))
            return
        from src.db import image_translate_queue_pg as st
        with st._LOCK:
            cur_v = dict(st._MEM_STATE.get(key) or {})
            cur_v[field] = int(cur_v.get(field) or 0) + 1
            st._MEM_STATE[key] = cur_v
    except Exception as exc:
        logger.warning("[번역 계측] 프로바이더 일 집계 기록 실패: %s: %s", type(exc).__name__, exc)


def provider_day_counts(day: str = "") -> dict:
    """`{provider: {ok, fail}}` — 오늘(UTC) 또는 `day`(YYYYMMDD). 없으면 빈 칸 0."""
    out = {p: {"ok": 0, "fail": 0} for p in DEFAULT_CHAIN_ORDER}
    try:
        from src.db import image_translate_queue_pg as st
        raw = st.state_get(_PROV_DAY_PREFIX + (day or _utc_day())) or {}
    except Exception:
        raw = {}
    for k, v in raw.items():
        p, _, kind = str(k).rpartition("_")
        if p in out and kind in ("ok", "fail"):
            out[p][kind] = int(v or 0)
    return out


def papago_daily_limit() -> int:
    try:
        return max(0, int(os.getenv("PAPAGO_DAILY_CHAR_LIMIT", str(PAPAGO_DAILY_CHAR_LIMIT_DEFAULT)) or 0))
    except (TypeError, ValueError):
        return PAPAGO_DAILY_CHAR_LIMIT_DEFAULT


def papago_chars_today() -> int:
    try:
        from src.db import option_translate_queue_pg as q
        return int(q.day_count(_PAPAGO_DAY_PREFIX + _utc_day()))
    except Exception:
        return 0


def _papago_take(chars: int) -> bool:
    """오늘 Papago 몫에서 `chars`자를 가져간다(워커 공유·원자적). 상한이면 False — 그날은 다음 단(DeepL)으로."""
    limit = papago_daily_limit()
    if limit <= 0 or chars <= 0:
        return True
    from src.db import option_translate_queue_pg as q
    granted, _n = q.take_n(_PAPAGO_DAY_PREFIX + _utc_day(), limit, chars)
    if granted < chars:
        # 일부만 남았으면 그 몫도 다 써 버린 것으로 둔다(오늘 남은 호출이 반쪽 번역을 내지 않게).
        return False
    return True


def _papago_exhaust_today() -> None:
    """Papago가 한도 초과로 거절했으면(NCP 콘솔 일 한도 등) 오늘 몫을 상한까지 채워 다시 안 부르게 한다."""
    limit = papago_daily_limit()
    if limit <= 0:
        return
    try:
        from src.db import option_translate_queue_pg as q
        q.take_n(_PAPAGO_DAY_PREFIX + _utc_day(), limit, limit)
    except Exception:
        pass


class PapagoDailyLimit(RuntimeError):
    """우리 쪽 Papago 일 상한 도달 — 체인이 다음 단으로 내려간다(실패 아님, 건너뜀)."""


def _record_translate(ok: bool, reason: str = "", provider: str = "",
                      code: str = "", status=None, body: str = "") -> None:
    _bump_provider_day(provider, ok)
    with _TR_STATS_LOCK:
        _TR_STATS["calls"] += 1
        if ok:
            _TR_STATS["ok"] += 1
        else:
            _TR_STATS["fail"] += 1
            key = (reason or code or "원인 미상")[:80]
            _TR_STATS["by_reason"][key] = _TR_STATS["by_reason"].get(key, 0) + 1
            if code:
                _TR_STATS["by_code"][code] = _TR_STATS["by_code"].get(code, 0) + 1
            # 원 응답(코드·상태·바디 스니펫) 보존 — 오귀인 시 대조용. 시크릿 없음(에러 바디만, 300자).
            _TR_STATS["recent"].append({
                "provider": provider or "", "code": code or "", "status": status,
                "body": (body or "")[:300], "reason": (reason or "")[:120]})
            if len(_TR_STATS["recent"]) > _TR_RECENT_MAX:
                _TR_STATS["recent"] = _TR_STATS["recent"][-_TR_RECENT_MAX:]


def raw_error_meta(exc: Exception):
    """예외에서 원 응답 (status_code, body 스니펫) 추출 — 프로바이더 응답 원문 보존용."""
    status = None
    body = ""
    resp = getattr(exc, "response", None)
    if resp is not None:
        status = getattr(resp, "status_code", None)
        try:
            body = (getattr(resp, "text", "") or "")[:300]
        except Exception:
            body = ""
    if not body:
        body = str(exc or "")[:300]
    return status, body


def _exc_text(exc: Exception) -> str:
    """예외 문자열 + 응답 본문 — Y7-K: 429의 진짜 사유(insufficient_quota·credit_balance_exhausted)는 **본문**에만 있다.
    `str(HTTPError)`는 「429 Client Error: Too Many Requests」뿐이라 크레딧 소진을 속도 제한으로 읽었다."""
    s = str(exc or "")
    resp = getattr(exc, "response", None)
    if resp is not None:
        try:
            s += " " + (getattr(resp, "text", "") or "")[:600]
        except Exception:
            pass
    return s.lower()


def is_credit_exhausted(exc: Exception) -> bool:
    s = _exc_text(exc)
    return "insufficient_quota" in s or "credit_balance_exhausted" in s or "no credits remaining" in s


def _is_rate_limit_exc(exc: Exception) -> bool:
    resp = getattr(exc, "response", None)
    code = getattr(resp, "status_code", None) if resp is not None else None
    if is_credit_exhausted(exc):
        return False                                 # Y7-K: 크레딧 0은 기다려도 안 풀린다 — 재시도하지 않는다
    s = str(exc or "").lower()
    return code == 429 or "rate limit" in s or "rate_limit" in s or "too many requests" in s


def _post_with_429_retry(req, url, **kw):
    """v87-W8 item4: OpenAI 상시 429 대응 — rate_limit이면 **짧은 백오프 1회**만 재시도(과금·지연 최소).
    재시도도 실패하면 예외 전파 → 체인이 다음(또는 stub) 폴백. env OPENAI_RETRY_BACKOFF_SEC(기본 1.5, 0=끔)."""
    try:
        r = req.post(url, **kw)
        r.raise_for_status()
        return r
    except Exception as exc:
        if not _is_rate_limit_exc(exc):
            raise
        try:
            backoff = float(os.getenv("OPENAI_RETRY_BACKOFF_SEC", "1.5") or 0)
        except (TypeError, ValueError):
            backoff = 1.5
        if backoff > 0:
            import time as _t
            _t.sleep(min(backoff, 5))
        logger.warning("OpenAI 429(rate_limit) — %.1fs 백오프 후 1회 재시도", backoff)
        r = req.post(url, **kw)      # 1회만 재시도. 또 429면 raise → 폴백.
        r.raise_for_status()
        return r


def record_translate_failure(exc: Exception, provider: str) -> str:
    """분류(코드·문구) + 원 응답(status·body)을 계측에 적재하고 사람 문구를 반환(호출측 error 표시용)."""
    code, reason = classify_translate_reason(exc)
    status, body = raw_error_meta(exc)
    _record_translate(False, reason=reason, provider=provider, code=code, status=status, body=body)
    return reason


def failure_line(exc: Exception, provider: str) -> str:
    """Y5(오너 2026-10-04): AI 호출 실패를 **한 줄 원문**으로 — 사유 · 공급사 · HTTP 코드 · 재시도 여부 · 응답 앞부분.
    「요청 속도 제한」「HTTPError」만 보여서 무엇이 언제 막았는지 몰랐다. 계측에도 같이 적재한다."""
    code, reason = classify_translate_reason(exc)
    status, body = raw_error_meta(exc)
    _record_translate(False, reason=reason, provider=provider, code=code, status=status, body=body)
    label = provider_label(provider.split("-")[0])
    retry = ("429 백오프 재시도 1회 뒤에도 실패" if code == "rate_limit"
             else ("재시도 안 함(서버 월 예산)" if code == "budget" else "재시도 안 함"))
    return f"{reason} · {label} HTTP {status if status else '—'} · {retry} · 원문 {str(body or '')[:120]}"


def provider_diagnostics() -> list:
    """v87-W11 item1: 프로바이더별 **env 검출 여부 + 활성 체인 포함 여부**(키 값 미출력).
    '상위 4 전멸'이 env 미검출(체인에서 제외됨)인지 호출 실패(체인엔 있으나 실패)인지 즉시 판별.
    호출 실패 사유는 get_translate_stats()의 by_code/recent(원 응답)로 대조."""
    from src.utils.env import env_present
    checks = {
        "mymemory": lambda: os.getenv("TRANSLATE_DISABLE_MYMEMORY") != "1",
        "papago": lambda: env_present("NCP_PAPAGO_CLIENT_ID") and env_present("NCP_PAPAGO_CLIENT_SECRET"),
        "deepl": lambda: env_present("DEEPL_API_KEY"),
        "azure": lambda: env_present("AZURE_TRANSLATOR_KEY"),
        "openai": lambda: env_present("OPENAI_API_KEY"),
    }
    active = set(AITranslator()._provider_chain())          # 무키(비-ja 기본) 순서 기준
    active_ja = set(AITranslator()._provider_chain(src_lang="ja"))
    out = []
    for name in ["mymemory", "papago", "deepl", "azure", "openai"]:
        try:
            present = bool(checks[name]())
        except Exception:
            present = False
        out.append({"provider": name, "env_present": present,
                    "in_chain": name in (active | active_ja)})
    return out


def get_translate_stats() -> dict:
    """번역 호출 계측 스냅샷(읽기 전용) — 호출/성공/실패/사유별·코드별·최근 실패 원문. 쿼터 회계와 무관."""
    with _TR_STATS_LOCK:
        return {"calls": _TR_STATS["calls"], "ok": _TR_STATS["ok"], "fail": _TR_STATS["fail"],
                "by_reason": dict(_TR_STATS["by_reason"]), "by_code": dict(_TR_STATS["by_code"]),
                "recent": list(_TR_STATS["recent"])}


def reset_translate_stats() -> None:
    """계측 리셋(테스트·리포트 구간 측정용)."""
    with _TR_STATS_LOCK:
        _TR_STATS["calls"] = 0
        _TR_STATS["ok"] = 0
        _TR_STATS["fail"] = 0
        _TR_STATS["by_reason"] = {}
        _TR_STATS["by_code"] = {}
        _TR_STATS["recent"] = []


# v87-W7 회수: 실패 메시지에 **프로바이더명 명시** — 체인 도입 후 어느 단이 죽었는지 오너가 바로 알아야 한다.
_PROVIDER_LABEL = {"mymemory": "MyMemory", "papago": "Papago", "deepl": "DeepL",
                   "azure": "Azure", "openai": "OpenAI"}


def provider_label(name: str) -> str:
    """체인 프로바이더 내부명 → 사람이 읽을 표기(‘-fallback’ 접미 제거)."""
    base = (name or "").replace("-fallback", "").strip().lower()
    return _PROVIDER_LABEL.get(base, base or "번역")


# v87-W7a 재개정: "한도 초과" 발화 주체를 4분한다(오너 실증 — OpenAI 잔액 $22.37, 크레딧 고갈 기각).
#   ①서버 내부 예산 가드(AI_MONTHLY_BUDGET_USD) 차단 → **"서버 월 예산"** 명시(OpenAI 지갑 아님)
#   ②프로바이더 429 insufficient_quota(크레딧·결제 소진) ③프로바이더 429 rate_limit(요청 속도 — 재시도)
#   ④401/403 무효 키. 각각 별 문구 + 짧은 사유코드(translate_stats 집계). 종전엔 ①③를 ②로 뭉갰다.
def classify_translate_reason(exc: Exception) -> tuple:
    """(사유코드, 사람 문구) 반환. 코드는 translate_stats 집계용(budget/quota/rate_limit/auth/model/timeout/network/http/unknown)."""
    s = _exc_text(exc)                                # Y7-K: 응답 본문까지(429 크레딧 소진 판별)
    status = None
    resp = getattr(exc, "response", None)
    if resp is not None:
        status = getattr(resp, "status_code", None)
    # ① 서버 내부 예산 가드(우리 코드가 막은 것) — OpenAI 결제와 무관. 오너가 지갑 뒤지지 않게 명시.
    if type(exc).__name__ == "BudgetExceededError" or "월 예산" in str(exc or "") or "monthly budget" in s:
        return ("budget", "서버 월 예산 상한에 도달해 AI 호출을 멈췄어요(OpenAI 잔액 아님 · AI_MONTHLY_BUDGET_USD 상향/대기)")
    # ④ 인증
    if status in (401, 403) or "unauthorized" in s or "invalid_api_key" in s or "authenticationerror" in s:
        return ("auth", "API 키가 잘못됐거나 만료됐어요(키 재발급 후 재설정)")
    # ② 프로바이더 크레딧·결제 소진(429 insufficient_quota) — 진짜 '결제' 문제.
    if "insufficient_quota" in s or "credit_balance_exhausted" in s or ("quota" in s and "rate" not in s):
        return ("quota", "프로바이더 크레딧·결제가 소진됐어요(해당 프로바이더 결제·플랜 확인)")
    # ③ 프로바이더 요청 속도 제한(429 rate limit) — 결제 아님, 잠시 후 재시도.
    if status == 429 or "rate limit" in s or "rate_limit" in s or "too many requests" in s:
        return ("rate_limit", "요청 속도 제한에 걸렸어요(결제 아님 · 잠시 후 자동 재시도)")
    if (status in (404, 400) and "model" in s) or ("model" in s and ("does not exist" in s or "not found" in s)):
        return ("model", "설정한 모델명(OPENAI_MODEL)이 잘못됐어요")
    if "timeout" in s or "timed out" in s:
        return ("timeout", "번역 서버 응답이 지연됐어요(잠시 후 재시도)")
    if "connection" in s or "network" in s or "resolve" in s or "ssl" in s:
        return ("network", "번역 서버에 연결하지 못했어요(네트워크·프록시 확인)")
    if status:
        return ("http", f"번역 API 오류(HTTP {status})")
    return ("unknown", "번역 API 호출에 실패했어요")


#: Y7-K — AI 초안이 기본 문장으로 대신 나갈 때 화면 한 줄(영문 원문 없음). 코드 = `classify_translate_reason`
DRAFT_FALLBACK_REASON = {
    "quota": "OpenAI 크레딧 없음", "budget": "서버 월 예산 상한", "auth": "OpenAI 키 확인 필요",
    "rate_limit": "OpenAI 요청이 몰려 잠시 막힘", "model": "AI 모델 설정 확인 필요", "timeout": "AI 응답 지연",
    "network": "AI 서버 연결 실패",
}


def draft_user_line(code: str, status=None) -> str:
    why = DRAFT_FALLBACK_REASON.get(code or "", "AI 호출 실패")
    return f"{why}" + (f"(HTTP {status})" if status else "")


def classify_translate_error(exc: Exception) -> str:
    """사람이 읽을 한 줄(무음 금지·오귀인 금지). 사유코드는 classify_translate_reason 참조."""
    return classify_translate_reason(exc)[1]


_CAT_LABEL = {
    "BAG": "가방", "CLO": "의류", "BTY": "뷰티", "FOD": "식품", "ELC": "가전", "DIG": "디지털",
    "HOM": "홈·리빙", "HLT": "건강", "SPT": "스포츠·레저", "TOY": "완구", "BBY": "유아", "PET": "반려동물",
    "OFC": "문구·오피스", "GEN": "",
}


#: Y7-J(오너 2026-10-10) — 상세 초안 형식 버전. 저장된 `detail_auto.v`가 이보다 낮으면 사전검증이 다시 만든다.
DRAFT_VERSION = 2


def _josa(word: str, with_final: str, without_final: str) -> str:
    """받침 있으면 with_final(은·이), 없으면 without_final(는·가). 한글이 아니면 앞쪽 표기."""
    w = str(word or "").strip()
    if not w:
        return without_final
    ch = w[-1]
    if "가" <= ch <= "힣":
        return with_final if (ord(ch) - 0xAC00) % 28 else without_final
    return with_final


def draft_source_lines(description: str, title: str = "") -> list:
    """원문 상세에서 초안 재료로 쓸 줄 — 가게 통계·운영 줄(S2 표)·UI 쓰레기·상표 줄·초단문·**상품명과 같은 줄**(Y7-K) 제외."""
    from src.collectors import ko_polish as _kp
    from src.uploaders.detail_ui_junk import is_junk as _ui_junk
    if _ui_junk(str(description or "")):
        return []                                               # Y7-N: 본문 전체가 가게 UI 글자 — 재료 0
    txt, _d = _kp.drop_detail_lines(str(description or ""))
    txt, _m = _kp.gate_lines(txt)
    out = []
    for ln in txt.replace("\r", "").split("\n"):
        s = ln.strip()
        if len(s) < 4 or _is_input_junk(s) or _is_contaminated(s) or s in out:
            continue
        if re.fullmatch(r"[\d.,%\s]+", s):                     # 「4.8」 같은 숫자 조각
            continue
        if title and re.sub(r"\s+", " ", s) == re.sub(r"\s+", " ", str(title).strip()):
            continue                                            # 상품명 그대로(원문 상세가 제목만 담은 상품) — 내용 아님
        out.append(s)
    return out


def _structured_draft(title, category, keywords, specs, options, brand, description="") -> str:
    """키 없음·AI 실패 때의 초안 — **확인된 정보만 문장으로**(Y7-J 오너 2026-10-10).

    예전 형식은 「■ 특징」에 키워드(= 옛 번역 제목을 낱말로 자른 값)를 한 줄씩 나열했다 — 셰고가 13802276439
    본문 「· 미야케 · 아키라의 · 미니멀리즘 …」. 이제 키워드는 쓰지 않는다(`keywords`는 호환용 인자).
    순서: 상품 한 줄 → ■ 옵션·상세(옵션은 문장, 스펙은 「이름: 값」) → ■ 원문 상세(남는 줄이 있을 때만) →
    ■ 사이즈·세탁 안내(의류) → ■ 배송·구매대행 안내. 「해외 정품」 같은 확인 안 된 주장은 쓰지 않는다.
    """
    from src.collectors import ko_polish as _kp

    def _clean(v):
        return str(v or "").strip()

    lines = []
    t = _clean(title)
    if t and _is_contaminated(t):
        t = ""
    t = _kp.strip_marks(t)[0] if t else ""
    if t:
        lines.append(t)

    rows, seen = [], set()
    for opt in (options or []):
        if not isinstance(opt, dict):
            continue
        name = _clean(opt.get("name_ko") or opt.get("name"))
        vals = []
        for v in (opt.get("values_ko") or opt.get("values") or []):
            vv = _kp.strip_marks(_clean(v.get("ko") or v.get("src") if isinstance(v, dict) else v))[0]
            if vv and vv not in vals:
                vals.append(vv)
        if not name or not vals or name in seen:
            continue
        seen.add(name)
        if len(vals) == 1:
            rows.append(f"· {name}{_josa(name, '은', '는')} {vals[0]} 한 가지예요.")
        else:
            rows.append(f"· {name}{_josa(name, '은', '는')} {', '.join(vals[:12])}"
                        f"{' 외' if len(vals) > 12 else ''} {len(vals)}가지 중에서 고를 수 있어요.")
    for sp in (specs or []):
        try:
            label, value = _clean(sp[0]), _clean(sp[1])
        except Exception:
            continue
        if not label or not value or len(label) <= 1 or len(value) <= 1 or label in seen:
            continue      # ★ '- k: v' 플레이스홀더/빈 행 · 옵션과 같은 이름 생략(두 번 싣지 않음)
        value = _kp.strip_marks(value)[0]
        if not value:
            continue
        seen.add(label)
        rows.append(f"· {label}: {value}")
    if rows:
        lines += ["", "■ 옵션·상세"] + rows

    src_lines = draft_source_lines(description, t)
    if src_lines:
        lines += ["", "■ 원문 상세"] + src_lines[:40]   # ★ 원문 라인 통째(숫자 조각으로 쪼개지 않음)

    if _clean(category) == "CLO":
        lines += ["", "■ 사이즈·세탁 안내",
                  "· 사이즈는 옵션에 적힌 표기를 기준으로 해요. 실측 치수는 위 사진의 사이즈 안내를 확인해 주세요.",
                  "· 세탁은 제품에 붙은 라벨 안내를 따라 주세요."]

    if not rows and not src_lines:
        lines += ["", "· 확인된 상세 정보가 부족합니다. 소재·사이즈·용도 등을 직접 입력해 주세요."]
    lines += ["", "■ 배송·구매대행 안내",
              "· 해외 구매대행 상품으로, 주문 후 현지 배송·통관을 거쳐 발송됩니다.",
              "· 모니터·조명 환경에 따라 실제 색상과 차이가 있을 수 있습니다.",
              "· 정확한 사이즈·소재는 위 옵션·상세 정보를 확인해 주세요.",
              "· 교환·반품은 판매 마켓과 구매대행 정책을 따릅니다."]
    return "\n".join(lines).strip()


class AITranslator:
    """상품 메타데이터 → 한국어 번역 + 마켓별 광고 카피 생성."""

    def __init__(self) -> None:
        self.provider = self._select_provider()
        logger.info("AITranslator 초기화: provider=%s", self.provider)

    def _select_provider(self) -> str:
        """사용 가능한 AI 프로바이더 선택. v44 0-1: 값의 따옴표/공백을 제거해 읽는다."""
        from src.utils.env import env_present
        if env_present("OPENAI_API_KEY"):
            return "openai"
        if env_present("DEEPL_API_KEY"):
            return "deepl"
        return "stub"

    # v87-W7 item1: 번역 프로바이더 **체인** — 하나 실패하면 다음 시도. 기본 순서는 브리프대로 **무료 우선**
    #   (mymemory=무키·무가입) → 저가/키필요(deepl, 키 있을 때만) → OpenAI(키 있을 때만). env
    #   `TRANSLATE_PROVIDER_CHAIN`(쉼표구분)로 순서·선택 오버라이드(예: "openai,mymemory"로 품질 우선).
    #   mymemory는 `TRANSLATE_DISABLE_MYMEMORY=1`로 끌 수 있다(사설 프록시 등 외부호출 차단 환경).
    def _provider_chain(self, src_lang: str = None) -> list:
        from src.utils.env import env_present
        # R0(오너 2026-10-01): 순서 env는 `TRANSLATE_CHAIN_ORDER`(쉼표). 예전 이름 `TRANSLATE_PROVIDER_CHAIN`도
        #   그대로 읽는다(새 이름이 우선). 둘 다 없으면 기본 순서 — **모든 원문 언어 공통**.
        #   예전 기본(비-ja)은 mymemory가 맨 앞이라 무료 단이 거의 늘 이겼다 — 뒤 단은 부를 일이 없었다.
        override = (os.getenv("TRANSLATE_CHAIN_ORDER", "").strip()
                    or os.getenv("TRANSLATE_PROVIDER_CHAIN", "").strip())
        if override:
            names = [n.strip().lower() for n in override.split(",") if n.strip()]
        else:
            names = list(DEFAULT_CHAIN_ORDER)
        chain = []
        for n in names:
            if n == "openai" and not env_present("OPENAI_API_KEY"):
                continue
            if n == "deepl" and not env_present("DEEPL_API_KEY"):
                continue
            # Papago(NCP)는 CLIENT_ID·SECRET 둘 다 있어야 호출 가능.
            if n == "papago" and not (env_present("NCP_PAPAGO_CLIENT_ID") and env_present("NCP_PAPAGO_CLIENT_SECRET")):
                continue
            if n == "azure" and not env_present("AZURE_TRANSLATOR_KEY"):
                continue
            if n == "mymemory" and os.getenv("TRANSLATE_DISABLE_MYMEMORY") == "1":
                continue
            if n in ("mymemory", "papago", "deepl", "azure", "openai") and n not in chain:
                chain.append(n)
        return chain

    def _budget_left(self) -> float:
        """v87-W10: 요청 예산 잔여 초. deadline 미설정(비-translate_product 경로)이면 큰 값."""
        import time as _t
        dl = getattr(self, "_deadline", None)
        return 1e9 if dl is None else (dl - _t.time())

    def _clamp_timeout(self, default: float) -> float:
        """프로바이더 소켓 timeout을 남은 예산으로 클램프(최소 1초) — 워커 장기 점유 차단."""
        left = self._budget_left()
        return max(1.0, min(float(default), left)) if left < 1e8 else float(default)

    def translate_product(self, source: dict, *, style: str = "") -> dict:
        """상품 메타데이터를 한국어로 번역하고 마켓별 카피 생성 — **프로바이더 체인**(순차 폴백).

        반환: {title_ko, description_ko, copy_*, provider, attempts:[{provider,ok,error}], (translate_error)}
        - 첫 성공 프로바이더의 결과 반환 + attempts(시도 이력). 전부 실패면 원문 유지 + provider="none" +
          translate_error(마지막 사유). 키/프로바이더 전무면 stub(원문 유지, 실패 아님).

        ## `style` — 문체 지시 (D3-4 ④, 오너 2026-09-21)

        상품 이미지의 글자는 **광고 카피**다. 일반 프롬프트는 「~입니다」로 끝나는 평서문을 낸다.
        지시가 오면 **지시를 따를 수 있는 프로바이더**(`STYLE_CAPABLE`)로 체인을 좁힌다 —
        사전형 MT에 문체를 시키는 것은 시키는 척일 뿐이다.

        그런 프로바이더가 **하나도 없으면** 원래 체인 그대로 돌리되 결과에
        **`style_applied=False`**를 남긴다. 조용히 따른 척하지 않는다.
        """
        # v87-W8 item3: 라쿠텐 상용구(楽ギフ_包装·あす着·送料無料 등)를 **번역 전** 제목에서 제거
        #   (상품 속성어 보존). 안 그러면 mymemory가 상용구를 오역해 "Rakugifu_포장 내일 착용 서신"류가 남는다.
        title = strip_market_boilerplate(source.get("title", ""))
        description = source.get("description", "")

        if _dry_run():
            logger.info("ADAPTER_DRY_RUN=1 — AITranslator stub 모드")
            return {"title_ko": title, "description_ko": description, "provider": "stub",
                    "copy_coupang": f"[stub] {title}", "copy_smartstore": f"[stub] {title}",
                    "copy_11st": f"[stub] {title}", "attempts": []}

        # v87-W8 item3 / v87-W9 item1: 소스 언어별 체인 — 가나·한자 1자라도 있으면 ja(라틴 비율 무관).
        #   ja는 papago/deepl 선행, mymemory 후순위(저품질 로마자화 방지). 감지·체인을 결과에 기록(진단).
        _src = _route_src_lang((title or "") + " " + (description or ""))
        chain = self._provider_chain(src_lang=_src)
        # D3-4 ④ — 문체 지시가 있으면 **따를 수 있는 단**으로 좁힌다(없으면 그대로 + 정직 표기).
        style = str(style or "").strip()
        style_applied = False
        if style and chain:
            capable = [n for n in chain if n in STYLE_CAPABLE]
            if capable:
                chain, style_applied = capable, True
        if not chain:
            logger.warning("AI 번역 프로바이더 없음(키·무료 모두 불가) — 원본 반환 (stub 모드)")
            return {"title_ko": title, "description_ko": description, "provider": "stub",
                    "copy_coupang": f"[stub] {title}", "copy_smartstore": f"[stub] {title}",
                    "copy_11st": f"[stub] {title}", "attempts": []}

        import time as _time
        # v87-W10 item2: **요청 경로 워커 보호** — 체인 전체 소요에 상한(기본 8초). 체인 순서·프로바이더는
        #   불변(로직 무손대), 각 프로바이더 timeout을 '남은 예산'으로 클램프하고, 예산 소진이면 다음 시도
        #   없이 정직 실패 반환. 워커를 오래 점유(최악 125초)해 전면 저속·워커 고갈되던 것을 차단.
        try:
            _budget = float(os.getenv("TRANSLATE_REQUEST_BUDGET_SEC", "8") or "8")
        except (TypeError, ValueError):
            _budget = 8.0
        self._deadline = _time.time() + max(1.0, _budget)   # 프로바이더가 _budget_left()로 읽어 timeout 클램프
        attempts = []
        _invented_fallback = None
        for name in chain:
            _t0 = _time.time()
            if self._budget_left() < 0.8:      # 남은 예산이 사실상 없으면 다음 프로바이더 시도 중단(정직 실패로)
                attempts.append({"provider": name, "ok": False, "error": "요청 시간 예산 초과(서버 보호)",
                                 "ms": 0, "skipped": True})
                logger.warning("[번역 체인] 예산 초과 — %s 이후 시도 중단(워커 보호)", name)
                break
            try:
                if name == "mymemory":
                    res = self._translate_mymemory(title, description)
                elif name == "papago":
                    res = self._translate_papago(title, description)
                elif name == "deepl":
                    res = self._translate_deepl(title, description)
                elif name == "azure":
                    res = self._translate_azure(title, description)
                elif name == "openai":
                    res = self._translate_openai(title, description, style=style)
                else:
                    continue
            except Exception as exc:
                res = {"provider": name + "-fallback", "error": classify_translate_error(exc)}
            ok = str(res.get("provider") or "") == name and not res.get("error")
            # T3(오너 2026-10-02): 번역기가 **원문에 없는 고유명**을 만들면(「三宅艺创」 → 「미야케 아키라」) 그 결과는 버리고
            #   다음 엔진으로. 끝까지 다 그러면 정리 규칙(이름 → 「플리츠」)을 건 값을 쓴다(아래).
            if ok:
                try:
                    from src.collectors.ko_polish import invented_names as _inv
                    _bad = _inv(title, res.get("title_ko") or "")
                except Exception:
                    _bad = []
                if _bad:
                    ok = False
                    res = dict(res, error=f"원문에 없는 고유명({', '.join(_bad)})을 만들어 버렸습니다")
                    _invented_fallback = res
            attempts.append({"provider": name, "ok": bool(ok), "error": str(res.get("error") or ""),
                             "ms": int((_time.time() - _t0) * 1000)})   # v87-W7: 소요 시간 기록
            if res.get("skipped"):
                attempts[-1]["skipped"] = True      # R0: 비용 상한으로 건너뜀(호출 안 함) — 실패와 구별
            if ok:
                res["attempts"] = attempts
                res["detected_lang"] = _src          # v87-W9 item1: 감지 언어·선택 체인 기록(진단만으로 판독)
                res["chain"] = list(chain)
                if style:
                    res["style"] = style
                    res["style_applied"] = bool(style_applied and name in STYLE_CAPABLE)
                return res
            logger.warning("[번역 체인] %s 실패(%s) → 다음 프로바이더", name, res.get("error") or "원인 미상")

        if _invented_fallback is not None:
            # T3: 엔진마다 같은 고유명을 만들었다 — 정리 규칙으로 이름을 바꾼 값을 쓰고 그 사실을 남긴다.
            from src.collectors.ko_polish import invented_names as _inv2, polish_ko as _pk
            fixed = _pk(_invented_fallback.get("title_ko") or "")
            if fixed and not _inv2(title, fixed):
                out = dict(_invented_fallback, title_ko=fixed, attempts=attempts, detected_lang=_src, chain=list(chain),
                           translate_warn="번역기가 원문에 없는 고유명을 만들어 정리 규칙으로 바꿨습니다")
                out.pop("error", None)
                return out
        # 체인 전부 실패 → 원문 유지(정직 실패). 마지막 프로바이더·사유를 보존(드로어·하위호환 진단).
        _last = attempts[-1]["provider"] if attempts else ""
        _reason = (attempts[-1]["error"] if attempts else "") or "번역 실패"
        # v87-W7 회수: 실패 메시지에 프로바이더명 명시("OpenAI: 결제 한도 초과" 식) — 어느 단이 죽었는지 즉시 파악.
        _err = f"{provider_label(_last)}: {_reason}" if _last else _reason
        return {"title_ko": title, "description_ko": description,
                "provider": (_last + "-fallback") if _last else "none",
                "error": _err, "translate_error": _err, "attempts": attempts,
                "detected_lang": _src, "chain": list(chain),
                "copy_coupang": f"[fallback] {title}", "copy_smartstore": f"[fallback] {title}",
                "copy_11st": f"[fallback] {title}"}

    def translate_options(self, options: list) -> dict:
        """v87-W9 item3: 옵션명·값(ブラウン→브라운) 번역 + **원문 보존**. 체인 경유(ja면 papago 선두).

        입력: [{name, values:[...]}]. 반환: {"options":[{name, name_ko, values, values_ko}], "provider", "translated": bool}
        원문 보존: values/name은 그대로 두고 *_ko를 병기. 실패 시 *_ko=원문(가짜 번역 0).
        """
        opts = [o for o in (options or []) if isinstance(o, dict)]
        if not opts:
            return {"options": [], "provider": "none", "translated": False}
        # 고유 용어 수집(옵션명 + 값) → 한 번에 매핑(중복 호출 최소, 최대 40개).
        terms = []
        for o in opts:
            nm = str(o.get("name") or "").strip()
            if nm:
                terms.append(nm)
            for v in (o.get("values") or ([o.get("value")] if o.get("value") is not None else [])):
                sv = str(v or "").strip()
                if sv:
                    terms.append(sv)
        uniq = []
        for t in terms:
            if t not in uniq:
                uniq.append(t)
        # T1/T2(오너 2026-09-30-H): 전엔 **앞 40개만** 한 줄씩 이어 한 번에 보냈고, 줄 수가 하나라도 어긋나면
        #   전부 원문으로 뒀다(MyMemory는 480자에서 자른다 → 긴 목록은 거의 늘 어긋남). 게다가 이 함수는
        #   「한국어 번역」 버튼에서만 불렸다 — 운영 최근 48건 values_ko 0개.
        #   이제: ① 정리 규칙(ko_polish)으로 먼저 옮기고(판촉 접미사 삭제·소재·색상) 한자가 안 남으면 번역기 안 부름
        #         ② 남은 것만 **작은 묶음**(≤450자·≤15개)으로 — 한 묶음이 어긋나도 그 묶음만 원문
        #         ③ 번역 결과도 정리 규칙을 한 번 더(「재고 있음」 같은 판촉 직역 삭제)
        from src.collectors import ko_polish as _kp
        mapping = {}
        pending = []                                # (원문, 번역기에 보낼 정리본)
        for t in uniq:
            if _route_src_lang(t) == "ko" and not _kp.has_han(t):
                mapping[t] = t
                continue
            if _kp.has_han(t) and not re.search("[\u3040-\u30ff]", t):      # 중국어만 규칙표(일본어 가나는 번역기로)
                ov = _kp.option_value(t)
                if ov["value"]:
                    mapping[t] = ov["value"]
                    continue
            pending.append((t, _kp.strip_cn(t) or t))      # 번역기엔 지우기만 한 원문(섞으면 「한국어」로 오판)
        provider, translated = ("rules" if mapping and any(mapping[k] != k for k in mapping) else "none"), False
        if any(mapping[k] != k for k in mapping):
            translated = True
        batches, cur, size = [], [], 0
        for t, pre in pending:
            if cur and (len(cur) >= 15 or size + len(pre) + 1 > 450):
                batches.append(cur)
                cur, size = [], 0
            cur.append((t, pre))
            size += len(pre) + 1
        if cur:
            batches.append(cur)
        # Z 후속2(오너 2026-10-04 20:39): 못 옮긴 값마다 **왜**를 남긴다 — 번역기 응답 원문·시도 이력.
        #   「옵션 값 1개 미해석」만으론 범인을 못 찾는다(보류 문구가 이걸 그대로 싣는다).
        diag: dict = {}
        for batch in batches[12:]:
            for t, _pre in batch:
                diag[t] = "한 번에 보내는 12묶음을 넘어 이번엔 안 보냄(다음 번역에서)"
        for batch in batches[:12]:                  # 한 번에 최대 12묶음(≈180값) — 나머지는 다음 번역에서
            out = self.translate_product({"title": "", "description": "\n".join(p for _t, p in batch)})
            prov = out.get("provider", "none")
            ok = prov not in ("none", "stub", "") and not str(prov).endswith("-fallback")
            ko_lines = [l.strip() for l in str(out.get("description_ko") or "").split("\n") if l.strip()]
            if ok and len(ko_lines) == len(batch):
                for (t, _pre), ko in zip(batch, ko_lines):
                    mapping[t] = _kp.polish_ko(ko) or ko
                provider, translated = prov, True
            else:
                tries = " · ".join(f"{a.get('provider')}: {('건너뜀 ' if a.get('skipped') else '')}{str(a.get('error') or '실패')[:120]}"
                                   for a in (out.get("attempts") or []) if not a.get("ok"))
                if prov == "stub":
                    why = "설정된 번역기 없음(번역 키 0개 — 원문 유지)"
                elif ok:
                    why = (f"{prov} 응답 줄 수 어긋남(보낸 {len(batch)}줄 · 받은 {len(ko_lines)}줄) — "
                           f"응답 원문 「{str(out.get('description_ko') or '')[:160]}」")
                else:
                    why = f"번역기 실패({prov}) — " + (tries or str(out.get("translate_error") or out.get("error") or "사유 없음")[:200])
                for t, _pre in batch:
                    diag[t] = why
        for t in uniq:
            mapping.setdefault(t, t)                # 못 옮긴 값은 원문 그대로(가짜 번역 0) — 등록 단계가 값 단위로 보류
        out_opts = []
        for o in opts:
            nm = str(o.get("name") or "").strip()
            vals = [str(v or "").strip() for v in (o.get("values") or ([o.get("value")] if o.get("value") is not None else [])) if str(v or "").strip()]
            out_opts.append({
                "name": nm, "name_ko": mapping.get(nm, nm),
                "values": vals, "values_ko": [mapping.get(v, v) for v in vals]})
        return {"options": out_opts, "provider": provider, "translated": translated, "diag": diag}

    def _translate_mymemory(self, title: str, description: str) -> dict:
        """v87-W7: MyMemory 무료 번역 API(무키·무가입). 제목·상세 각각 요청, 한국어로.
        실패(HTTP·쿼터·파싱)면 error를 담아 반환 → 체인이 다음 프로바이더로 폴백."""
        import requests as _req

        src = _route_src_lang((title or "") + " " + (description or ""))
        if src == "ko":   # 이미 한국어면 번역 불필요(원문 유지, 실패 아님이지만 체인상 성공 처리).
            _record_translate(True, provider="mymemory")
            return {"title_ko": title, "description_ko": description, "provider": "mymemory",
                    "copy_coupang": self._copy_template(title, "coupang"),
                    "copy_smartstore": self._copy_template(title, "smartstore"),
                    "copy_11st": self._copy_template(title, "11st")}

        _mm_src = {"zh": "zh-CN"}.get(src, src)      # R0: 중국어는 zh-CN(전엔 ja로 갔다)

        def _one(text: str) -> str:
            text = (text or "").strip()
            if not text:
                return text
            # MyMemory 단일 요청 상한(약 500자) — 초과분은 그대로 두지 않고 문장 경계로 잘라 앞부분만(정직: 부분).
            snippet = text[:480]
            r = _req.get("https://api.mymemory.translated.net/get",
                         params={"q": snippet, "langpair": f"{_mm_src}|ko"}, timeout=self._clamp_timeout(12))
            r.raise_for_status()
            j = r.json()
            if int(j.get("responseStatus") or 0) != 200:
                raise RuntimeError(f"MyMemory 응답 상태 {j.get('responseStatus')}")
            out = ((j.get("responseData") or {}).get("translatedText") or "").strip()
            if not out:
                raise RuntimeError("MyMemory 빈 응답")
            # 원문보다 길어진 미번역 잔여(원문 그대로 반환류)면 원문 유지.
            return out if out and out.lower() != snippet.lower() else text

        try:
            title_ko = _one(title) or title
            description_ko = _one(description) or description
            _record_translate(True, provider="mymemory")
            return {"title_ko": title_ko, "description_ko": description_ko, "provider": "mymemory",
                    "copy_coupang": self._copy_template(title_ko, "coupang"),
                    "copy_smartstore": self._copy_template(title_ko, "smartstore"),
                    "copy_11st": self._copy_template(title_ko, "11st")}
        except Exception as exc:
            reason = record_translate_failure(exc, "mymemory")   # v87-W7a: 원 응답 코드·바디까지 계측 적재
            logger.warning("MyMemory 번역 실패(%s): %s", reason, exc)
            return {"title_ko": title, "description_ko": description,
                    "provider": "mymemory-fallback", "error": reason}

    def generate_marketplace_copy(self, product: dict, marketplace: str) -> str:
        """마켓별 톤앤매너에 맞는 광고 카피 생성.

        Args:
            product: {"title": str, "description": str, ...}
            marketplace: "coupang" | "smartstore" | "11st"

        Returns:
            광고 카피 문자열
        """
        title = product.get("title", "")
        hint = _MARKET_PROMPTS.get(marketplace, "간결하게 작성.")

        if self.provider == "openai" and not _dry_run():
            return self._copy_openai(title, marketplace, hint)
        if self.provider == "deepl" and not _dry_run():
            # DeepL은 번역만 지원 — 카피는 template 기반
            return self._copy_template(title, marketplace)

        return self._copy_template(title, marketplace)

    def generate_description(self, product: dict) -> dict:
        """v39-E2 #3: 상세설명이 없거나 빈약할 때 한국어 상세 '초안'을 생성.

        입력: {title, category, specs:[(label,value)], options, description, brand}
        출력: {"text", "provider": "openai"|"stub", "is_draft": True, "draft_status", "draft_error", "ai_call"}
        - Y7-J(오너 2026-10-10): **문장형** — 상품 한 줄 소개 → 특징 3~5문장(소재·실루엣·착용 상황 — 옵션·카테고리·원문
          상세에서만) → 사이즈·세탁 안내(해당 시). 제목 낱말 나열 금지·상표 금지. 키워드는 넣지 않는다(옛 번역 제목을
          낱말로 자른 값이라 나열을 부른다 — 13802276439 「■ 특징 · 미야케 · 아키라의 …」).
        - `ai_call` = 실제로 부른 기록 `{called, model, prompt, status, error, response_head}`(키 없으면 called False).
        - OPENAI 키 미설정/dry-run/실패 시 provider="stub" — 확인된 정보만 문장으로(`_structured_draft`).
        """
        from src.collectors import ko_polish as _kp
        title = _kp.strip_marks((product.get("title") or "").strip())[0]
        category = (product.get("category") or "").strip()
        brand = _kp.strip_marks((product.get("brand") or "").strip())[0]

        # v87-W5: 입력 전처리 — 마켓 UI 쓰레기(레ビュー·신고·송료무료 등)를 스펙에서 제거한 뒤 초안에 넣는다.
        keywords = _clean_keywords_for_draft(product.get("keywords") or [])   # 호환 인자(초안엔 쓰지 않음)
        specs = _clean_specs_for_draft(product.get("specs") or [])
        options = product.get("options") or []
        description = str(product.get("description") or "").strip()   # v87-W7 item4: 원문 상세 라인 보존용

        # v87-W7a: 키 부재 vs 키 있으나 호출 실패를 **구분**한다 — draft_status 3분.
        from src.utils.env import env_present
        draft_status = "no_openai_key"
        draft_error = ""
        draft_code = ""
        ai_call = {"called": False, "model": "", "prompt": "", "status": None, "error": "", "response_head": ""}
        if env_present("OPENAI_API_KEY") and not _dry_run():
            try:
                _res = self._describe_openai(title, category, specs, keywords, brand,
                                             options=options, description=description, trace=ai_call)
                _record_translate(True, provider="openai-draft")
                _res["text"] = _kp.gate_lines(_res.get("text") or "")[0]   # 모델이 상표를 써도 그 줄은 뺀다
                _res.setdefault("draft_status", "openai")
                _res["ai_call"] = ai_call
                return _res
            except Exception as exc:
                full = failure_line(exc, "openai-draft")          # Y5: 사유·HTTP·재시도·원문 한 줄(계측 적재 포함)
                draft_status = "openai_error"
                draft_code = classify_translate_reason(exc)[0]
                # Y7-K(오너 2026-10-10): 화면엔 한국어 사유만 — 영문 원문은 관리자 로그·`ai_call`(관리 기록)에만
                draft_error = draft_user_line(draft_code, raw_error_meta(exc)[0])
                ai_call["error"] = full
                ai_call["code"] = draft_code
                logger.warning("AI 상세 생성 실패(%s) — 구조화 폴백(키 있음, 호출 실패): %s", full, exc)

        return {"text": _structured_draft(title, category, keywords, specs, options, brand, description),
                "provider": "stub", "is_draft": True, "draft_code": draft_code,
                "draft_status": draft_status, "draft_error": draft_error, "ai_call": ai_call}

    @staticmethod
    def draft_prompt(title, category, specs, brand, *, options=None, description="") -> str:
        """AI 상세 초안 프롬프트 — 한 자리(보고·테스트가 같은 글을 본다)."""
        cat_label = _CAT_LABEL.get(category, category)
        opt_lines = []
        for o in options or []:
            if not isinstance(o, dict):
                continue
            nm = str(o.get("name_ko") or o.get("name") or "").strip()
            vals = [str((v.get("ko") or v.get("src")) if isinstance(v, dict) else v).strip()
                    for v in (o.get("values_ko") or o.get("values") or [])]
            vals = [v for v in vals if v]
            if nm and vals:
                opt_lines.append(f"- {nm}: {', '.join(vals[:12])}")
        spec_txt = "\n".join(f"- {l}: {v}" for l, v in specs[:20]) or "(스펙 표 없음)"
        src = "\n".join(draft_source_lines(description, title)[:30]) or "(원문 상세 없음)"
        return (
            "다음 상품의 한국어 상세설명 '초안'을 작성하세요.\n"
            "입력 정보(상품명·옵션·스펙·원문 상세)가 외국어(일본어·중국어 등)일 수 있습니다. **결과물은 처음부터 끝까지 "
            "자연스러운 한국어 판매 문안**으로 작성하고, 원문 언어 조각을 남기거나 스펙 라벨·값을 기계 번역기 말투로 "
            "직역하지 마세요. 쇼핑몰 UI 문구(리뷰/후기/신고/장바구니/찜/쿠폰/포인트/배송 배너·가게 평점·발송 시간 등)는 "
            "상품 정보가 아니므로 **무시**하세요.\n"
            "구성(이 순서, 문장형):\n"
            "1) 상품 한 줄 소개 — 한 문장.\n"
            "2) 특징 3~5개 — 한 줄에 한 문장. 소재·실루엣(모양)·구성·착용/사용 상황을 **아래 옵션·카테고리·원문 상세에서만** "
            "추론하세요. 거기에 없는 사실(소재 이름·수치·인증·원산지·효능)은 절대 지어내지 마세요(모르면 쓰지 않음).\n"
            "3) 사이즈·세탁 안내 — 의류·잡화처럼 해당될 때만 1~2문장(옵션의 사이즈 표기를 기준으로, 세탁은 라벨 안내).\n"
            "금지: 상품명을 낱말로 쪼개 나열하기 · 상표·브랜드명(디자이너 이름 포함) · 마켓 금지어(최고/최상/유일/100%/완벽/"
            "의학·과학 효능 단정) · 이모지·해시태그 · AI 특유의 정형 문장·번역체 · 「여러분」「~를 소개합니다」 같은 진부한 도입 · "
            "감탄 남발.\n"
            "톤: 공손하되 군더더기 없는 큐레이터 높임말, 사람이 직접 쓴 것처럼 짧고 구체적인 문장.\n\n"
            f"상품명: {title}\n카테고리: {cat_label or '(미상)'}\n"
            f"옵션:\n{chr(10).join(opt_lines) or '(옵션 없음)'}\n"
            f"스펙:\n{spec_txt}\n"
            f"원문 상세:\n{src}\n"
        )

    def _describe_openai(self, title, category, specs, keywords, brand, *, options=None, description="",
                         trace=None) -> dict:
        import requests as _req
        import time as _time
        # v87-W10 item2: AI 초안도 요청 경로 — 워커 보호 예산(기본 8초)로 timeout 클램프.
        if getattr(self, "_deadline", None) is None:
            try:
                _b = float(os.getenv("TRANSLATE_REQUEST_BUDGET_SEC", "8") or "8")
            except (TypeError, ValueError):
                _b = 8.0
            self._deadline = _time.time() + max(1.0, _b)
        api_key = __import__("src.utils.env", fromlist=["env_str"]).env_str("OPENAI_API_KEY")
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        prompt = self.draft_prompt(title, category, specs, brand, options=options, description=description)
        trace = trace if trace is not None else {}
        trace.update(called=True, model=model, prompt=prompt)
        # Y5: AI 초안도 서버 월 예산(AI_MONTHLY_BUDGET_USD)에 묶고, 429는 백오프 1회 재시도(번역 체인과 같은 규칙).
        from decimal import Decimal as _D
        from src.ai.budget import BudgetGuard, BudgetExceededError
        _guard = BudgetGuard()
        if not _guard.can_spend(estimated_cost_usd=_D(str(len(prompt))) * _OPENAI_IN_USD + _D("900") * _OPENAI_OUT_USD):
            raise BudgetExceededError(_guard.summary())
        try:
            resp = _post_with_429_retry(
                _req, "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.4},
                timeout=self._clamp_timeout(20),
            )
        except Exception as exc:
            st, body = raw_error_meta(exc)
            trace.update(status=st, response_head=str(body or "")[:500])
            raise
        trace["status"] = getattr(resp, "status_code", 200)
        text = resp.json()["choices"][0]["message"]["content"].strip()
        trace["response_head"] = text[:500]
        return {"text": text, "provider": "openai", "is_draft": True}

    # ------------------------------------------------------------------
    # 내부 구현
    # ------------------------------------------------------------------

    def _translate_openai(self, title: str, description: str, *, style: str = "") -> dict:
        """OpenAI GPT-4o-mini로 번역 + 카피 생성."""
        try:
            import requests as _req
            api_key = __import__("src.utils.env", fromlist=["env_str"]).env_str("OPENAI_API_KEY")
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            # v60 STEP3: 이커머스 특화 프롬프트(직역투·음차 박멸). 브랜드/모델/규격 원문 보존, 자연 판매 문체.
            system = (
                "당신은 해외 상품을 한국 오픈마켓(쿠팡·스마트스토어)에 등록하는 전문 상품 번역가입니다. "
                "다음 규칙을 반드시 지키세요.\n"
                "1) 브랜드명·모델명·규격(치수·용량·재질·호환 기종 예: MagSafe, iPhone 15)은 **원문 그대로 보존**"
                " — 억지 음차(예: 안도빌)·직역 금지.\n"
                "2) 마케팅 수식어(ultra-thin, premium 등)는 **자연스러운 한국어 판매 문체**로(예: 초슬림, 프리미엄).\n"
                "3) 단위 변환 금지(inch·mm·g 원문 단위 유지). 없는 스펙 창작 금지.\n"
                "4) 상품명은 한국 관례 **브랜드 + 핵심 스펙 + 용도** 순, 자연스러운 명사구(어색한 조사·번역기 말투 금지).\n"
                "5) 설명은 원문 불릿(·) 구조를 유지하며 한국어로."
            )
            if style:
                # D3-4 ④ — 호출부가 준 문체 지시(예: 상품 이미지 광고 카피체). 규칙 뒤에 붙인다.
                system += "\n6) 문체: " + str(style)
            prompt = (
                "아래 상품을 위 규칙대로 한국어로 번역하고, 마켓용 판매 카피도 만드세요.\n"
                f"[제목]\n{title}\n\n[설명]\n{description}\n\n"
                "JSON으로만 답변:\n"
                '{"title_ko":"브랜드+핵심스펙+용도 자연문","description_ko":"불릿 유지 한국어",'
                '"copy_coupang":"...","copy_smartstore":"...","copy_11st":"..."}'
            )
            # v87-W6 item 2 근원: max_tokens=900 고정이 **긴 상세(일본어 721자 등) + 제목 + 마켓 카피 3종**을
            #   한 JSON으로 뽑을 때 출력이 잘려 json.loads 실패 → openai-fallback(원문 유지)로 '조용한 실패 다발'
            #   이었다. 입력 길이에 비례해 상한을 잡고(캡 3000 — AI 예산 존중), 타임아웃도 길이 대응해 늘린다.
            _in_len = len(title) + len(description)
            _max_tokens = max(900, min(3000, 1000 + _in_len))
            _timeout = 30 if _in_len > 400 else 15
            payload = {
                "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
                "max_tokens": _max_tokens,
                "response_format": {"type": "json_object"},
            }
            # R0(오너 2026-10-01): 번역 체인의 OpenAI 호출도 **서버 월 예산(AI_MONTHLY_BUDGET_USD)**에 묶는다.
            #   실측: 이 함수는 예산을 확인하지도 기록하지도 않았다 — 카피·CS 봇만 묶여 있었다.
            #   넘었으면 부르지 않고(BudgetExceededError → 사유 「서버 월 예산」) 다음 단(MyMemory)으로.
            from decimal import Decimal as _D
            from src.ai.budget import BudgetGuard, BudgetExceededError
            _guard = BudgetGuard()
            _est = _D(str(_in_len)) * _OPENAI_IN_USD + _D(str(_max_tokens)) * _OPENAI_OUT_USD
            if not _guard.can_spend(estimated_cost_usd=_est):
                raise BudgetExceededError(_guard.summary())
            resp = _post_with_429_retry(   # v87-W8 item4: 429면 짧은 백오프 1회 재시도
                _req, "https://api.openai.com/v1/chat/completions",
                headers=headers, json=payload, timeout=self._clamp_timeout(_timeout),
            )
            _j = resp.json()
            _usage = _j.get("usage") or {}
            _pt, _ct = int(_usage.get("prompt_tokens") or 0), int(_usage.get("completion_tokens") or 0)
            try:
                _guard.record(cost_usd=_D(str(_pt)) * _OPENAI_IN_USD + _D(str(_ct)) * _OPENAI_OUT_USD,
                              provider="openai", tokens=_pt + _ct, note="translate")
            except Exception as _e:
                logger.warning("[번역 체인] OpenAI 비용 기록 실패: %s", _e)
            content = _j["choices"][0]["message"]["content"]
            import json
            result = json.loads(content)
            result["provider"] = "openai"
            _record_translate(True, provider="openai")   # v87-W6 계측
            return result
        except Exception as exc:
            reason = record_translate_failure(exc, "openai")   # v87-W7a: 원 응답 코드·바디까지 계측 적재
            logger.warning("OpenAI 번역 실패(%s): %s", reason, exc)   # v64 STEP6: 원인 로깅(무음 금지)
            return {
                "title_ko": title,
                "description_ko": description,
                "copy_coupang": f"[openai-fallback] {title}",
                "copy_smartstore": f"[openai-fallback] {title}",
                "copy_11st": f"[openai-fallback] {title}",
                "provider": "openai-fallback",
                "error": reason,
            }

    def _translate_deepl(self, title: str, description: str) -> dict:
        """DeepL로 번역 (카피는 template 기반)."""
        try:
            import requests as _req
            api_key = __import__("src.utils.env", fromlist=["env_str"]).env_str("DEEPL_API_KEY")
            base_url = (
                "https://api-free.deepl.com/v2/translate"
                if api_key.endswith(":fx")
                else "https://api.deepl.com/v2/translate"
            )
            params = {
                "auth_key": api_key,
                "text": [title, description],
                "target_lang": "KO",
            }
            resp = _req.post(base_url, data=params, timeout=self._clamp_timeout(10))
            resp.raise_for_status()
            translations = resp.json().get("translations", [])
            title_ko = translations[0]["text"] if len(translations) > 0 else title
            description_ko = translations[1]["text"] if len(translations) > 1 else description
            _record_translate(True, provider="deepl")   # v87-W6 계측
            return {
                "title_ko": title_ko,
                "description_ko": description_ko,
                "copy_coupang": self._copy_template(title_ko, "coupang"),
                "copy_smartstore": self._copy_template(title_ko, "smartstore"),
                "copy_11st": self._copy_template(title_ko, "11st"),
                "provider": "deepl",
            }
        except Exception as exc:
            reason = record_translate_failure(exc, "deepl")   # v87-W7a: 원 응답 코드·바디까지 계측 적재
            logger.warning("DeepL 번역 실패(%s): %s", reason, exc)   # v64 STEP6: 원인 로깅(무음 금지)
            return {
                "title_ko": title,
                "description_ko": description,
                "copy_coupang": f"[deepl-fallback] {title}",
                "copy_smartstore": f"[deepl-fallback] {title}",
                "copy_11st": f"[deepl-fallback] {title}",
                "provider": "deepl-fallback",
                "error": reason,
            }

    def _translate_papago(self, title: str, description: str) -> dict:
        """v87-W7 회수: 네이버 클라우드(NCP) Papago NMT — 공식 엔드포인트. ko·ja·zh 도메인 최적.
        env: NCP_PAPAGO_CLIENT_ID / NCP_PAPAGO_CLIENT_SECRET. 실패면 error 담아 체인 폴백."""
        import requests as _req
        _env = __import__("src.utils.env", fromlist=["env_str"])
        cid = _env.env_str("NCP_PAPAGO_CLIENT_ID")
        secret = _env.env_str("NCP_PAPAGO_CLIENT_SECRET")
        src = _route_src_lang((title or "") + " " + (description or ""))
        if src == "ko":   # 이미 한국어 → 번역 불필요(성공 처리, 원문 유지).
            _record_translate(True, provider="papago")
            return {"title_ko": title, "description_ko": description, "provider": "papago",
                    "copy_coupang": self._copy_template(title, "coupang"),
                    "copy_smartstore": self._copy_template(title, "smartstore"),
                    "copy_11st": self._copy_template(title, "11st")}
        headers = {"x-ncp-apigw-api-key-id": cid, "x-ncp-apigw-api-key": secret}
        # R0: 중국어는 `zh-CN`으로 보낸다(전엔 ja로 판정돼 `source=ja`로 갔다). Papago 언어 코드 표기.
        papago_src = {"zh": "zh-CN"}.get(src, src)
        # R0 비용 가드: 오늘(UTC) 몫이 모자라면 부르지 않고 다음 단(DeepL)으로 — 지출 상한, 실패 아님.
        need = len((title or "").strip()[:4900]) + len((description or "").strip()[:4900])
        if not _papago_take(need):
            limit = papago_daily_limit()
            logger.info("[번역 체인] Papago 오늘 상한(%s자) — 이번 %s자는 다음 번역기로", limit, need)
            return {"title_ko": title, "description_ko": description, "provider": "papago-fallback",
                    "error": f"Papago 오늘 사용 상한({limit:,}자) — 다음 번역기로", "skipped": True}

        def _one(text: str) -> str:
            text = (text or "").strip()
            if not text:
                return text
            r = _req.post("https://papago.apigw.ntruss.com/nmt/v1/translation",
                          headers=headers, data={"source": papago_src, "target": "ko", "text": text[:4900]},
                          timeout=self._clamp_timeout(10))
            r.raise_for_status()
            out = (((r.json() or {}).get("message") or {}).get("result") or {}).get("translatedText", "")
            if not out:
                raise RuntimeError("Papago 빈 응답")
            return out
        try:
            title_ko = _one(title) or title
            description_ko = _one(description) or description
            _record_translate(True, provider="papago")
            return {"title_ko": title_ko, "description_ko": description_ko, "provider": "papago",
                    "copy_coupang": self._copy_template(title_ko, "coupang"),
                    "copy_smartstore": self._copy_template(title_ko, "smartstore"),
                    "copy_11st": self._copy_template(title_ko, "11st")}
        except Exception as exc:
            reason = record_translate_failure(exc, "papago")   # v87-W7a: 원 응답 코드·바디까지 계측 적재
            logger.warning("Papago 번역 실패(%s): %s", reason, exc)
            # R0: NCP가 한도 초과로 거절(429 + quota/limit)하면 오늘은 더 안 부른다 — 다음 호출부터 바로 DeepL.
            _st, _body = raw_error_meta(exc)
            if _st == 429 and re.search(r"quota|limit|한도|사용량", _body or "", re.I):
                _papago_exhaust_today()
            return {"title_ko": title, "description_ko": description,
                    "provider": "papago-fallback", "error": reason}

    def _translate_azure(self, title: str, description: str) -> dict:
        """v87-W7 회수: Azure Translator(Cognitive Services) — 공식 엔드포인트, 소스 자동 감지.
        env: AZURE_TRANSLATOR_KEY (+ AZURE_TRANSLATOR_REGION, 지역 리소스면 필수). 실패면 체인 폴백."""
        import requests as _req
        _env = __import__("src.utils.env", fromlist=["env_str"])
        key = _env.env_str("AZURE_TRANSLATOR_KEY")
        region = _env.env_str("AZURE_TRANSLATOR_REGION")
        headers = {"Ocp-Apim-Subscription-Key": key, "Content-Type": "application/json"}
        if region:
            headers["Ocp-Apim-Subscription-Region"] = region
        try:
            r = _req.post("https://api.cognitive.microsofttranslator.com/translate",
                          params={"api-version": "3.0", "to": "ko"}, headers=headers,
                          json=[{"Text": title or ""}, {"Text": description or ""}], timeout=self._clamp_timeout(10))
            r.raise_for_status()
            data = r.json()

            def _pick(i, fallback):
                try:
                    return (data[i].get("translations") or [{}])[0].get("text") or fallback
                except (IndexError, AttributeError, KeyError):
                    return fallback
            title_ko = _pick(0, title)
            description_ko = _pick(1, description)
            _record_translate(True, provider="azure")
            return {"title_ko": title_ko, "description_ko": description_ko, "provider": "azure",
                    "copy_coupang": self._copy_template(title_ko, "coupang"),
                    "copy_smartstore": self._copy_template(title_ko, "smartstore"),
                    "copy_11st": self._copy_template(title_ko, "11st")}
        except Exception as exc:
            reason = record_translate_failure(exc, "azure")   # v87-W7a: 원 응답 코드·바디까지 계측 적재
            logger.warning("Azure 번역 실패(%s): %s", reason, exc)
            return {"title_ko": title, "description_ko": description,
                    "provider": "azure-fallback", "error": reason}

    def _copy_openai(self, title: str, marketplace: str, hint: str) -> str:
        """OpenAI로 마켓별 카피 생성."""
        try:
            import requests as _req
            import json
            api_key = __import__("src.utils.env", fromlist=["env_str"]).env_str("OPENAI_API_KEY")
            prompt = f"상품명: {title}\n마켓: {marketplace}\n조건: {hint}\n광고 카피 1개만 작성."
            payload = {
                "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.5,
                "max_tokens": 200,
            }
            resp = _req.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
        except Exception as exc:
            logger.warning("OpenAI 카피 생성 실패: %s", exc)
            return self._copy_template(title, marketplace)

    @staticmethod
    def _copy_template(title: str, marketplace: str) -> str:
        """키 없을 때 template 기반 카피 생성."""
        templates = {
            "coupang": f"✅ {title} | 빠른 배송 | 최저가 보장 | 로켓배송 가능",
            "smartstore": (
                f"{title}\n"
                "정품 보장 · 당일 발송 · 무료 교환\n"
                "네이버 쇼핑 최저가 도전"
            ),
            "11st": f"[특가] {title} — 지금 구매하면 최대 할인!",
        }
        return templates.get(marketplace, f"{title} — 구매 추천")
