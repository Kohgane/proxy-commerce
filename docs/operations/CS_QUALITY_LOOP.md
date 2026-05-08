# CS 답변 품질 학습 루프 (Phase 139)

## 목적
- AI 제안 답변과 실제 발송문 간 편집률을 측정해 FAQ 개선 후보를 찾습니다.

## 저장소
- Sheets 워크시트: `cs_reply_quality`
- 폴백: `data/cs_reply_quality.jsonl`

## 수집 항목
- 메시지 ID, FAQ ID, 언어, 제안문/최종문, 채택 여부, 유사도 점수(0~1)

## 운영 화면
- `/seller/cs/quality`
  - 저품질 FAQ 목록
  - 마지막 발송문으로 FAQ 답변 갱신(원클릭)
  - 응답 시간 분포(평균, P95)
