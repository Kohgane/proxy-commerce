"""순찰 127 M1(운영 10-27 10:40 KST) — 오너 결정 「빼고 등록」(애플워치 호환 표기 · 글자 고치기)이 `imgedit:day`를 1 올린 뒤
20분+ 응답 없이 멈췄다. 잡 잠금이 다음 일회성 작업까지 막았다. 그리기 뒤 Cloudinary 업로드에 시간 상한이 없었다(SDK 기본 = 무한 대기).

- 업로드 한 번: 사진 60초 · 동영상·파생본 300초(`timeout` 주면 그 값).
- 편집 한 장: 그리기 기다림·업로드 각 30초(`IMAGE_EDIT_STEP_TIMEOUT_SEC`).
- 「빼고 등록」 한 번의 다시 그리기 전체 120초(`RISK_STRIP_BUDGET_SEC`) — 넘으면 남은 장은 사진째 뺀다(사유).
"""
import time

import pytest


@pytest.fixture
def _cloudinary(monkeypatch):
    import cloudinary.uploader as U
    from src.media import image_pipeline as P
    for k, v in (("CLOUDINARY_CLOUD_NAME", "c"), ("CLOUDINARY_API_KEY", "k"), ("CLOUDINARY_API_SECRET", "s")):
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("ADAPTER_DRY_RUN", "0")
    monkeypatch.setattr(P, "_CDN_UPLOAD_ENABLED", True)
    got = []

    def fake_upload(fileobj, **opts):
        got.append(opts)
        return {"secure_url": "https://res.cloudinary.com/c/image/upload/x.jpg", "public_id": "x", "bytes": 3}
    monkeypatch.setattr(U, "upload", fake_upload)
    return P, got


def test_upload_always_carries_a_timeout(_cloudinary):
    P, got = _cloudinary
    assert P.upload_bytes(b"abc")["ok"] and got[-1]["timeout"] == 60.0
    P.upload_bytes(b"abc", resource_type="video")
    assert got[-1]["timeout"] == 300.0
    P.upload_bytes(b"abc", eager=[{"effect": "gen_remove"}])
    assert got[-1]["timeout"] == 300.0
    P.upload_bytes(b"abc", timeout=30)
    assert got[-1]["timeout"] == 30.0


def test_upload_timeout_env_and_bad_values(monkeypatch):
    from src.media import image_pipeline as P
    monkeypatch.setenv("CLOUDINARY_UPLOAD_TIMEOUT_SEC", "45")
    assert P.upload_timeout_sec() == 45.0
    monkeypatch.setenv("CLOUDINARY_UPLOAD_TIMEOUT_SEC", "x")
    assert P.upload_timeout_sec() == 60.0
    monkeypatch.setenv("CLOUDINARY_UPLOAD_TIMEOUT_SEC", "0")
    assert P.upload_timeout_sec() == 60.0


def test_upload_that_times_out_returns_a_reason(_cloudinary, monkeypatch):
    import cloudinary.uploader as U
    P, _got = _cloudinary

    def slow(fileobj, **opts):
        raise TimeoutError("read timed out")
    monkeypatch.setattr(U, "upload", slow)
    r = P.upload_bytes(b"abc", timeout=1)
    assert r["ok"] is False and ("TimeoutError" in r["error"] or "timed out" in r["error"])


def test_edit_steps_are_capped():
    from src.services import image_edit as IE
    from tests._ast_probe import calls_in
    assert IE.step_timeout_sec() == 30.0
    assert "step_timeout_sec" in calls_in(IE.apply)                     # 그리기 기다림·업로드 둘 다 이 상한을 받는다(호출 구조로)


def _hit(n):
    return {"key": "compat:applewatch", "names": ["애플워치"], "case": False, "to": "스마트워치", "cat": "호환 표기",
            "found": ["애플워치"], "images": [{"kind": "detail", "idx": i} for i in range(n)]}


def test_strip_budget_excludes_the_rest_instead_of_hanging(monkeypatch):
    from src.services import risk_gate as R
    monkeypatch.setenv("RISK_STRIP_BUDGET_SEC", "0.05")
    calls = []

    def slow_retext(ex, kind, e, names, case, to, label):
        calls.append(int(e["idx"]))
        time.sleep(0.06)                                                # 한 장이 상한을 다 썼다
    monkeypatch.setattr(R, "_retext_or_exclude", slow_retext)
    ex = {"detail_images_ko": [{"idx": i, "url": f"https://x/{i}.jpg"} for i in range(4)]}
    R.strip_extra(ex, _hit(4), erase_pixels=True)
    assert calls == [0]                                                  # 첫 장만 그렸다
    rest = ex["detail_images_ko"][1:]
    assert all("시간 초과" in e.get("risk_exclude", "") and "사진째 뺌" in e["risk_exclude"] for e in rest)


def test_strip_budget_does_not_touch_text_only_decisions(monkeypatch):
    from src.services import risk_gate as R
    monkeypatch.setenv("RISK_STRIP_BUDGET_SEC", "0.000001")
    ex = {"title_ko": "애플워치 호환 밴드", "detail_images_ko": [{"idx": 0, "url": "https://x/0.jpg"}]}
    R.strip_extra(ex, _hit(1))                                           # 자동 적용(글자만) — 사진은 건드리지 않는다
    assert ex["title_ko"] == "스마트워치 호환 밴드" and "risk_exclude" not in ex["detail_images_ko"][0]
