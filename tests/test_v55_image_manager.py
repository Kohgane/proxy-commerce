"""tests/test_v55_image_manager.py — v55 STEP3: 드로어 이미지 관리 UI + 라이트박스.

썸네일 hover 삭제/대표지정/드래그순서 + '이미지 추가'(URL+미리보기 검증) 1급 + 라이트박스 모달
(원비율 max 80vw/80vh, ESC·배경클릭·←→, 새창 금지). 변경은 '변경사항 저장'과 동일 플로우로 영속.
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")
TPL = Path("src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")
CSS_S6C = Path("src/static/app.css").read_text(encoding="utf-8")
# ★ Stage 6-c(2026-09-03): 이 화면들의 CSS가 템플릿 `<style>`/인라인 → **app.css로 이관**됐다.
#   핀이 보는 건 "그 규칙이 살아 있나"이지 "어느 파일에 있나"가 아니다 — 소스만 갈아끼운다.



def test_gallery_hover_actions_and_drag():
    assert "kgpGalleryDelete" in TPL and "kgpGalleryPrimary" in TPL and "kgpGalleryReorder" in TPL
    assert "draggable" in TPL and "dragstart" in TPL and "drop" in TPL   # 드래그 순서변경
    assert "kgp-gimg-del" in TPL and "kgp-gimg-star" in TPL              # hover 삭제/대표


def test_add_image_first_class_with_preview():
    assert 'id="addImgUrl"' in TPL and "kgpAddImageFromInput" in TPL
    assert 'id="addImgPreview"' in TPL                                    # 미리보기
    assert "이미지 추가" in TPL
    assert "probe.onload" in TPL and "probe.onerror" in TPL              # URL 로드 검증 후 추가


def test_lightbox_no_new_window():
    assert 'id="kgpLightbox"' in TPL and "kgpOpenLightbox" in TPL
    assert "max-width: 80vw" in CSS_S6C and "max-height: 80vh" in CSS_S6C   # 원비율 80vw/80vh
    assert "kgpLbStep" in TPL and "ArrowLeft" in TPL and "ArrowRight" in TPL   # ←→
    assert "Escape" in TPL                                                # ESC 닫기
    assert "kgpLbClose" in TPL and "e.target === lb" in TPL              # 배경 클릭 닫기
    assert "원본 새 탭에서 열기" in TPL                                   # 원본은 보조 링크로만
    # 갤러리·고급 썸네일 클릭이 window.open(새 창) 아님
    assert "window.open(v, '_blank')" not in TPL


def test_model_still_imagerows_for_save():
    # 변경사항 저장 플로우 유지: 모델은 #imageRows(buildProductData가 읽음).
    assert 'id="imageRows"' in TPL and "_kgpImageUrls" in TPL


def test_drawer_renders():
    from src.order_webhook import app
    item = {"id": "x", "title": "책상", "url": "https://t/g-1", "price": "20605", "currency": "KRW",
            "extra_json": '{"images":["https://t/1.jpg","https://t/2.jpg"],"title_ko":"책상"}'}
    with patch("src.seller_console.collect_history_store.get", return_value=item):
        with app.test_client() as c:
            with c.session_transaction() as s:
                s["user_id"] = "u1"; s["email"] = "u1"; s["authenticated"] = True
            assert c.get("/seller/collect/preview/x").status_code == 200
