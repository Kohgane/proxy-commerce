"""src/seller_console/category_classifier.py — 상품 카테고리 자동 분류 (Phase 224).

상품명/설명의 키워드로 정규화 카테고리 코드를 추정한다. 각 마켓 업로더가 이 코드를
자기 마켓 카테고리로 매핑한다(예: coupang CATEGORY_MAP). 키워드 미일치 시 'GEN'.

정직성: 추측 기반 단정이 아니라 키워드 규칙의 결과를 confidence와 함께 돌려준다.
"""
from __future__ import annotations

from typing import Any, Dict, List

# 정규화 카테고리: (코드, 한글 라벨, 키워드들)  — 코드는 coupang CATEGORY_MAP과 정렬
CATEGORY_RULES: List[Dict[str, Any]] = [
    {"code": "BAG", "label": "가방/지갑", "kw": [
        "가방", "백팩", "지갑", "파우치", "토트", "크로스백", "숄더백", "클러치", "bag", "wallet", "pouch", "backpack"]},
    {"code": "CLO", "label": "의류/패션", "kw": [
        "옷", "의류", "셔츠", "티셔츠", "맨투맨", "후드", "자켓", "재킷", "코트", "팬츠", "바지", "청바지",
        "원피스", "스커트", "치마", "니트", "신발", "운동화", "스니커즈", "모자", "양말", "shirt", "jacket",
        "pants", "dress", "shoe", "sneaker", "hoodie"]},
    {"code": "BTY", "label": "뷰티/화장품", "kw": [
        "화장품", "뷰티", "향수", "립", "립스틱", "스킨", "토너", "크림", "에센스", "세럼", "마스카라",
        "파운데이션", "쿠션", "샴푸", "cosmetic", "perfume", "skincare", "serum", "lipstick"]},
    {"code": "FOD", "label": "식품/차", "kw": [
        "식품", "간식", "과자", "차", "녹차", "홍차", "커피", "원두", "티백", "음료", "초콜릿", "사탕",
        "건강식품", "영양제", "tea", "coffee", "food", "snack", "chocolate"]},
    {"code": "DIG", "label": "디지털/컴퓨터", "kw": [
        "노트북", "컴퓨터", "키보드", "마우스", "모니터", "usb", "ssd", "충전기", "케이블", "태블릿",
        "스마트폰", "케이스", "보조배터리", "laptop", "keyboard", "mouse", "charger", "tablet"]},
    {"code": "ELC", "label": "가전/전자", "kw": [
        "가전", "이어폰", "헤드폰", "스피커", "블루투스", "청소기", "선풍기", "공기청정기", "전동", "가습기",
        "earphone", "headphone", "speaker", "bluetooth"]},
    {"code": "HOM", "label": "홈/가구/주방", "kw": [
        "가구", "의자", "소파", "리클라이너", "흔들의자", "안락의자", "침대", "책상", "선반", "수납",
        "주방", "그릇", "컵", "텀블러", "인테리어", "조명", "쿠션", "이불", "sofa", "chair", "table", "kitchen"]},
    {"code": "HLT", "label": "건강/의료", "kw": [
        "건강", "비타민", "마스크", "체온계", "혈압", "안마", "마사지", "찜질", "보호대", "health", "vitamin", "mask"]},
    {"code": "SPT", "label": "스포츠/레저", "kw": [
        "스포츠", "운동", "요가", "헬스", "덤벨", "매트", "자전거", "등산", "캠핑", "낚시", "골프",
        "발란스", "보드", "sport", "yoga", "fitness", "camping", "golf"]},
    {"code": "TOY", "label": "완구/취미", "kw": [
        "장난감", "완구", "블록", "인형", "퍼즐", "보드게임", "피규어", "toy", "lego", "puzzle"]},
    {"code": "BBY", "label": "유아/출산", "kw": [
        "유아", "아기", "기저귀", "분유", "젖병", "유모차", "baby", "diaper"]},
    {"code": "PET", "label": "반려동물", "kw": [
        "반려", "강아지", "고양이", "애견", "펫", "사료", "고양이모래", "pet", "dog", "cat"]},
    {"code": "OFC", "label": "사무/문구", "kw": [
        "사무", "문구", "노트", "펜", "다이어리", "파일", "office", "stationery"]},
]

DEFAULT = {"code": "GEN", "label": "기타", "confidence": 0.0}

# 화면 드롭다운용 정규화 카테고리 목록
CATEGORY_OPTIONS: List[Dict[str, str]] = (
    [{"code": r["code"], "label": r["label"]} for r in CATEGORY_RULES]
    + [{"code": "GEN", "label": "기타"}]
)


def classify(title: str, description: str = "", keywords: str = "") -> Dict[str, Any]:
    """상품명/설명/키워드에서 정규화 카테고리를 추정한다.

    Returns: {"code", "label", "confidence", "matched": [kw...]}
    키워드 미일치 시 GEN(confidence 0).
    """
    text = " ".join([title or "", description or "", keywords or ""]).lower()
    if not text.strip():
        return {**DEFAULT, "matched": []}

    best = None
    best_hits: List[str] = []
    for rule in CATEGORY_RULES:
        hits = [k for k in rule["kw"] if k.lower() in text]
        if hits and (best is None or len(hits) > len(best_hits)):
            best = rule
            best_hits = hits
    if not best:
        return {**DEFAULT, "matched": [], "suggested_keywords": suggest_keywords("GEN", title)}

    # confidence: 매칭 키워드 수에 따라 0.5~0.95
    confidence = min(0.5 + 0.15 * len(best_hits), 0.95)
    return {"code": best["code"], "label": best["label"],
            "confidence": round(confidence, 2), "matched": best_hits[:5],
            "suggested_keywords": suggest_keywords(best["code"], title)}


# 카테고리별 추천 키워드(검색 노출용 일반어). 자동분류 시 칩으로 제시 → 셀러가 골라 담는다.
KEYWORD_SUGGESTIONS: Dict[str, List[str]] = {
    "BAG": ["가방", "데일리백", "크로스백", "토트백", "백팩", "숄더백", "방수", "남녀공용", "수납", "여행"],
    "CLO": ["데일리룩", "베이직", "남녀공용", "사계절", "오버핏", "캐주얼", "편한", "신상", "선물"],
    "BTY": ["보습", "수분", "데일리", "민감성", "안티에이징", "지속력", "선물세트", "여행용", "휴대용"],
    "FOD": ["선물세트", "건강", "프리미엄", "수제", "전통", "명절선물", "차선물", "휴대", "개별포장"],
    "DIG": ["휴대용", "고속충전", "호환", "미니멀", "사무용", "게이밍", "필수템", "선물", "여행"],
    "ELC": ["무선", "블루투스", "휴대용", "고음질", "저소음", "에너지절약", "선물", "신상"],
    "HOM": ["인테리어", "북유럽", "원룸", "공간활용", "수납", "편안한", "거실", "주방", "선물", "1인용"],
    "HLT": ["건강관리", "휴대용", "가정용", "선물", "데일리", "관리", "편안한"],
    "SPT": ["홈트", "운동", "휴대용", "초보용", "캠핑", "아웃도어", "남녀공용", "선물"],
    "TOY": ["선물", "교육용", "어린이", "취미", "인기", "조립", "수집"],
    "BBY": ["유아", "신생아", "출산선물", "안전", "순한", "데일리", "휴대용"],
    "PET": ["반려견", "반려묘", "간식", "용품", "데일리", "선물", "수제"],
    "OFC": ["사무용", "데일리", "미니멀", "심플", "선물", "대용량"],
    "GEN": ["데일리", "선물", "인기", "신상", "남녀공용", "실용적", "휴대용"],
}


def suggest_keywords(code: str, title: str = "") -> List[str]:
    """카테고리 코드 기반 추천 키워드(+제목 단어 일부) 목록."""
    base = list(KEYWORD_SUGGESTIONS.get(code, KEYWORD_SUGGESTIONS["GEN"]))
    # 제목에서 의미있는 한글 단어 2개 정도 보강(중복 제외)
    for w in (title or "").replace("|", " ").split():
        w = w.strip()
        if 2 <= len(w) <= 8 and w not in base and not any(ch.isdigit() for ch in w):
            base.append(w)
        if len(base) >= 16:
            break
    return base[:16]
