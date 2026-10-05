"""R2(오너 2026-10-05 역직구) — Qoo10 재팬 QAPI 뼈대.

키 흐름(오너 확정): QSM 셀러 가입 → 설정 › My Information › 담당 매니저에게 API Key 메일 요청 →
API Key + QSM ID/PW로 `CertificationAPI.CreateCertificationKey` → 인증키(SellerAuthKey, 1년)로 전 호출.

env(값은 로그·화면에 안 남긴다):
  QOO10_API_KEY · QOO10_USER_ID · QOO10_PASSWORD  — 인증키 발급용
  QOO10_CERT_KEY                                  — 발급받은 인증키를 직접 넣을 때(있으면 이걸 쓴다)
  QOO10_FEE_PCT                                   — 판매 수수료율(가격 엔진, 기본값 없음)

★ 추측 금지(오너 지시): 메서드명·베이스 URL·**파라미터 이름**은 QAPI 가이드(api.qoo10.jp …/QAPIGuideIndex.aspx)로
   확정한다. 이 컨테이너는 가이드에 못 나간다(egress 차단). 그래서 `METHODS`의 각 줄은 **출처**와 `params_confirmed`를 갖고,
   파라미터가 확정되지 않은 메서드는 호출하지 않는다(`Qoo10NotReady` — 사유를 그대로 말함).
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

ENV_KEYS = ("QOO10_API_KEY", "QOO10_USER_ID", "QOO10_PASSWORD")
ENV_CERT = "QOO10_CERT_KEY"

# 베이스 — 웹 검색 결과(2026-10-05)에 나온 SetNewGoods 엔드포인트 모양 `…/GMKT.INC.Front.QAPIService/ebayjapan.qapi/<메서드>`.
#   가이드로 재확인 전까지 `confirmed=False`.
QAPI_BASE = {"url": "https://api.qoo10.jp/GMKT.INC.Front.QAPIService/ebayjapan.qapi", "confirmed": False,
             "source": "웹 검색 결과 요약(2026-10-05) — 가이드 미확인"}

# 쓰임새 → 메서드. name이 비면 가이드에서 이름부터 확인.
METHODS: Dict[str, Dict[str, Any]] = {
    "cert": {"name": "CertificationAPI.CreateCertificationKey", "params_confirmed": False, "params": [],
             "source": "오너 지시(2026-10-05) + 웹 검색 — 파라미터 이름 미확인"},
    "new_goods": {"name": "ItemsBasic.SetNewGoods", "params_confirmed": False, "params": [],
                  "source": "오너 지시(2026-10-05) + 웹 검색(엔드포인트 모양) — 파라미터 이름 미확인"},
    "options": {"name": "", "params_confirmed": False, "params": [], "source": "가이드에서 확인 필요(옵션 등록)"},
    "images": {"name": "", "params_confirmed": False, "params": [], "source": "가이드에서 확인 필요(이미지)"},
    "inventory": {"name": "", "params_confirmed": False, "params": [], "source": "가이드에서 확인 필요(재고·가격)"},
    "orders": {"name": "", "params_confirmed": False, "params": [], "source": "가이드에서 확인 필요(주문 조회)"},
}


class Qoo10NotReady(RuntimeError):
    """호출 전제가 안 갖춰졌다 — 키 미설정 또는 명세 미확인. 사유를 그대로 화면에."""


def status() -> Dict[str, Any]:
    """`{state: ready|cert_needed|미설정, missing:[env], mode, line}` — 값은 안 싣는다."""
    if os.getenv(ENV_CERT, "").strip():
        return {"state": "ready", "missing": [], "mode": "인증키 직접(QOO10_CERT_KEY)",
                "line": "인증키 설정됨(QOO10_CERT_KEY)"}
    missing = [k for k in ENV_KEYS if not os.getenv(k, "").strip()]
    if missing:
        return {"state": "미설정", "missing": missing, "mode": "",
                "line": "미설정 — " + " · ".join(missing) + " (또는 인증키를 QOO10_CERT_KEY로)"}
    return {"state": "cert_needed", "missing": [], "mode": "API Key + ID/PW → 인증키 발급",
            "line": "API Key·ID·PW 설정됨 — 인증키 발급(CreateCertificationKey) 전"}


def spec_gaps() -> List[str]:
    """호출 전에 가이드로 확정해야 하는 것 — 진단 화면이 그대로 보인다."""
    gaps = []
    if not QAPI_BASE["confirmed"]:
        gaps.append(f"베이스 URL 미확인 ({QAPI_BASE['url']} — {QAPI_BASE['source']})")
    for use, m in METHODS.items():
        if not m["name"]:
            gaps.append(f"{use}: 메서드명 미확인 — {m['source']}")
        elif not m["params_confirmed"]:
            gaps.append(f"{use}: {m['name']} 파라미터 이름 미확인")
    return gaps


def call(use: str, params: Dict[str, Any], *, transport=None) -> Dict[str, Any]:
    """QAPI 호출 — 키·명세가 다 갖춰졌을 때만. 아니면 Qoo10NotReady(사유)."""
    st = status()
    if st["state"] == "미설정":
        raise Qoo10NotReady(st["line"])
    m = METHODS.get(use) or {}
    if not m.get("name"):
        raise Qoo10NotReady(f"{use}: 메서드명 미확인 — QAPI 가이드에서 확인 필요")
    if not (QAPI_BASE["confirmed"] and m.get("params_confirmed")):
        raise Qoo10NotReady(f"{m['name']}: 베이스·파라미터 이름이 가이드로 확정되지 않아 호출하지 않아요(추측 금지)")
    unknown = sorted(set(params) - set(m.get("params") or []))
    if unknown:
        raise Qoo10NotReady(f"{m['name']}: 명세에 없는 파라미터 {', '.join(unknown)}")
    if transport is None:
        raise Qoo10NotReady("전송 계층 미연결 — 명세 확정 뒤 붙인다")
    return transport(f"{QAPI_BASE['url']}/{m['name']}", params)


def build_goods(product: Dict[str, Any], *, ja: Optional[Dict[str, Any]] = None,
                price: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """우리 상품 → Qoo10 등록 재료(**논리 필드** — QAPI 파라미터 이름은 명세 확정 뒤 매핑). 빠진 재료는 `holds`."""
    ja = ja or {}
    holds = []
    if not ja.get("translated"):
        holds.append("일본어 번역 안 됨 — " + (" · ".join(f"{a['provider']}: {a['error']}" for a in ja.get("attempts") or [])
                                         or "번역 안 돌림"))
    if not price or price.get("state") != "ok":
        holds.append("판매가 없음 — " + ((price or {}).get("why") or "가격 엔진 안 돌림"))
    imgs = [u for u in (product.get("images_effective") or product.get("images") or []) if isinstance(u, str) and u]
    if not imgs:
        holds.append("이미지 0장")
    return {"title_ja": ja.get("title_ja", ""), "description_ja": ja.get("description_ja", ""),
            "options_ja": ja.get("options_ja", []), "price_jpy": (price or {}).get("price"),
            "duty_free_flag": (price or {}).get("duty_free"), "images": imgs[:10],
            "seller_code": str(product.get("id") or product.get("item_id") or ""),
            "skus": product.get("skus") or [], "holds": holds}
