"""앱 v1.1(오너 2026-11-23) — 아이폰 앱 푸시(APNs).

· 등록: 앱이 로그인한 웹뷰에서 `POST /api/push/apns/register {token, env, bundle}` → 사용자별 기기 여러 대를 `app_state`에 둔다.
· 발송: 수집 완료 · 사전검증 보류 · 등록 성공/실패 · 새 주문. payload = `{"aps":{"alert":{title,body},"sound":"default"},"path":"/seller/…"}`
  (앱이 알림을 누르면 `path` 화면을 연다).
· 키: env `APNS_KEY_P8`(PEM 여러 줄 그대로) · `APNS_KEY_ID` · `APNS_TEAM_ID` · `APNS_TOPIC`. **키가 없으면 조용히 건너뛴다**
  (가짜 「보냄」 없음 — 결과는 `{"sent":0,"skipped":"no_keys"}`). APNs는 HTTP/2만 받는다 → `httpx[http2]`. 라이브러리가 없어도 건너뛴다.
· 410/400 BadDeviceToken·Unregistered 응답이면 그 기기를 지운다(지운 앱에 계속 보내지 않게).
· 발송은 요청을 막지 않게 데몬 스레드에서. 기기 토큰은 로그에 앞 8자만.
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_PREFIX = "apns_devices:"
_MAX_DEVICES = 10
_TOKEN_RE = re.compile(r"^[0-9a-fA-F]{32,200}$")
_HOSTS = {"production": "https://api.push.apple.com", "sandbox": "https://api.sandbox.push.apple.com"}
_DROP_REASONS = {"BadDeviceToken", "Unregistered", "DeviceTokenNotForTopic"}

_jwt_cache: dict = {"tok": "", "at": 0.0}
_jwt_lock = threading.Lock()


def _st():
    from src.db import image_translate_queue_pg as st
    return st


def _env(name: str) -> str:
    try:
        from src.utils.env import env_str
        return env_str(name)
    except Exception:
        return str(os.getenv(name, "") or "").strip()


def configured() -> bool:
    return all(_env(k) for k in ("APNS_KEY_P8", "APNS_KEY_ID", "APNS_TEAM_ID", "APNS_TOPIC"))


# ── 기기 등록 ────────────────────────────────────────────────────────────────

def register(user_id: str, token: str, env: str = "production", bundle: str = "") -> dict:
    """기기 한 대를 등록(같은 토큰이면 갱신). 반환 `{ok, devices}` 또는 `{ok:False, error}`."""
    uid = str(user_id or "").strip()
    tok = str(token or "").strip()
    if not uid:
        return {"ok": False, "error": "로그인이 필요해요."}
    if not _TOKEN_RE.match(tok):
        return {"ok": False, "error": "기기 토큰 모양이 아니에요."}
    env = "sandbox" if str(env or "").strip().lower() == "sandbox" else "production"
    topic = _env("APNS_TOPIC")
    bundle = str(bundle or "").strip()
    if topic and bundle and bundle != topic:
        return {"ok": False, "error": "이 앱의 알림 주소가 아니에요."}
    now = datetime.now(timezone.utc).isoformat()

    def _put(cur: dict) -> dict:
        devs = [d for d in list((cur or {}).get("devices") or []) if d.get("token") != tok]
        devs.append({"token": tok, "env": env, "bundle": bundle, "at": now})
        return {"devices": devs[-_MAX_DEVICES:]}

    new = _st().state_update(_PREFIX + uid, _put)
    logger.info("[apns] 기기 등록 user=%s token=%s… env=%s (총 %d대)", uid, tok[:8], env, len(new.get("devices") or []))
    return {"ok": True, "devices": len(new.get("devices") or [])}


def devices(user_id: str) -> list:
    return list((_st().state_get(_PREFIX + str(user_id or "")) or {}).get("devices") or [])


def _drop(user_id: str, token: str) -> None:
    def _rm(cur: dict) -> dict:
        return {"devices": [d for d in list((cur or {}).get("devices") or []) if d.get("token") != token]}
    try:
        _st().state_update(_PREFIX + str(user_id), _rm)
    except Exception:
        pass


# ── 발송 ────────────────────────────────────────────────────────────────────

def _provider_jwt() -> str:
    """APNs 제공자 토큰(ES256) — 50분마다 새로(애플: 20~60분 사이 재발급)."""
    with _jwt_lock:
        if _jwt_cache["tok"] and time.time() - _jwt_cache["at"] < 50 * 60:
            return _jwt_cache["tok"]
        import jwt  # PyJWT(ES256은 cryptography)
        key = _env("APNS_KEY_P8").replace("\\n", "\n")
        tok = jwt.encode({"iss": _env("APNS_TEAM_ID"), "iat": int(time.time())}, key, algorithm="ES256",
                         headers={"kid": _env("APNS_KEY_ID"), "alg": "ES256"})
        _jwt_cache.update(tok=tok, at=time.time())
        return tok


def payload(title: str, body: str, path: str = "") -> dict:
    p = {"aps": {"alert": {"title": str(title or "")[:120], "body": str(body or "")[:300]}, "sound": "default"}}
    if path and str(path).startswith("/seller/"):
        p["path"] = str(path)
    return p


def send(user_id: str, title: str, body: str, path: str = "") -> dict:
    """그 사용자의 기기 전부에 보낸다(동기). `{sent, failed, skipped}` — 키·기기·라이브러리 없으면 skipped."""
    if not configured():
        return {"sent": 0, "failed": 0, "skipped": "no_keys"}
    devs = devices(user_id)
    if not devs:
        return {"sent": 0, "failed": 0, "skipped": "no_devices"}
    try:
        import httpx  # HTTP/2 — APNs는 HTTP/1.1을 받지 않는다
    except Exception:
        logger.warning("[apns] httpx[http2] 없음 — 발송 건너뜀")
        return {"sent": 0, "failed": 0, "skipped": "no_http2"}
    body_json = payload(title, body, path)
    sent = failed = 0
    try:
        auth = "bearer " + _provider_jwt()
    except Exception as exc:
        logger.warning("[apns] 제공자 토큰 서명 실패(키 확인): %s", type(exc).__name__)
        return {"sent": 0, "failed": len(devs), "skipped": "bad_key"}
    headers = {"authorization": auth, "apns-topic": _env("APNS_TOPIC"), "apns-push-type": "alert",
               "apns-priority": "10"}
    try:
        with httpx.Client(http2=True, timeout=10.0) as client:
            for d in devs:
                host = _HOSTS.get(d.get("env") or "production", _HOSTS["production"])
                try:
                    r = client.post(f"{host}/3/device/{d['token']}", json=body_json, headers=headers)
                except Exception as exc:
                    failed += 1
                    logger.warning("[apns] 보내기 실패 token=%s… %s", d["token"][:8], type(exc).__name__)
                    continue
                if r.status_code == 200:
                    sent += 1
                    continue
                failed += 1
                reason = ""
                try:
                    reason = str((r.json() or {}).get("reason") or "")
                except Exception:
                    pass
                logger.warning("[apns] 거절 token=%s… HTTP %s %s", d["token"][:8], r.status_code, reason)
                if r.status_code == 410 or reason in _DROP_REASONS:
                    _drop(user_id, d["token"])
    except Exception as exc:
        logger.warning("[apns] 연결 실패: %s", type(exc).__name__)
        return {"sent": sent, "failed": failed or len(devs), "skipped": ""}
    return {"sent": sent, "failed": failed, "skipped": ""}


def notify(user_id: str, title: str, body: str, path: str = "") -> None:
    """요청을 막지 않게 백그라운드로 보낸다. 키·기기가 없으면 스레드도 만들지 않는다."""
    uid = str(user_id or "").strip()
    if not uid or uid == "default" or not configured():
        return
    try:
        if not devices(uid):
            return
    except Exception:
        return

    def _run():
        try:
            res = send(uid, title, body, path)
            logger.info("[apns] %s → sent=%s failed=%s %s", title[:20], res.get("sent"), res.get("failed"),
                        res.get("skipped") or "")
        except Exception as exc:
            logger.warning("[apns] 발송 스레드 오류: %s", type(exc).__name__)

    threading.Thread(target=_run, name="apns-notify", daemon=True).start()
