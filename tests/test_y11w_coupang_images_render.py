"""Y11-W(오너 2026-10-16 23:56~00:00) — 쿠팡 「기타이미지 경로가 잘못되어」 · 네이버 규격 내수 키 · 옵션 사진 렌더(배지 반쪽 문구 · 작은 장식 글자)."""
import io
import json

import pytest


# ── 1. 쿠팡 상세 갱신: 기타 사진은 쿠팡이 준 그대로 ─────────────────────────────────────────────────────────────

def test_patch_items_keeps_coupang_image_fields_as_returned():
    from src.services import coupang_detail_refresh as R
    live_imgs = [
        {"imageOrder": 0, "imageType": "REPRESENTATION", "cdnPath": "vendor_inventory/aaa/rep.jpg",
         "vendorPath": "https://res.cloudinary.com/x/old.jpg"},
        {"imageOrder": 1, "imageType": "DETAIL", "cdnPath": "vendor_inventory/bbb/d1.jpg", "vendorPath": ""},
        {"imageOrder": 2, "imageType": "DETAIL", "cdnPath": "vendor_inventory/ccc/d2.jpg",
         "vendorPath": "https://img.alicdn.com/d2.jpg"},
    ]
    body = {"items": [{"externalVendorSku": "s1", "salePrice": 100, "originalPrice": 100, "images": [dict(x) for x in live_imgs]}]}
    out = R.patch_items(body, {"contents": [], "sku_images": {"s1": "https://res.cloudinary.com/x/ko.jpg"}})
    imgs = body["items"][0]["images"]
    assert imgs[0] == {"imageOrder": 0, "imageType": "REPRESENTATION", "vendorPath": "https://res.cloudinary.com/x/ko.jpg"}
    # 예전: {"vendorPath": "vendor_inventory/bbb/d1.jpg"} — 상대 경로를 절대 주소 칸에 넣어 「기타이미지 경로가 잘못되어」
    assert imgs[1] == {"imageOrder": 1, "imageType": "DETAIL", "cdnPath": "vendor_inventory/bbb/d1.jpg", "vendorPath": ""}
    assert imgs[2]["cdnPath"] == "vendor_inventory/ccc/d2.jpg" and imgs[2]["vendorPath"] == "https://img.alicdn.com/d2.jpg"
    s = out["sent"][0]
    assert s["sku"] == "s1" and s["n"] == 3
    assert s["images"][1] == {"type": "DETAIL", "cdn": True, "vendor": "", "ext": "", "query": False, "len": 0}
    assert s["images"][0]["vendor"] == "res.cloudinary.com" and s["images"][0]["ext"] == "jpg"


def test_refresh_hash_changes_with_image_patch_version():
    """이미 보낸 등록본(옛 재구성)도 다음 갱신 때 다시 나간다."""
    from src.services import coupang_detail_refresh as R
    assert R._hash({"contents": [], "sku_images": {}, "list_price": "markup:15"}) != \
        R._hash({"contents": [], "sku_images": {}, "list_price": "markup:15", "img": 2})


def test_coupang_enqueue_never_raises(monkeypatch):
    from src.services import coupang_detail_refresh as R
    monkeypatch.setattr(R, "queue_rows", lambda: (_ for _ in ()).throw(RuntimeError("db down")))
    assert R.enqueue_item("it", {"uploaded": [{"market": "coupang:gogane", "product_id": "1"}]}, "u") == 0


# ── 3. 네이버 상세 규격: 중국 내수 속성 키 ──────────────────────────────────────────────────────────────────────

VRSUK_SPEC = ("参数信息\n\n金属\n框架材质\n安装方式\n是\n总长\n83cm\n是否可预售\n是\n是否可拆换\n否\n包装体积\n100x88x62cm\n"
              "是否可定制\n是\n安装说明详情\n提供安装说明视频\n图案\n抽象\n出租车是否可运输\n否\n"
              "可送货/安装\n佛山市 郑州市 贵阳市 广州市 福州市 哈尔滨市 全国 其他\n品牌\nvrsuk")


def test_domestic_attribute_keys_are_dropped_with_their_values():
    from src.uploaders import detail_ui_junk as J
    r = J.strip_page_ui(VRSUK_SPEC)
    assert r["domestic"] == ["安装方式", "是否可预售", "是否可拆换", "是否可定制", "安装说明详情", "出租车是否可运输", "可送货/安装"]
    body = r["text"]
    for gone in ("是否可", "出租车", "佛山市", "可送货", "提供安装说明视频"):
        assert gone not in body
    for kept in ("框架材质", "总长", "83cm", "包装体积", "100x88x62cm", "图案", "品牌", "vrsuk"):
        assert kept in body


def test_spec_key_lines_are_never_domestic():
    from src.uploaders import detail_ui_junk as J
    assert not J.is_domestic_key("材质")
    assert not J.is_domestic_key("尺寸 是否可定制 82cm 材质 皮革 很长的一行规格说明文字")
    assert J.is_city_list("北京 上海 天津 重庆")
    assert not J.is_city_list("金属 实木 皮革")


# ── 4. 옵션 사진 렌더 — 배지 반쪽 문구 · 작은 장식 글자(원본 되살림) ───────────────────────────────────────────────

def test_ban_cut_and_tiny_latin_rules():
    from src.services import image_polish as P
    assert P.ban_cut({"why": "금지어·과장(보장)", "ko": "정품", "tgt": "정품 보장"})
    assert not P.ban_cut({"why": "", "ko": "정품", "tgt": "정품 보장"})
    assert not P.ban_cut({"why": "금지어·과장(최고)", "ko": "고급 소재 의자", "tgt": "최고급 소재 의자"})
    size = [1440, 1440]
    assert P.tiny_latin({"h": 10, "src": "dicen", "tgt": "디센"}, size)                  # 0.7%
    assert P.tiny_latin({"h": 17, "src": "ambustione di pino", "tgt": "리플러 랩에서의 소나무 발포"}, size)
    assert not P.tiny_latin({"h": 35, "src": "italia", "tgt": "이탈리아"}, size)           # 배지 글자(2.4%)
    assert not P.tiny_latin({"h": 10, "src": "正品", "tgt": "정품"}, size)                  # 한자 — 번역 대상
    assert not P.tiny_latin({"h": 10, "src": "82cm", "tgt": "82cm"}, size)                 # 한글 없음 — 텐센트가 옮기지 않음


def test_old_polish_with_half_badge_or_unrestored_tiny_text_is_redone():
    from src.services import image_edit as IE
    from src.services import image_polish as P
    boxes = [{"h": 35, "src": "正品保障", "tgt": "정품 보장"}, {"h": 10, "src": "dicen", "tgt": "디센"}]
    ed = {"by": P.POLISH_BY, "render": "local", "render_v": IE.RENDER_V, "ops": [{"id": "t0", "action": "text", "text": "정품"}]}
    assert P._redo_polish(ed, boxes, [1440, 1440])                                          # 반쪽 배지
    ed2 = {"by": P.POLISH_BY, "render": "local", "render_v": IE.RENDER_V, "ops": []}
    assert P._redo_polish(ed2, boxes, [1440, 1440])                                         # 작은 글자 안 되살림
    ed3 = {"by": P.POLISH_BY, "render": "local", "render_v": IE.RENDER_V, "ops": [{"id": "t1", "action": "restore"}]}
    assert not P._redo_polish(ed3, boxes, [1440, 1440])
    assert not P._redo_polish(ed2, boxes, None)                                             # 틀이 다르면(되살릴 수 없으면) 그대로


def _jpeg(color, size=(200, 200)):
    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", size, color).save(b, "JPEG", quality=95)
    return b.getvalue()


def test_render_local_restores_original_pixels():
    pytest.importorskip("cv2")
    from PIL import Image
    from src.services import image_edit as IE
    base, orig = _jpeg((200, 30, 30)), _jpeg((30, 30, 200))
    box = {"x": 50, "y": 50, "w": 40, "h": 10, "src": "dicen", "tgt": "디센"}
    rr = IE.render_local(base, 1.0, [], [], others=[box], restore=[box], orig_raw=orig)
    assert rr["ok"] and rr["restored"] == 1
    im = Image.open(io.BytesIO(rr["bytes"])).convert("RGB")
    r, g, b = im.getpixel((70, 55))
    assert b > 150 and r < 90                                                               # 원본(파랑) 자리
    r2, _g2, b2 = im.getpixel((10, 10))
    assert r2 > 150 and b2 < 90                                                             # 그 밖은 번역본 그대로(빨강)


def test_spec_block_becomes_key_value_lines_and_drops_tags():
    """Y11-W 추가(오너): 규격 블록 「키: 값」 한 줄 · 颜色分类(옵션 뭉침)·流行元素·款式定位 태그 · 내수 속성 짝 제외. 값이 앞이든 뒤든 짝."""
    from src.uploaders import detail_ui_junk as J
    txt = ("金属\n框架材质\n品质奢华型\n款式定位\n手动调节\n调节功能\n风格\n复古怀旧\n总长\n83cm\n"
           "颜色分类\n焦黄[Oilwaxed防水油蜡半皮]带踏 黑色全皮带踏\n流行元素\n藤 异形 刺绣\n是否可定制\n是\n品牌\nvrsuk")
    r = J.strip_page_ui(txt)
    assert r["text"].split("\n") == ["框架材质: 金属", "调节功能: 手动调节", "风格: 复古怀旧", "总长: 83cm", "品牌: vrsuk"]
    assert [k for k in r["domestic"]] == ["款式定位", "颜色分类", "流行元素", "是否可定制"]
    assert r["spec_pairs"] == 5


def test_plain_description_is_untouched_by_pairing():
    from src.uploaders import detail_ui_junk as J
    txt = "편안한 1인 의자예요.\n오일 왁스 가죽을 썼어요.\n거실·서재에 잘 어울려요."
    assert J.strip_page_ui(txt)["text"] == txt
