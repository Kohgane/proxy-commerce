/* kgp-main.js — MAIN world 브릿지 (v47 STEP4, 근본 수리).
 *
 * 문제: 확장 content_script는 **격리 월드(isolated world)**라 페이지의 live 전역
 *   (window.rawData / __NEXT_DATA__ / __NUXT__ 등)을 못 읽는다. Temu처럼 초기 상태를
 *   **XHR로 렌더 후에 채우는** 사이트는 인라인 <script> 텍스트에도 안 실려, 격리월드
 *   추출기가 가격·이미지·상세를 못 얻어 '부분 수집'이 났다(v46 실기기 실패의 근본).
 *
 * 해결: 이 스크립트를 manifest "world":"MAIN" 으로 페이지 월드에 주입한다. 여기서는
 *   live 전역이 그대로 보이므로 kgpExtractProduct()를 실행하면 초기상태 JSON을 읽는다.
 *   순환참조/대용량 상태를 직접 넘기지 않고 **추출 결과(작은 plain object)만** postMessage로
 *   격리월드 content_script에 넘긴다(구조화 복제 안전). 추가 네트워크(API) 호출 없음.
 */
(function () {
  "use strict";
  if (window.__kgpMainBound) return;   // 중복 주입 방지(SPA 재주입 등)
  window.__kgpMainBound = true;

  function _run(opts) {
    try {
      // v86-H: 격리월드가 넘겨준 pageType을 그대로 전달 — MAIN world는 카드 수를 못 세어 스스로 판정 불가.
      return (typeof window.kgpExtractProduct === "function") ? window.kgpExtractProduct(opts || {}) : null;
    } catch (e) {
      try { console.warn("[고가수집기] MAIN world 추출 오류:", e); } catch (_) {}
      return null;
    }
  }

  // 격리월드가 요청(__kgpReq)하면 그 시점의 live DOM/전역에서 추출해 결과(__kgpRes)를 돌려준다.
  window.addEventListener("message", function (e) {
    try {
      if (e.source !== window || !e.data) return;
      // v54 STEP2: 진단 모드 — 격리월드가 __kgpDiagReq 를 보내면 캡처·채점된 후보를 콘솔 표로 출력.
      if (e.data.__kgpDiagReq) {
        try {
          var rows = (typeof window.__kgpDiagRows === "function") ? window.__kgpDiagRows() : [];
          if (rows.length && console.table) {
            console.log("%c[고가수집기] 자가진단 — 가로챈 JSON 응답 채점(최고점=상품 소스 자동 채택)", "font-weight:bold;color:#119a8e");
            console.table(rows);
          } else {
            console.log("[고가수집기] 자가진단: 아직 상품형 JSON 응답 없음(페이지 스크롤·옵션 클릭 후 다시 시도)");
          }
        } catch (_) {}
        return;
      }
      if (e.data.__kgpReq == null) return;
      var meta = _run({ pageType: (e.data && e.data.pageType) || "" });
      // v55 STEP1: Tier1 진단 정보 동봉 — 격리월드가 '왜 Tier1이 비었나'를 무음 없이 1줄로 알림.
      // v62 STEP2: goods_id 매칭 진단 — 내 goods_id 응답 포착 여부(오채택 방지 근거).
      // v86-G: netStats(seen/jsonish/kept/dropped) + top 후보 요약을 함께 넘긴다 —
      //   `captured:0` 하나로는 '월드/타이밍 실패'와 '채점 실패'를 못 갈랐다(kgp-net.js 주석 참조).
      var diag = { netBound: false, captured: 0, topScore: 0, topUrl: "", pageGoodsId: "", matched: false, mismatch: false,
                   netStats: null, top: null, scope: null, adopted: null };
      try {
        diag.netBound = !!window.__kgpNetBound;
        var cap = window.__kgpCaptured || [];
        diag.captured = cap.length;
        if (cap.length) { diag.topScore = cap[0].score || 0; diag.topUrl = cap[0].url || ""; }
        diag.netStats = window.__kgpNetStats || null;
        diag.top = (typeof window.__kgpTopCandidate === "function") ? window.__kgpTopCandidate() : null;
        // v86-K: 실제 채택 후보(읽기 전용) — top≠adopted면 방어(id 불일치 기각) 작동 증거.
        diag.adopted = (typeof window.__kgpAdoptedCandidate === "function") ? window.__kgpAdoptedCandidate() : null;
        // v86-G(수리): 추출기가 방금 정한 Tier1 스코프(추천 캐러셀 배제 여부). _run() 뒤라 값이 서 있다.
        diag.scope = window.__kgpTier1Scope || null;
        diag.pageGoodsId = (typeof window.__kgpPageGoodsId === "function") ? (window.__kgpPageGoodsId() || "") : "";
        if (diag.pageGoodsId) {
          diag.matched = !!(typeof window.__kgpMatchCapture === "function" && window.__kgpMatchCapture(diag.pageGoodsId));
          diag.mismatch = !diag.matched;
        }
      } catch (_) {}
      window.postMessage({ __kgpRes: e.data.__kgpReq, meta: meta, diag: diag }, "*");
    } catch (_) {}
  }, false);
})();
