# v54 STEP1 — 북마클릿 파비콘: 북마크바 직행 가져오기

## 전제 (오너 확정)
`javascript:` 북마크의 파비콘은 **가져오기 파일 ICON 속성만이 유일 기록 경로**. 드래그 상속·Favicons DB
조작은 재시도 금지.

## 수리
- **NETSCAPE 파일 구조**: 북마클릿을 `<H3 PERSONAL_TOOLBAR_FOLDER="true">Bookmarks bar</H3>` 폴더 하위에
  배치(2중 `<DL>`) → 크롬이 가져오기 시 이 폴더 내용을 **북마크바로 직행 병합**(별도 폴더로 빠지지 않게).
- **ICON = v181 favicon-32**(브리프 지정, 32px). 구 favicon-48 → favicon-32 교체. 구 아이콘 잔존 0.
- **페이지 UI 재편**: 1순위 카드 = **① 파일 받기 → ② 크롬에 가져오기(끝)** 2단계 + **아이콘 미리보기**
  (북마크바에 어떻게 보이는지 favicon-32 + '고가수집'). 복사 방식은 `<details>`로 강등 + **"아이콘 없이
  빠른 설치"** 정직 라벨.
- **정직 안내(추측 금지)**: "크롬 버전에 따라 드물게 ‘가져온 북마크’(Imported) 폴더로 들어갈 수 있어요 —
  그럼 그 폴더에서 북마크바로 끌어다 놓으세요(아이콘 유지)." → 실기기 크롬 동작은 오너 확인 후 문구 확정.

## 로컬 실증
- `_netscape_bookmark`: PERSONAL_TOOLBAR_FOLDER="true"·2중 DL·ICON base64(==favicon-32 v181)·라벨 '고가수집'.
- `/seller/bookmarklet/file` POST → 200, 파일에 PERSONAL_TOOLBAR_FOLDER+ICON, Content-Disposition attachment.

## 판정 (오너)
실기기에서 파일 받기 → 가져오기 → 북마크바에 **아이콘 + '고가수집'** 노출 캡처 + 클릭 수집 성공.
(build 메타 해시 curl 보고 — v53 규약.)

## 가드
test_v54_bookmarklet_toolbar(4): NETSCAPE 폴더 구조·ICON=favicon-32·파일우선/복사강등·다운로드 엔드포인트.
+ v39b/v49/v53 북마클릿 테스트 v54 UI 반영.
