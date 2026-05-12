"""src/ai_listing/routes.py — AI 상품등록 Blueprint (Phase 149).

라우트:
  GET  /seller/listing/ai-create           — AI 등록 UI 메인 페이지
  POST /api/ai-listing/analyze             — 이미지 분석 API
  POST /api/ai-listing/generate            — 제목/설명/태그 생성 API
  POST /api/ai-listing/publish             — 멀티마켓 동시 등록 API
  GET  /api/ai-listing/status/<listing_id> — 등록 상태 조회

환경변수:
  AI_LISTING_ENABLED            1 = 활성화
  AI_LISTING_MAX_DAILY_PER_USER 50 = 사용자별 일일 한도
"""
from __future__ import annotations

import logging
import os
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from flask import Blueprint, jsonify, render_template_string, request, session

logger = logging.getLogger(__name__)

_ENABLED = os.getenv("AI_LISTING_ENABLED", "1") == "1"
_MAX_DAILY_PER_USER = int(os.getenv("AI_LISTING_MAX_DAILY_PER_USER", "50"))
_MAX_IMAGES = int(os.getenv("AI_LISTING_MAX_IMAGES_PER_REQUEST", "5"))
_DEFAULT_MARKETS = [
    m.strip()
    for m in os.getenv("AI_LISTING_MARKETS_DEFAULT", "coupang,smartstore").split(",")
    if m.strip()
]
_DEFAULT_LANG = os.getenv("AI_LISTING_LANG_DEFAULT", "kr")
_URL_HEAD_CHECK_ENABLED = os.getenv("AI_LISTING_URL_HEAD_CHECK", "1") == "1"
_FORCE_REFRESH_ALLOWED = os.getenv("AI_LISTING_FORCE_REFRESH_ALLOWED", "1") == "1"
_DEBUG_PANEL_ENABLED = os.getenv("AI_LISTING_DEBUG_PANEL", "1") == "1"
_PROMPT_VERSION = os.getenv("AI_LISTING_PROMPT_VERSION", "v2_explicit_fields")

bp = Blueprint("ai_listing", __name__, url_prefix="/seller/listing")

# 사용자별 일일 사용량 카운터 (인메모리)
_daily_usage: Dict[str, Dict[str, Any]] = {}
_analyze_events: list[Dict[str, Any]] = []


def _check_daily_limit(user_id: str) -> bool:
    """사용자별 일일 한도 체크. True = 통과, False = 초과."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    key = f"{user_id}:{today}"
    entry = _daily_usage.get(key, {"count": 0, "date": today})
    if entry["count"] >= _MAX_DAILY_PER_USER:
        return False
    entry["count"] += 1
    _daily_usage[key] = entry
    return True


def _user_id() -> str:
    return str(session.get("user_id", "anonymous"))


def _truthy(val: Any) -> bool:
    return str(val).strip().lower() in {"1", "true", "yes", "on"}


def _is_force_refresh_requested(data: Dict[str, Any]) -> bool:
    if not _FORCE_REFRESH_ALLOWED:
        return False
    return _truthy(request.args.get("force_refresh")) or _truthy(data.get("force_refresh"))


def _build_confidence_badges(analysis: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    def _badge(value: Any, source: str = "") -> Dict[str, str]:
        has_value = bool(value)
        if not has_value:
            return {"level": "empty", "icon": "🔴", "label": "빈 값"}
        if source == "jsonld":
            return {"level": "jsonld", "icon": "🟢", "label": "JSON-LD"}
        if source in {"scraping", "og"}:
            return {"level": "scraped", "icon": "🟢", "label": "스크래핑 성공"}
        return {"level": "ai", "icon": "🟡", "label": "AI 추론"}

    return {
        "title": _badge(
            (analysis.get("json_ld_normalized") or {}).get("name") or analysis.get("_scraped_title"),
            str(analysis.get("_title_source") or ""),
        ),
        "category": _badge(analysis.get("category"), str(analysis.get("_category_source") or "")),
        "brand": _badge(analysis.get("brand"), str(analysis.get("_brand_source") or "")),
        "description": _badge(analysis.get("source_description"), str(analysis.get("_description_source") or "")),
        "keywords": _badge(analysis.get("keywords"), "ai"),
        "estimated_price_range": _badge(analysis.get("estimated_price_range"), str(analysis.get("_price_source") or "")),
        "variants": _badge(analysis.get("variants"), str(analysis.get("_variants_source") or "")),
    }


def _count_extracted_fields(analysis: Dict[str, Any]) -> int:
    fields = [
        analysis.get("category"),
        analysis.get("brand"),
        analysis.get("colors"),
        analysis.get("materials"),
        analysis.get("keywords"),
        analysis.get("estimated_price_range"),
        analysis.get("price_candidates"),
        analysis.get("size_options"),
        analysis.get("origin_country"),
        analysis.get("scraped_images"),
    ]
    return sum(1 for f in fields if bool(f))


def _record_analyze_event(analysis: Dict[str, Any], page_url: str, scraper_called: bool) -> None:
    _analyze_events.append({
        "at": datetime.now(timezone.utc),
        "scraper_called": scraper_called,
        "http_200": (analysis.get("_debug", {}) or {}).get("http_status") == 200,
        "json_ld": bool((analysis.get("_debug", {}) or {}).get("json_ld")),
        "og_tags": bool((analysis.get("_debug", {}) or {}).get("og_tags")),
        "cache_hit": bool(analysis.get("_analysis_cache_hit") or (analysis.get("_debug", {}) or {}).get("scraper_cache_hit")),
        "prompt_version": str(analysis.get("_prompt_version") or "unknown"),
        "extracted_fields": _count_extracted_fields(analysis),
        "price_extracted": bool(analysis.get("source_price_krw")),
        "variants_count": len(analysis.get("variants") or []),
        "fx_conversion_used": bool(analysis.get("fx_rate")),
        "page_url": bool(page_url),
    })
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    _analyze_events[:] = [e for e in _analyze_events if e.get("at") and e["at"] >= cutoff]


# ── 페이지 라우트 ────────────────────────────────────────────────────────────

_AI_CREATE_PAGE = """
{% extends "_base.html" %}
{% from "_macros.html" import phase_header %}
{% block title %}🤖 AI 상품등록{% endblock %}
{% block content %}
<div class="container-fluid px-0">
  {{ phase_header("🤖 AI 상품등록 자동화", current_phase) }}

  {% if not enabled %}
  <div class="alert alert-warning">⚠️ AI 상품등록 기능이 비활성화되어 있습니다 (AI_LISTING_ENABLED=0).</div>
  {% endif %}

  <!-- Step 1: 이미지 업로드 -->
  <div class="card mb-4">
    <div class="card-header fw-bold">📸 Step 1 — 이미지 업로드</div>
    <div class="card-body">
      <div class="row g-3">
        <div class="col-md-6">
          <label class="form-label fw-semibold">이미지 파일 업로드 (최대 {{ max_images }}장, JPG/PNG/WEBP)</label>
          <input type="file" id="imageFiles" class="form-control" multiple accept="image/*">
          <div class="mt-2" id="imagePreview"></div>
        </div>
        <div class="col-md-6">
          <label class="form-label fw-semibold">또는 이미지 URL 입력</label>
          <input type="url" id="imageUrl" class="form-control" placeholder="https://example.com/product.jpg">
          <small class="text-muted">URL 1개씩 입력하여 분석 가능</small>
        </div>
        <div class="col-md-12">
          <label class="form-label fw-semibold">상품 페이지 URL (선택)</label>
          <input type="url" id="pageUrl" class="form-control" placeholder="https://example.com/products/item">
          <small class="text-muted">URL 입력 시 접근 가능(HEAD 200) 확인 후 스크래핑 + AI 분석을 진행합니다.</small>
        </div>
      </div>
      <div id="analyzeWarning" class="alert alert-danger mt-3" style="display:none"></div>
    </div>
  </div>

  <!-- Step 2: 옵션 설정 -->
  <div class="card mb-4">
    <div class="card-header fw-bold">⚙️ Step 2 — 등록 옵션</div>
    <div class="card-body">
      <div class="row g-3">
        <div class="col-md-4">
          <label class="form-label fw-semibold">대상 마켓</label>
          <div>
            {% for market in all_markets %}
            <div class="form-check form-check-inline">
              <input class="form-check-input" type="checkbox" id="market_{{ market }}" name="markets"
                     value="{{ market }}" {% if market in default_markets %}checked{% endif %}>
              <label class="form-check-label" for="market_{{ market }}">{{ market }}</label>
            </div>
            {% endfor %}
          </div>
        </div>
        <div class="col-md-4">
          <label class="form-label fw-semibold">언어</label>
          <select id="language" class="form-select">
            <option value="kr" {% if default_lang == 'kr' %}selected{% endif %}>한국어</option>
            <option value="jp" {% if default_lang == 'jp' %}selected{% endif %}>日本語</option>
            <option value="both" {% if default_lang == 'both' %}selected{% endif %}>한국어 + 日本語</option>
          </select>
        </div>
        <div class="col-md-4">
          <label class="form-label fw-semibold">가격 모드</label>
          <select id="priceMode" class="form-select">
            <option value="auto">자동 (가격 룰 적용)</option>
            <option value="manual">수동 설정</option>
          </select>
        </div>
      </div>
      <div class="mt-3">
        <button id="analyzeBtn" class="btn btn-primary px-4" style="min-height:44px"
                onclick="runAnalysis()" {% if not enabled %}disabled{% endif %}>
          🤖 AI 자동 생성
        </button>
        <small class="text-muted ms-3">일일 한도: {{ max_daily }}건 / 현재 비용 가드가 활성</small>
      </div>
    </div>
  </div>

  <!-- Step 3: 결과 미리보기 (동적) -->
  <div id="resultsSection" style="display:none">
    <div class="card mb-4">
      <div class="card-header fw-bold">📋 Step 3 — AI 분석 결과</div>
      <div class="card-body">
        <div class="row">
          <div class="col-md-4">
            <img id="previewImg" src="" class="img-fluid rounded mb-2" style="max-height:250px;display:none">
            <div id="analysisCard" class="p-3 bg-light rounded small"></div>
          </div>
          <div class="col-md-8">
            <ul class="nav nav-tabs" id="marketTabs"></ul>
            <div class="tab-content pt-3" id="marketTabContent"></div>
          </div>
        </div>
      </div>
    </div>

    <!-- Step 4: 등록 실행 -->
    <div class="card mb-4">
      <div class="card-header fw-bold">🚀 Step 4 — 선택 마켓에 등록</div>
      <div class="card-body">
        <div id="publishProgress"></div>
        <button id="publishBtn" class="btn btn-success px-4" style="min-height:44px"
                onclick="publishToMarkets()">
          📤 선택한 마켓에 등록
        </button>
      </div>
    </div>
  </div>

  <!-- 등록 결과 카드 -->
  <div id="publishResults" style="display:none"></div>
</div>

<script>
let _listingId = null;
let _analysis = null;
let _generated = null;
const DEBUG_PANEL_ENABLED = {{ 'true' if debug_panel_enabled else 'false' }};
const escapeHtml = (value) => String(value ?? '')
  .replace(/&/g, '&amp;')
  .replace(/</g, '&lt;')
  .replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;')
  .replace(/'/g, '&#39;');
 
async function runAnalysis() {
  const btn = document.getElementById('analyzeBtn');
  const warning = document.getElementById('analyzeWarning');
  warning.style.display = 'none';
  warning.textContent = '';
  btn.disabled = true;
  btn.textContent = '🔄 분석 중...';

  const imageUrl = document.getElementById('imageUrl').value.trim();
  const pageUrl = document.getElementById('pageUrl').value.trim();
  const markets = Array.from(document.querySelectorAll('input[name=markets]:checked')).map(e => e.value);
  const language = document.getElementById('language').value;
  const priceMode = document.getElementById('priceMode').value;
  const hasExistingAnalysis = !!_analysis;

  if (!imageUrl && !pageUrl && !document.getElementById('imageFiles').files.length) {
    warning.textContent = '이미지 URL/파일 또는 상품 페이지 URL을 입력하세요.';
    warning.style.display = '';
    btn.disabled = false;
    btn.textContent = '🤖 AI 자동 생성';
    return;
  }

  try {
    const analyzeUrl = hasExistingAnalysis ? '/api/ai-listing/analyze?force_refresh=1' : '/api/ai-listing/analyze';
    // 분석 API 호출
    const analyzeResp = await fetch(analyzeUrl, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({image_url: imageUrl, page_url: pageUrl, language, markets, force_refresh: hasExistingAnalysis ? 1 : 0})
    });
    const analyzeData = await analyzeResp.json();
    if (!analyzeData.ok) {
      warning.textContent = analyzeData.error || '알 수 없는 오류';
      warning.style.display = '';
      btn.disabled = false;
      btn.textContent = _analysis ? '🔄 다시 분석 (캐시 무시)' : '🤖 AI 자동 생성';
      return;
    }
    _analysis = analyzeData.analysis;
    _listingId = analyzeData.listing_id;

    // 생성 API 호출
    const genResp = await fetch('/api/ai-listing/generate', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({listing_id: _listingId, analysis: _analysis, markets, language, price_mode: priceMode})
    });
    _generated = await genResp.json();

    // 결과 표시
    showResults(
      imageUrl || ((analyzeData.debug_panel || {}).image_urls || [])[0] || '',
      _analysis,
      _generated,
      markets,
      analyzeData.confidence_badges || {},
      analyzeData.debug_panel || {}
    );

  } catch (e) {
    warning.textContent = '오류: ' + e.message;
    warning.style.display = '';
  }

  btn.disabled = false;
  btn.textContent = '🔄 다시 분석 (캐시 무시)';
}

function showResults(imageUrl, analysis, generated, markets, confidenceBadges, debugPanel) {
  document.getElementById('resultsSection').style.display = '';

  // 이미지 미리보기
  if (imageUrl) {
    const img = document.getElementById('previewImg');
    img.src = imageUrl;
    img.style.display = '';
  }

  // 분석 결과 카드
  const card = document.getElementById('analysisCard');
  const badge = (k) => {
    const b = confidenceBadges[k] || {icon: '🔴', label: '빈 값'};
    return ` <span class="badge text-bg-light border ms-1">${b.icon} ${b.label}</span>`;
  };
  const sourceTitle = (analysis.json_ld_normalized || {}).name || analysis._scraped_title || '-';
  const sourceDescription = analysis.source_description || '-';
  const sourcePrice = analysis.source_price || {};
  const sourcePriceDisplay = sourcePrice.amount && sourcePrice.currency
    ? `${sourcePrice.amount} ${sourcePrice.currency} → ₩${(analysis.source_price_krw || 0).toLocaleString()}`
    : '-';
  card.innerHTML = [
    '<strong>원본 제목</strong>: ' + escapeHtml(sourceTitle) + badge('title'),
    '<strong>카테고리</strong>: ' + escapeHtml(analysis.category || '-') + badge('category'),
    '<strong>브랜드</strong>: ' + (analysis.brand || '-') + badge('brand'),
    '<strong>색상</strong>: ' + escapeHtml((analysis.colors || []).join(', ')),
    '<strong>사이즈</strong>: ' + escapeHtml((analysis.size_options || []).join(', ')),
    '<strong>키워드</strong>: ' + (analysis.keywords || []).join(', ') + badge('keywords'),
    '<strong>가격</strong>: ' + escapeHtml(sourcePriceDisplay) + badge('estimated_price_range'),
    '<strong>설명</strong>: ' + escapeHtml(sourceDescription) + badge('description'),
    '<strong>변형</strong>: ' + ((analysis.variants || []).length || 0) + '개' + badge('variants'),
  ].map(s => '<div class="mb-1">' + s + '</div>').join('');
  if (DEBUG_PANEL_ENABLED) {
    card.innerHTML += `
      <details class="mt-3">
        <summary class="fw-semibold">📋 원본 데이터</summary>
        <pre class="small bg-white border rounded p-2 mt-2 mb-0" style="white-space:pre-wrap">${JSON.stringify({
          http_status: debugPanel.http_status,
          response_size: debugPanel.response_size,
          json_ld: debugPanel.json_ld,
          json_ld_normalized: debugPanel.json_ld_normalized,
          og_tags: debugPanel.og_tags,
          meta_description: debugPanel.meta_description,
          image_urls: debugPanel.image_urls,
          source_price: debugPanel.source_price,
          variants: debugPanel.variants,
          prompt_version: debugPanel.prompt_version,
          cache: debugPanel.cache,
        }, null, 2)}</pre>
      </details>
    `;
  }

  // 마켓별 탭
  const tabs = document.getElementById('marketTabs');
  const content = document.getElementById('marketTabContent');
  tabs.innerHTML = '';
  content.innerHTML = '';
  markets.forEach((market, i) => {
    const active = i === 0 ? 'active' : '';
    tabs.innerHTML += `<li class="nav-item"><a class="nav-link ${active}" data-bs-toggle="tab" href="#tab_${market}">${market}</a></li>`;
    const mdata = (generated.markets || {})[market] || {};
    const variants = mdata.variants || [];
    const variantRows = variants.map(v => `<tr><td>${escapeHtml(v.color || '-')}</td><td>${escapeHtml(v.size || '-')}</td><td>${escapeHtml(v.sku || '-')}</td><td>${escapeHtml(v.gtin || '-')}</td></tr>`).join('');
    const sourcePriceText = mdata.source_price && mdata.source_price.amount
      ? `${mdata.source_price.amount} ${mdata.source_price.currency}`
      : '-';
    content.innerHTML += `
      <div class="tab-pane fade ${i===0?'show active':''}" id="tab_${market}">
        <div class="mb-2">
          <label class="fw-semibold small">제목 (${(mdata.title||'').length}자)</label>
          <input class="form-control form-control-sm" id="title_${market}" value="${escapeHtml(mdata.title||'')}">
          <div class="form-text">원본 제목: ${escapeHtml((analysis.json_ld_normalized || {}).name || mdata.title || '-')}</div>
        </div>
        <div class="mb-2">
          <label class="fw-semibold small">카테고리</label>
          <input class="form-control form-control-sm mb-1" value="${escapeHtml(mdata.category_text||'')}" readonly>
          <label class="fw-semibold small">카테고리 코드</label>
          <input class="form-control form-control-sm" value="${mdata.category_code||''}" readonly>
        </div>
        <div class="mb-2">
          <label class="fw-semibold small">제안 가격 (원)</label>
          <input type="number" class="form-control form-control-sm" id="price_${market}" value="${mdata.suggested_price_krw||''}">
          <div class="form-text">원본가: ${escapeHtml(sourcePriceText)} · 환산가: ₩${(mdata.source_price_krw||0).toLocaleString()} · 환율: ${escapeHtml(mdata.fx_rate || '-')} KRW/${escapeHtml((mdata.source_price||{}).currency || '')}</div>
          <div class="form-text">마진 가드 후 제안가: ₩${(mdata.margin_guard_price_krw||mdata.suggested_price_krw||0).toLocaleString()}</div>
        </div>
        <div class="mb-2">
          <label class="fw-semibold small">브랜드 / 소재</label>
          <div class="form-control form-control-sm bg-light">${escapeHtml(mdata.brand || '-')} / ${escapeHtml(mdata.material || '-')}</div>
        </div>
        <div class="mb-2">
          <label class="fw-semibold small">옵션 자동 분리 (${mdata.variant_count || 0}개 변형 감지)</label>
          <div class="small mb-1">색상: ${(mdata.colors||[]).map(c => `<span class="badge text-bg-light border me-1">${escapeHtml(c)}</span>`).join('') || '-'}</div>
          <div class="small mb-1">사이즈: ${(mdata.sizes||[]).map(s => `<span class="badge text-bg-light border me-1">${escapeHtml(s)}</span>`).join('') || '-'}</div>
          <details class="small">
            <summary>SKU / GTIN 보기</summary>
            <div class="table-responsive mt-2">
              <table class="table table-sm table-bordered">
                <thead><tr><th>색상</th><th>사이즈</th><th>SKU</th><th>GTIN</th></tr></thead>
                <tbody>${variantRows || '<tr><td colspan="4" class="text-muted">변형 없음</td></tr>'}</tbody>
              </table>
            </div>
          </details>
        </div>
        <div class="mb-2">
          <label class="fw-semibold small">설명</label>
          <textarea class="form-control form-control-sm" rows="3" id="desc_${market}">${escapeHtml(mdata.description||'')}</textarea>
          <details class="small mt-1">
            <summary>원문/번역 보기</summary>
            <div class="text-muted mt-1">번역 상태: ${escapeHtml(mdata.description_translation_status || 'unknown')}</div>
            <div class="mt-2"><strong>원문</strong><div class="border rounded bg-light p-2">${escapeHtml(mdata.description_original || '-')}</div></div>
            <div class="mt-2"><strong>한국어</strong><div class="border rounded bg-light p-2">${escapeHtml(mdata.description_kr || '-')}</div></div>
          </details>
        </div>
        <div class="mb-2">
          <label class="fw-semibold small">태그</label>
          <input class="form-control form-control-sm" value="${escapeHtml((mdata.tags||[]).join(', '))}">
        </div>
      </div>`;
  });
}

async function publishToMarkets() {
  if (!_listingId) { alert('먼저 AI 분석을 실행하세요.'); return; }
  const btn = document.getElementById('publishBtn');
  btn.disabled = true;
  btn.textContent = '⏳ 등록 중...';

  const markets = Array.from(document.querySelectorAll('input[name=markets]:checked')).map(e => e.value);
  const language = document.getElementById('language').value;

  // 인라인 편집 값 수집
  const marketData = {};
  markets.forEach(m => {
    marketData[m] = {
      title: (document.getElementById('title_' + m)||{}).value || '',
      description: (document.getElementById('desc_' + m)||{}).value || '',
      price_krw: parseInt((document.getElementById('price_' + m)||{}).value || '0'),
    };
  });

  try {
    const resp = await fetch('/api/ai-listing/publish', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({listing_id: _listingId, markets, market_data: marketData, language, analysis: _analysis})
    });
    const data = await resp.json();
    showPublishResults(data);
  } catch (e) {
    alert('등록 오류: ' + e.message);
  }
  btn.disabled = false;
  btn.textContent = '📤 선택한 마켓에 등록';
}

function showPublishResults(data) {
  const el = document.getElementById('publishResults');
  el.style.display = '';
  const results = (data.results || {}).markets || [];
  const rows = results.map(r => {
    const icon = r.status === 'success' ? '✅' : '❌';
    const retry = r.status === 'failed' ? `<button class='btn btn-xs btn-outline-danger ms-2 btn-sm' onclick='retryMarket("${r.market}")'>재시도</button>` : '';
    return `<li class='list-group-item d-flex justify-content-between align-items-center'>
      <span>${icon} <strong>${r.market}</strong> ${r.external_product_id ? '— ID: ' + r.external_product_id : ''}</span>
      <span>${r.error_message ? '<span class=text-danger small>' + r.error_message + '</span>' : ''} ${retry}</span>
    </li>`;
  }).join('');
  el.innerHTML = `<div class='card mb-4'><div class='card-header fw-bold'>📊 등록 결과</div>
    <div class='card-body'><ul class='list-group'>${rows || '<li class=list-group-item>결과 없음</li>'}</ul></div></div>`;
}
</script>
{% endblock %}
"""


@bp.get("/ai-create")
def ai_listing_create():
    """AI 상품등록 자동화 페이지 (Phase 149)."""
    try:
        from src.version import get_current_phase
        current_phase = get_current_phase()
    except Exception:
        current_phase = 151
    all_markets = ["coupang", "smartstore", "11st", "gmarket"]
    return render_template_string(
        _AI_CREATE_PAGE,
        enabled=_ENABLED,
        max_images=_MAX_IMAGES,
        max_daily=_MAX_DAILY_PER_USER,
        default_markets=_DEFAULT_MARKETS,
        all_markets=all_markets,
        default_lang=_DEFAULT_LANG,
        current_phase=current_phase,
        debug_panel_enabled=_DEBUG_PANEL_ENABLED,
        page="ai_listing_create",
    )


# ── API 라우트 ────────────────────────────────────────────────────────────────

ai_api_bp = Blueprint("ai_listing_api", __name__, url_prefix="/api/ai-listing")


@ai_api_bp.post("/analyze")
def api_analyze():
    """이미지 분석 API.

    Request JSON: {image_url, language, markets}
    Response: {ok, listing_id, analysis}
    """
    if not _ENABLED:
        return jsonify({"ok": False, "error": "AI_LISTING_ENABLED=0"}), 403

    user_id = _user_id()
    if not _check_daily_limit(user_id):
        return jsonify({
            "ok": False,
            "error": f"일일 한도 초과 ({_MAX_DAILY_PER_USER}건/일)",
        }), 429

    data = request.get_json(force=True) or {}
    image_url = str(data.get("image_url") or "").strip()
    page_url = str(data.get("page_url") or "").strip()
    language = str(data.get("language") or _DEFAULT_LANG)
    force_refresh = _is_force_refresh_requested(data)

    if not image_url and not page_url:
        return jsonify({"ok": False, "error": "image_url 또는 page_url 필수"}), 400

    try:
        from src.ai_listing.analyzer import analyze_image
        from src.ai_listing.url_scraper import head_check_url, scrape_product_page

        if page_url and _URL_HEAD_CHECK_ENABLED:
            head = head_check_url(page_url)
            if not head.get("ok"):
                status = head.get("status")
                status_txt = f"HTTP {status}" if status is not None else "연결 실패"
                return jsonify({
                    "ok": False,
                    "error": f"이 URL에 접근할 수 없습니다 ({status_txt}). URL을 확인해주세요.",
                    "url_head_check": {
                        "ok": False,
                        "status": status,
                    },
                }), 400

        scrape_data = None
        if page_url:
            scrape_data = scrape_product_page(page_url, force_refresh=force_refresh)

        analysis = analyze_image(
            image_url=image_url,
            language=language,
            force_refresh=force_refresh,
            page_url=page_url,
            prompt_version=_PROMPT_VERSION,
            scrape_data=scrape_data,
        )
        confidence_badges = _build_confidence_badges(analysis)
        debug_panel = {
            **(analysis.get("_debug", {}) or {}),
            "prompt_version": analysis.get("_prompt_version", _PROMPT_VERSION),
            "cache": {
                "analysis": "hit" if analysis.get("_analysis_cache_hit") else "miss",
                "scraper": "hit" if (analysis.get("_debug", {}) or {}).get("scraper_cache_hit") else "miss",
            },
        }
        _record_analyze_event(
            analysis=analysis,
            page_url=page_url,
            scraper_called=bool(page_url),
        )
        listing_id = str(uuid.uuid4())
        return jsonify({
            "ok": True,
            "listing_id": listing_id,
            "analysis": analysis,
            "confidence_badges": confidence_badges,
            "debug_panel": debug_panel,
        })
    except Exception as exc:
        logger.warning("AI 분석 오류: %s", exc)
        return jsonify({"ok": False, "error": "AI 분석 중 오류가 발생했습니다."}), 500


@ai_api_bp.post("/generate")
def api_generate():
    """제목/설명/태그/가격 생성 API.

    Request JSON: {listing_id, analysis, markets, language, price_mode}
    Response: {ok, markets: {market: {title, description, tags, category_code, suggested_price_krw}}}
    """
    if not _ENABLED:
        return jsonify({"ok": False, "error": "AI_LISTING_ENABLED=0"}), 403

    data = request.get_json(force=True) or {}
    analysis = data.get("analysis") or {}
    markets = data.get("markets") or _DEFAULT_MARKETS
    language = str(data.get("language") or _DEFAULT_LANG)
    price_mode = str(data.get("price_mode") or "auto")

    try:
        from src.ai_listing.generator import (
            build_listing_content,
            generate_title,
            generate_description,
            generate_tags,
        )
        from src.ai_listing.category_mapper import get_category_code
        from src.ai_listing.price_suggester import suggest_price

        result: Dict[str, Any] = {}
        for market in markets:
            listing = build_listing_content(analysis, market, language)
            result[market] = {
                "title": generate_title(analysis, market, language),
                "description": generate_description(analysis, market, language),
                "description_original": listing.get("description_original", ""),
                "description_kr": listing.get("description_kr", ""),
                "description_translation_status": listing.get("description_translation_status", ""),
                "tags": generate_tags(analysis, language),
                "category_text": listing.get("category_text", ""),
                "brand": listing.get("brand", ""),
                "colors": listing.get("colors", []),
                "sizes": listing.get("sizes", []),
                "variants": listing.get("variants", []),
                "material": listing.get("material", ""),
                "variant_count": len(listing.get("variants", [])),
                "category_code": get_category_code(listing.get("category_text", "") or analysis.get("category", ""), market),
                **suggest_price(analysis, market, mode=price_mode),
            }

        return jsonify({"ok": True, "markets": result})
    except Exception as exc:
        logger.warning("AI 생성 오류: %s", exc)
        return jsonify({"ok": False, "error": "콘텐츠 생성 중 오류가 발생했습니다."}), 500


@ai_api_bp.post("/publish")
def api_publish():
    """멀티마켓 동시 등록 API.

    Request JSON: {listing_id, markets, market_data, analysis, language}
    Response: {ok, results}
    """
    if not _ENABLED:
        return jsonify({"ok": False, "error": "AI_LISTING_ENABLED=0"}), 403

    data = request.get_json(force=True) or {}
    listing_id = str(data.get("listing_id") or uuid.uuid4())
    markets = data.get("markets") or _DEFAULT_MARKETS
    market_data = data.get("market_data") or {}
    analysis = data.get("analysis") or {}
    language = str(data.get("language") or _DEFAULT_LANG)

    try:
        from src.ai_listing.multi_publisher import publish_to_markets

        product_data = {
            "listing_id": listing_id,
            "analysis": analysis,
            "language": language,
            "market_data": market_data,
        }
        result = publish_to_markets(
            ai_listing_id=listing_id,
            product_data=product_data,
            markets=markets,
        )
        return jsonify({"ok": True, "results": result.to_dict()})
    except Exception as exc:
        logger.warning("AI 등록 오류: %s", exc)
        return jsonify({"ok": False, "error": "마켓 등록 중 오류가 발생했습니다."}), 500


@ai_api_bp.get("/status/<listing_id>")
def api_status(listing_id: str):
    """등록 상태 조회."""
    return jsonify({
        "ok": True,
        "listing_id": listing_id,
        "status": "done",
        "message": "mock status",
    })


def ai_listing_stats() -> Dict[str, Any]:
    """AI 등록 24h 통계."""
    from src.ai_listing.analyzer import cache_stats
    from src.ai_listing.multi_publisher import publisher_stats
    from src.ai_listing.url_scraper import scraper_cache_stats

    cache = cache_stats()
    scraper_cache = scraper_cache_stats()
    pub = publisher_stats()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    events = [e for e in _analyze_events if e.get("at") and e["at"] >= cutoff]
    attempts = len(events)
    scraper_called = sum(1 for e in events if e.get("scraper_called"))
    scraper_http_200 = sum(1 for e in events if e.get("http_200"))
    json_ld_found = sum(1 for e in events if e.get("json_ld"))
    og_found = sum(1 for e in events if e.get("og_tags"))
    cache_hits = sum(1 for e in events if e.get("cache_hit"))
    price_extracted = sum(1 for e in events if e.get("price_extracted"))
    fx_conversion_used = sum(1 for e in events if e.get("fx_conversion_used"))
    avg_variants = (
        round(sum(int(e.get("variants_count", 0)) for e in events) / attempts, 2)
        if attempts else 0.0
    )
    avg_fields = (
        round(sum(int(e.get("extracted_fields", 0)) for e in events) / attempts, 2)
        if attempts else 0.0
    )
    prompt_counts = Counter(str(e.get("prompt_version", "unknown")) for e in events)
    v1_pct = round((prompt_counts.get("v1", 0) / attempts) * 100, 1) if attempts else 0.0
    v2_pct = round((prompt_counts.get("v2_explicit_fields", 0) / attempts) * 100, 1) if attempts else 0.0

    def _pct(num: int, den: int) -> float:
        return round((num / den) * 100, 1) if den else 0.0

    return {
        "enabled": _ENABLED,
        "vision_provider": os.getenv("AI_LISTING_VISION_PROVIDER", "mock"),
        "vision_model": os.getenv("AI_LISTING_VISION_MODEL", "gpt-4o-mini"),
        "max_daily_per_user": _MAX_DAILY_PER_USER,
        "default_markets": _DEFAULT_MARKETS,
        "cache_active": cache.get("active", 0),
        "cache_ttl_hours": cache.get("ttl_hours", 24),
        "attempts_24h": attempts,
        "scraper_call_rate_pct": _pct(scraper_called, attempts),
        "scraper_http_200_rate_pct": _pct(scraper_http_200, scraper_called),
        "json_ld_extraction_rate_pct": _pct(json_ld_found, scraper_called),
        "og_extraction_rate_pct": _pct(og_found, scraper_called),
        "avg_extracted_fields_10": avg_fields,
        "cache_hit_rate_pct": _pct(cache_hits, attempts),
        "jsonld_priority_enabled": os.getenv("AI_LISTING_JSONLD_PRIORITY", "1") == "1",
        "price_auto_extract_success_rate_pct": _pct(price_extracted, scraper_called),
        "avg_variants_detected": avg_variants,
        "fx_conversion_used_count": fx_conversion_used,
        "prompt_distribution": dict(prompt_counts),
        "prompt_v1_pct": v1_pct,
        "prompt_v2_pct": v2_pct,
        "scraper_cache_active": scraper_cache.get("active", 0),
        **pub,
    }
