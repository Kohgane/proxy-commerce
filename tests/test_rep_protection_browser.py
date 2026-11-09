"""Real Chromium review UI, using local transport/storage doubles only.

Before templates are exact 74987b8 files. Captures are UI proof, not live OCR.
CI requires Chromium through the existing KGP_REQUIRE_BROWSER gate.
"""
import json
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from jinja2 import ChoiceLoader, FileSystemLoader
from tests import _pw


@pytest.mark.skipif(not _pw.chromium_hits(), reason='Playwright/chromium 미설치')
@pytest.mark.parametrize('width,height', [(1920, 940), (390, 844)])
def test_review_ui_exact_frame_and_scoped_save(monkeypatch, width, height):
    from flask import render_template_string
    from playwright.sync_api import sync_playwright, expect
    from src.order_webhook import app
    from src.seller_console import views as V, collect_history_store as S
    from src.services import image_edit as IE, rep_protection_review as R

    raw = Path('docs/screens/patrol148/before-d5af2185-p2.jpg').read_bytes()
    ex = {'images': ['https://fixture.test/lamp.jpg'], 'images_ko': [
        {'idx': 0, 'status': 'done', 'use': True, 'url': 'https://fixture.test/lamp.jpg',
         'translated_url': 'https://fixture.test/lamp.jpg'}]}
    monkeypatch.setattr(R, '_secret', lambda: 'review-browser-test-only')
    monkeypatch.setattr(IE, '_fetch', lambda _: raw)
    monkeypatch.setattr(IE, 'plan', lambda *a, **kw: pytest.fail('mutating editor path'))
    monkeypatch.setattr(V, '_is_admin_user', lambda: True)
    monkeypatch.setattr(V, '_check_auth', lambda: True)
    monkeypatch.setattr(V, '_get_owned_item', lambda _: {'extra_json': json.dumps(ex)})
    monkeypatch.setattr(V, '_seller_identities', lambda: {'review-test'})
    monkeypatch.setattr(V, '_image_edit_save', lambda *a, **kw: pytest.fail('market enqueue'))
    saves = []
    monkeypatch.setattr(S, 'save_rep_protection', lambda *a, **kw: saves.append(a) or True)
    client = app.test_client()
    with client.session_transaction() as s:
        s['user_id'] = 'review-test'
    shell = '''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <link rel="stylesheet" href="/static/app.css"><title>H-rep2 검토 UI 계약</title><body>
    <main class="container"><h1>대표 사진 검토</h1><p>저장소 실사진 · 운영 연결 없는 UI 검증</p>
    {% include '_coupang_exposure.html' %}</main></body></html>'''
    loader = app.jinja_env.loader
    with app.test_request_context('/'):
        after = render_template_string(shell, is_admin=True, cpx_item_id='fixture')
        try:
            app.jinja_env.loader = ChoiceLoader([FileSystemLoader('tests/fixtures/hrep2_review'), loader])
            app.jinja_env.cache.clear()
            before = render_template_string(shell, is_admin=True, cpx_item_id='fixture')
        finally:
            app.jinja_env.loader = loader
            app.jinja_env.cache.clear()
    captures = Path('artifacts/hrep2-review'); captures.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=_pw.chromium_hits()[0])
        page = browser.new_page(viewport={'width': width, 'height': height})
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        def serve(route):
            path = urlsplit(route.request.url).path
            if path in ('/before', '/after'):
                route.fulfill(content_type='text/html; charset=utf-8', body=before if path == '/before' else after)
            elif path == '/lamp.jpg':
                route.fulfill(content_type='image/jpeg', body=raw)
            elif path.endswith('/coupang-exposure'):
                route.fulfill(json={'ok': True, 'name': '램프 · 기존 저장소 사진', 'price_why': 'UI 검증',
                                    'rep': '/lamp.jpg', 'strip': [{'idx': 0, 'url': '/lamp.jpg', 'original': '/lamp.jpg', 'rep': True}]})
            elif path.startswith('/static/'):
                result = client.get(path)
                route.fulfill(status=result.status_code, content_type=result.content_type, body=result.data)
            elif '/rep-protection/' in path:
                if route.request.method == 'POST':
                    result = client.post(path, json=route.request.post_data_json)
                else:
                    result = client.get(path)
                route.fulfill(status=result.status_code, content_type=result.content_type, body=result.data)
            else:
                route.abort()
        page.route('**/*', serve)
        page.goto('https://fixture.test/before')
        expect(page.locator('[data-role=cpx-edit]')).to_be_visible()
        expect(page.locator('[data-role=cpx-protection]')).to_have_count(0)
        page.screenshot(path=str(captures / f'{width}-before.png'), full_page=True)
        page.goto('https://fixture.test/after')
        page.get_by_role('button', name='상품 보호 검토', exact=True).click()
        stage = page.locator('[data-rp=stage]')
        expect(stage).to_be_visible()
        assert not saves
        areas = page.locator('[data-rp=areas]')
        areas.scroll_into_view_if_needed()
        box = areas.bounding_box()
        # Same source frame: entire lamp region, not a text box used as product detection.
        for x, y in [(570, 520), (770, 850)]:
            page.mouse.click(box['x'] + x / 1440 * box['width'], box['y'] + y / 1440 * box['height'])
        expect(page.locator('[data-rp=count]')).to_have_text('상품 보호 영역 1곳')
        save = page.get_by_role('button', name='검토 기록 저장', exact=True)
        expect(save).to_be_disabled()
        page.locator('[data-rp=complete]').check()
        expect(save).to_be_enabled()
        page.screenshot(path=str(captures / f'{width}-after.png'), full_page=True)
        save.click()
        expect(page.locator('[data-rp=status]')).to_contain_text('저장했어요')
        assert len(saves) == 1
        proof = saves[0][2]['images_ko'][0]['rep_protection']
        assert R.verified(proof)
        for observed, desired in zip(proof['regions'][0], [570, 520, 770, 850]):
            assert abs(observed - desired) <= 4  # browser CSS pixel rounding, conservative integer bounds
        assert not errors
        browser.close()
