"""Y6-C A3(오너 2026-10-07 21:17 KST, 가족 폰 · 1225 CNY 「이식 현대 디자이너 소파 의자 … Desede 회전식 1인용 의자」).

- 용어집: 意式→이탈리안 스타일(번역기가 한자음 「이식」으로 옮겼다) · 北欧→북유럽 스타일 · 轻奢→럭셔리 · 创意→디자인 · 休闲→캐주얼.
  원문에 그 한자가 **있을 때만** 고친다(다른 상품의 「캐주얼한」·「창의적」은 그대로).
- 轻奢는 판촉어 삭제 목록에서 뺐다(지우지 않고 「럭셔리」로).
- 원제목 표시에도 상표 게이트: Desede(De Sede 레플리카)·임스·迪奥·星际穿越… → 「확인 필요」. 호환 표기(MagSafe)는 그대로.
"""
from __future__ import annotations

import json

import pytest

SRC = "意式现代设计师沙发椅 Desede 旋转单人椅"


@pytest.mark.parametrize("cn, ko, right", [
    ("意式现代设计师沙发椅", "이식 현대 디자이너 소파 의자", "이탈리안 스타일 현대 디자이너 소파 의자"),
    ("北欧实木餐桌", "북유럽풍 원목 식탁", "북유럽 스타일 원목 식탁"),
    ("轻奢床头柜", "가벼운 사치 침대 협탁", "럭셔리 침대 협탁"),
    ("创意落地灯", "창의적인 스탠드 조명", "디자인 스탠드 조명"),
    ("休闲椅", "레저 의자", "캐주얼 의자"),
])
def test_glossary_rows(cn, ko, right):
    from src.collectors.ko_polish import title_fix
    assert title_fix(ko, cn) == right


def test_glossary_only_when_source_has_the_han():
    from src.collectors.ko_polish import title_fix
    assert title_fix("창의적인 레저 의자", "折叠椅") == "창의적인 레저 의자"           # 원문에 创意·休闲 없음 → 손대지 않음


def test_qingshe_kept_for_translation_not_deleted():
    from src.collectors import ko_polish as K
    r = K.rules()
    assert "轻奢" not in r["delete_cn"]
    assert "轻奢" in K.strip_cn("轻奢床头柜")                                    # 번역기에 그대로 간다 → 용어집이 「럭셔리」로
    assert dict((a, b) for a, b in r["replace"])["北欧风"] == "북유럽 스타일"


def test_desede_is_a_replica_mark_and_title_drops_it():
    from src.collectors import ko_polish as K
    assert K.replica_hits(SRC) == ["디세데"]
    assert "Desede" not in K.trademark_fix("이탈리안 스타일 소파 의자 Desede 회전식 1인용 의자")


@pytest.mark.parametrize("raw, shown", [
    (SRC, "意式现代设计师沙发椅 「확인 필요」 旋转单人椅"),
    ("DESEDE DS-600 sofa", "「확인 필요」 DS-600 sofa"),                         # 대소문자 무관(라틴)
    ("伊姆斯 Eames 躺椅", "「확인 필요」 躺椅"),                                     # 이웃한 두 표기는 한 번만
    ("星际穿越 黑洞小夜灯", "「확인 필요」 黑洞小夜灯"),                               # IP
    ("MagSafe 磁吸支架", "MagSafe 磁吸支架"),                                      # 호환 표기는 가리지 않는다
    ("", ""),
])
def test_mask_marks(raw, shown):
    from src.collectors.ko_polish import mask_marks
    assert mask_marks(raw) == shown


def test_editor_shows_masked_original_title():
    from src.seller_console import collect_history_store as S
    iid = S.append(source="share", url="https://item.taobao.com/item.htm?id=511822926875", seller_id="y6c-a3",
                   title="이탈리안 스타일 현대 디자이너 소파 의자 회전식 1인용 의자", price="1225", currency="CNY",
                   extra={"title": SRC, "title_ko": "이탈리안 스타일 현대 디자이너 소파 의자 회전식 1인용 의자",
                          "price": "1225", "currency": "CNY", "images": ["https://img.alicdn.com/a.jpg"]})
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "y6c-a3"
    h = c.get(f"/seller/collect/preview/{iid}").get_data(as_text=True)
    line = [ln for ln in h.splitlines() if "const _ORIG_TITLE_SHOWN" in ln][0]
    shown = json.loads(line.split("=", 1)[1].strip().rstrip(";"))
    assert shown == "意式现代设计师沙发椅 「확인 필요」 旋转单人椅" and "Desede" not in line
    seg = h[h.index("function restoreOrigTitle()"):h.index("function initEditor()")]
    assert "_ORIG_TITLE_SHOWN" in seg and "_EXTRA.title" not in seg                # 되돌리기도 가린 글로만
