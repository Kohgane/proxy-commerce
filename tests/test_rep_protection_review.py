"""Human review producer contracts; image transport is stubbed, not live OCR."""
import base64
import copy
import io
import json
from contextlib import contextmanager

import pytest
from PIL import Image

from src.services import rep_protection_review as R, image_edit as IE


@pytest.fixture(autouse=True)
def secret(monkeypatch):
    monkeypatch.setattr(R, '_secret', lambda: 'review-test-only-secret')


@pytest.fixture
def source(monkeypatch):
    f = io.BytesIO()
    Image.new('RGB', (600, 600), 'white').save(f, 'PNG')
    raw = f.getvalue()
    ex = {'images': ['https://cdn.example/original.png'],
          'images_ko': [{'idx': 0, 'status': 'done', 'use': True,
                         'url': 'https://cdn.example/translated.png',
                         'translated_url': 'https://cdn.example/translated.png'}],
          'detail_images': ['https://cdn.example/detail.png'], 'title_ko': 'existing'}
    monkeypatch.setattr(IE, '_fetch', lambda _: raw)
    return ex, raw


def issued(ex):
    snap = R.snapshot(ex, 0, item_id='item', reviewer='owner')
    return snap, {'token': snap['token'], 'regions': [[100.5, 250.1, 500, 550]], 'reviewed_complete': True}


def test_snapshot_exact_bytes_no_mutating_editor_paths(source, monkeypatch):
    ex, raw = source
    old = copy.deepcopy(ex)
    for name in ('work_bytes', 'plan', 'ensure_boxes', 'refresh_pending', 'drop_legacy_edits'):
        monkeypatch.setattr(IE, name, lambda *a, **k: pytest.fail('mutating path'))
    s, _ = issued(ex)
    assert base64.b64decode(s['image'].split(',')[1]) == raw
    assert s['size'] == [600, 600] and ex == old


def test_producer_is_signed_and_changes_review_only(source):
    ex, _ = source
    _, body = issued(ex)
    result = R.accept(ex, 0, body, item_id='item', reviewer='owner')
    proof = result['images_ko'][0].pop('rep_protection')
    assert result == ex
    assert R.verified(proof) and proof['regions'] == [[100, 250, 500, 550]]
    assert proof['review_kind'] == 'human' and proof['reviewer'] == 'owner'
    proof['regions'] = [[0, 0, 1, 1]]
    assert not R.verified(proof)


@pytest.mark.parametrize('change', ['item', 'reviewer', 'state', 'url', 'bytes', 'token', 'expired'])
def test_stale_or_forged_review_rejected(source, monkeypatch, change):
    ex, _ = source
    _, body = issued(ex)
    args = {'item_id': 'item', 'reviewer': 'owner'}
    if change == 'reviewer': args['reviewer'] = 'other'
    if change == 'item': args['item_id'] = 'other'
    if change == 'state': ex['title_ko'] = 'new'
    if change == 'url': ex['images_ko'][0]['url'] = 'https://cdn.example/new.png'
    if change == 'bytes':
        out = io.BytesIO(); Image.new('RGB', (600, 600), 'black').save(out, 'PNG')
        monkeypatch.setattr(IE, '_fetch', lambda _: out.getvalue())
    if change == 'token': body['token'] = 'forged'
    if change == 'expired':
        from itsdangerous.timed import TimestampSigner
        original = TimestampSigner.get_timestamp
        monkeypatch.setattr(TimestampSigner, 'get_timestamp', lambda self: original(self) + 901)
    with pytest.raises(ValueError): R.accept(ex, 0, body, **args)


@pytest.mark.parametrize('regions', [[], [[True,0,2,2]], [[0,0,float('nan'),3]], [[-1,0,2,2]], [[0,0,601,20]], [[0,0,0,5]], [[0,0,1,1]]*25])
def test_invalid_regions_never_accepted(source, regions):
    ex, _ = source
    _, body = issued(ex); body['regions'] = regions
    with pytest.raises(ValueError): R.accept(ex, 0, body, item_id='item', reviewer='owner')


def test_explicit_complete_and_large_image_required(source, monkeypatch):
    ex, _ = source
    _, body = issued(ex); body['reviewed_complete'] = 'true'
    with pytest.raises(ValueError): R.accept(ex, 0, body, item_id='item', reviewer='owner')
    out = io.BytesIO(); Image.new('RGB', (2001, 2)).save(out, 'PNG')
    monkeypatch.setattr(IE, '_fetch', lambda _: out.getvalue())
    with pytest.raises(ValueError): R.snapshot(ex, 0, item_id='item', reviewer='owner')


def test_storage_preserves_concurrent_and_unrelated_fields(source, monkeypatch):
    from src.seller_console import collect_history_store as S
    ex, _ = source; _, body = issued(ex)
    reviewed = R.accept(ex, 0, body, item_id='item', reviewer='owner')
    row = {'id': 'item', 'seller_id': 'owner', 'extra_json': json.dumps(ex)}
    monkeypatch.setattr(S, '_pg_backend', lambda: None); monkeypatch.setattr(S, '_in_memory', [row])
    monkeypatch.setenv('APP_ENV', 'test')
    assert not S.save_rep_protection('item', ex, reviewed, seller_ids={'other'})
    altered = copy.deepcopy(reviewed); altered['title_ko'] = 'bad'
    assert not S.save_rep_protection('item', ex, altered, seller_ids={'owner'})
    newer = dict(ex, title_ko='concurrent'); row['extra_json'] = json.dumps(newer)
    assert not S.save_rep_protection('item', ex, reviewed, seller_ids={'owner'})
    assert json.loads(row['extra_json']) == newer
    row['extra_json'] = json.dumps(ex)
    assert S.save_rep_protection('item', ex, reviewed, seller_ids={'owner'})
    assert json.loads(row['extra_json']) == reviewed
    assert not S.save_rep_protection('item', ex, reviewed, seller_ids={'owner'})


def test_pg_save_is_scoped_atomic_compare_swap(source, monkeypatch):
    from src.db import collect_history_pg as P
    ex, _ = source
    class Cursor:
        def execute(self, sql, params): self.sql, self.params = sql, params
        def fetchone(self): return ('item',)
    c = Cursor()
    @contextmanager
    def tx(): yield c
    monkeypatch.setattr(P.pg, 'tx', tx)
    assert P.compare_swap_extra('item', ex, ex, seller_ids={'owner'})
    assert 'extra_json=%s::jsonb' in c.sql and 'deleted_at IS NULL' in c.sql
    assert 'user_id = ANY(%s)' in c.sql and 'RETURNING id' in c.sql
    assert json.loads(c.params[-1]) == ex


def test_route_admin_owned_read_only_and_save_without_market_queue(source, monkeypatch):
    from src.order_webhook import app
    from src.seller_console import views as V, collect_history_store as S
    ex, _ = source
    client = app.test_client()
    monkeypatch.setattr(V, '_is_admin_user', lambda: True)
    monkeypatch.setattr(V, '_check_auth', lambda: True)
    monkeypatch.setattr(V, '_get_owned_item', lambda _: {'extra_json': json.dumps(ex)})
    monkeypatch.setattr(V, '_seller_identities', lambda: {'owner'})
    monkeypatch.setattr(V, '_image_edit_save', lambda *a, **kw: pytest.fail('must not enqueue'))
    monkeypatch.setattr(IE, 'plan', lambda *a, **kw: pytest.fail('must not invoke editor GET'))
    saved = []
    monkeypatch.setattr(S, 'save_rep_protection', lambda *a, **kw: saved.append(a) or True)
    url = '/seller/collect/item/rep-protection/0'
    assert client.get(url).status_code == 403
    with client.session_transaction() as s: s['user_id'] = 'owner'
    r = client.get(url)
    assert r.status_code == 200 and r.headers['Cache-Control'] == 'no-store' and not saved
    payload = {'token': r.json['token'], 'regions': [[100,250,500,550]], 'reviewed_complete': True}
    assert client.post(url, json=payload).status_code == 200
    assert R.verified(saved[0][2]['images_ko'][0]['rep_protection'])
    monkeypatch.setattr(S, 'save_rep_protection', lambda *a, **kw: False)
    assert client.post(url, json=payload).status_code == 409
    monkeypatch.setattr(V, '_get_owned_item', lambda _: None)
    assert client.get(url).status_code == 404
    monkeypatch.setattr(V, '_is_admin_user', lambda: False)
    assert client.get(url).status_code == 403
    assert client.post(url, json=payload).status_code == 403
