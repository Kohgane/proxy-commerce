/* static/api_docs.js — API 문서 클라이언트 필터 (Phase 123, vanilla JS) */
(function () {
  'use strict';

  var searchInput = document.getElementById('search-input');
  var methodCheckboxes = document.querySelectorAll('.method-filter');

  /**
   * 현재 활성화된 메서드 집합을 반환한다.
   * @returns {Set<string>}
   */
  function activeMethods() {
    var active = new Set();
    methodCheckboxes.forEach(function (cb) {
      if (cb.checked) active.add(cb.value.toUpperCase());
    });
    return active;
  }

  /**
   * 검색어와 메서드 필터를 적용하여 각 endpoint-row를 보이기/숨기고,
   * 그룹(accordion-item)은 표시할 항목이 없으면 숨긴다.
   */
  function applyFilter() {
    var query = searchInput ? searchInput.value.trim().toLowerCase() : '';
    var methods = activeMethods();

    document.querySelectorAll('.accordion-item').forEach(function (item) {
      var visibleCount = 0;
      item.querySelectorAll('.endpoint-row').forEach(function (row) {
        var method = (row.dataset.method || '').toUpperCase();
        var path = (row.dataset.path || '').toLowerCase();
        var text = row.textContent.toLowerCase();

        var methodOk = methods.has(method);
        var queryOk = !query || path.includes(query) || text.includes(query);

        if (methodOk && queryOk) {
          row.classList.remove('hidden');
          visibleCount++;
        } else {
          row.classList.add('hidden');
        }
      });

      /* 그룹 자체를 숨기거나 보여준다 */
      if (visibleCount === 0) {
        item.classList.add('hidden');
      } else {
        item.classList.remove('hidden');
        /* 검색 중일 때는 해당 그룹 accordion을 자동 펼침 */
        if (query) {
          var collapseEl = item.querySelector('.accordion-collapse');
          if (collapseEl && !collapseEl.classList.contains('show')) {
            collapseEl.classList.add('show');
            var btn = item.querySelector('.accordion-button');
            if (btn) btn.classList.remove('collapsed');
          }
        }
      }
    });
  }

  /* 이벤트 바인딩 */
  if (searchInput) {
    searchInput.addEventListener('input', applyFilter);
  }
  methodCheckboxes.forEach(function (cb) {
    cb.addEventListener('change', applyFilter);
  });
})();
