"""src/seller_console/coupang_invoice.py — F48-b 쿠팡 구매대행 **인보이스영수증 파일** 업로드.

## 왜 (오너 브리프 F48-b, 2026-09-25)

쿠팡은 카테고리 메타 `requiredDocumentNames`에 「인보이스영수증(해외구매대행 선택시)」이 있으면
상품 생성 요청의 `requiredDocuments[templateName=…].documentPath`에 **파일 주소**를 요구한다.
그 주소를 셀러가 어딘가에 올려 두고 복사해 오라고 하면 그게 곧 이탈이다 — 여기서 올린다.

## 규칙

- 브라우저 → 서버 multipart → **서버가** Cloudinary에 올린다. 키·서명은 서버 env에만 있다
  (클라이언트는 파일만 보낸다). 저장값은 `secure_url`.
- 저장 자리는 **쿠팡 자격의 한 칸**(`COUPANG_INVOICE_DOCUMENT_URL`)뿐이다. 오너 역질문의 답:
  이 서류는 쿠팡 상품 생성 문서에만 있는 필드다 → 쿠팡 전용 칸이면 **다른 마켓으로 샐 경로 자체가 없다.**
  (그래도 새지 않는지는 `tests/test_f48b_invoice_upload.py`가 경로를 열거해 못박는다.)
- 상품 이미지와 **다른 폴더**(`…/coupang-invoice`)에 둔다 — 이미지 저장소를 훑는 코드가 줍지 않게.
"""
from __future__ import annotations

from typing import Any, Dict

INVOICE_ENV = "COUPANG_INVOICE_DOCUMENT_URL"
FOLDER = "coupang-invoice"
#: 받는 형식 — 영수증은 사진 아니면 PDF다. 그 밖은 쿠팡이 무엇을 받는지 모른다(지어내지 않는다).
ALLOWED = {"image/jpeg": ".jpg", "image/png": ".png", "application/pdf": ".pdf"}
MAX_BYTES = 10 * 1024 * 1024


def _sniff(data: bytes) -> str:
    """확장자·브라우저가 준 타입이 아니라 **바이트 머리**로 형식을 본다."""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:5] == b"%PDF-":
        return "application/pdf"
    return ""


def upload_invoice(data: bytes, filename: str = "") -> Dict[str, Any]:
    """파일 바이트 → Cloudinary → `{ok, secure_url, error, kind}`. 실패 사유는 문장 그대로."""
    out: Dict[str, Any] = {"ok": False, "secure_url": "", "error": "", "kind": ""}
    if not data:
        out["error"] = "파일이 비어 있습니다."
        return out
    if len(data) > MAX_BYTES:
        out["error"] = f"파일이 너무 큽니다({len(data) // 1024}KB) — 10MB까지 받습니다."
        return out
    kind = _sniff(data)
    if kind not in ALLOWED:
        out["error"] = "JPG·PNG·PDF만 받습니다(파일 내용이 그 셋 중 하나가 아닙니다)."
        return out
    out["kind"] = kind
    from src.media.image_pipeline import upload_bytes
    # PDF는 image 리소스로도 올라가지만(Cloudinary), 형식을 우리가 바꾸지 않게 auto로 둔다.
    res = upload_bytes(data, folder=FOLDER,
                       resource_type="auto" if kind == "application/pdf" else "image")
    if not res.get("ok"):
        out["error"] = "파일을 올리지 못했습니다 — " + str(res.get("error") or "사유 없음")
        return out
    out.update(ok=True, secure_url=str(res["secure_url"]))
    return out


def save_invoice(seller_id: str, data: bytes, filename: str = "") -> Dict[str, Any]:
    """올리고 → 쿠팡 자격의 인보이스 칸에 저장(되읽기 검증은 `market_credentials.save`가 한다)."""
    out = upload_invoice(data, filename)
    if not out["ok"]:
        return out
    from . import market_credentials as mc
    try:
        mc.save(seller_id, "coupang", {INVOICE_ENV: out["secure_url"]})
    except Exception as exc:
        # 올리긴 했는데 저장을 못 했다 — 「저장됨」이라 하지 않는다. 주소는 돌려준다(다시 붙이게).
        out.update(ok=False, error=f"파일은 올렸지만 저장하지 못했습니다 — {exc}")
    return out
