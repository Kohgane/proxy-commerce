"""Y7-H(오너 2026-10-09) — 네이버 상품 등록 **필수 칸 전수 표**. 등록 페이로드를 이 표로 재고, 빈 칸은 사전검증이 먼저 말한다.

출처 표기
  - 문서: Context7 `/websites/apicenter_commerce_naver`(원상품 정보 구조체) 요약에 required/필수로 나온 칸
  - 400: 네이버가 실제로 거부한 칸(카나리·운영 실측 — 볼트 기록)
  - 템플릿: 정본 템플릿(`ss_template.json`)이 늘 채워 보낸 칸(통과 이력)
※ 문서 사이트는 이 환경에서 직접 열 수 없어(차단) 칸별 required 표시를 원문으로 대조하지 못했다 — 그래서 표에 나온 칸은
  전부 채워 보낸다(빠져서 400이 나는 쪽으로 틀리지 않게).
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

#: (경로, 사람 이름, 출처) — 경로는 `.`로 잇는다.
PATHS: Tuple[Tuple[str, str, str], ...] = (
    ("originProduct.statusType", "판매 상태", "문서·템플릿"),
    ("originProduct.saleType", "판매 유형", "템플릿"),
    ("originProduct.leafCategoryId", "리프 카테고리", "400(Y7-B leafCategoryId)"),
    ("originProduct.name", "상품명", "문서"),
    ("originProduct.detailContent", "상세 본문", "400(Y7-F detailContent NotBlank)"),
    ("originProduct.images.representativeImage.url", "대표 이미지", "문서"),
    ("originProduct.salePrice", "판매가", "문서"),
    ("originProduct.stockQuantity", "재고", "문서"),
    ("originProduct.deliveryInfo.deliveryType", "배송 방법", "템플릿"),
    ("originProduct.deliveryInfo.deliveryAttributeType", "배송 속성", "템플릿"),
    ("originProduct.deliveryInfo.deliveryCompany", "택배사", "템플릿"),
    ("originProduct.deliveryInfo.deliveryFee.deliveryFeeType", "배송비 유형", "템플릿"),
    ("originProduct.deliveryInfo.claimDeliveryInfo.returnDeliveryFee", "반품 배송비", "템플릿"),
    ("originProduct.deliveryInfo.claimDeliveryInfo.exchangeDeliveryFee", "교환 배송비", "템플릿"),
    ("originProduct.deliveryInfo.claimDeliveryInfo.shippingAddressId", "출고지 주소", "템플릿"),
    ("originProduct.deliveryInfo.claimDeliveryInfo.returnAddressId", "반품지 주소", "템플릿"),
    ("originProduct.detailAttribute.afterServiceInfo.afterServiceTelephoneNumber", "A/S 전화번호", "문서(required)"),
    ("originProduct.detailAttribute.afterServiceInfo.afterServiceGuideContent", "A/S 안내", "문서(required)"),
    ("originProduct.detailAttribute.originAreaInfo.originAreaCode", "원산지 코드", "문서(required)"),
    ("originProduct.detailAttribute.originAreaInfo.content", "원산지 표시", "템플릿(03 상세설명에 표시)"),
    ("originProduct.detailAttribute.minorPurchasable", "미성년자 구매", "400(카나리 7차 minorPurchasable NotNull)"),
    ("originProduct.detailAttribute.productInfoProvidedNotice.productInfoProvidedNoticeType", "고시 타입",
     "400(카나리 8차 NotValidEnum)"),
    ("smartstoreChannelProduct.channelProductName", "채널 상품명", "템플릿"),
    ("smartstoreChannelProduct.naverShoppingRegistration", "네이버쇼핑 등록", "템플릿"),
    ("smartstoreChannelProduct.channelProductDisplayStatusType", "전시 상태", "템플릿"),
)

#: 고시 칸 이름(화면). 타입 블록 칸은 `naver_notice.REQUIRED`가 정본.
NOTICE_LABELS = {
    "returnCostReason": "반품 비용 기준", "noRefundReason": "청약철회 불가 사유", "qualityAssuranceStandard": "품질보증기준",
    "compensationProcedure": "대금 환불·지연 보상", "troubleShootingContents": "피해 보상·분쟁 처리",
    "material": "소재", "color": "색상", "size": "치수", "manufacturer": "제조자/수입자", "caution": "세탁방법·취급 주의",
    "packDateText": "제조연월", "warrantyPolicy": "품질보증기준", "afterServiceDirector": "A/S 책임자·전화",
    "itemName": "품명(50자 이내)", "modelName": "모델명(50자 이내)",
}


def _get(d: Any, path: str):
    cur = d
    for k in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def _blank(v) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def audit(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """표 전체 — `[{path, label, source, value, ok}]`(고시 타입 블록 칸 포함). PR·진단 화면이 그대로 쓴다."""
    from src.uploaders import naver_notice as _nn
    rows = []
    for path, label, src in PATHS:
        v = _get(payload, path)
        rows.append({"path": path, "label": label, "source": src, "value": v, "ok": not _blank(v)})
    notice = _get(payload, "originProduct.detailAttribute.productInfoProvidedNotice") or {}
    t = str(notice.get("productInfoProvidedNoticeType") or "")
    bad = set(_nn.missing(notice))
    for f in _nn.REQUIRED.get(t, ()):
        p = f"originProduct.detailAttribute.productInfoProvidedNotice.{t.lower()}.{f}"
        rows.append({"path": p, "label": NOTICE_LABELS.get(f, f), "source": f"문서({t})" + ("·400(19:46)" if f in ("itemName", "manufacturer") else ""),
                     "value": (notice.get(t.lower()) or {}).get(f), "ok": f not in bad})
    return rows


def missing(payload: Dict[str, Any], *, skip=()) -> List[Dict[str, Any]]:
    """채우지 못한 필수 칸 — `[{field, path, label}]`. `field`는 경로 끝 이름(사유코드 `naver_required_<field>`)."""
    out = []
    for r in audit(payload):
        if r["ok"] or r["path"] in skip:
            continue
        out.append({"field": r["path"].rsplit(".", 1)[-1], "path": r["path"], "label": r["label"]})
    return out
