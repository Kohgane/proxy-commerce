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

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from flask import Blueprint, jsonify, redirect, render_template_string, request, session, url_for

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

bp = Blueprint("ai_listing", __name__, url_prefix="/seller/listing")

# 사용자별 일일 사용량 카운터 (인메모리)
_daily_usage: Dict[str, Dict[str, Any]] = {}


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


# ── 페이지 라우트 ────────────────────────────────────────────────────────────

_AI_CREATE_PAGE = """
{% extends "_base.html" %}
{% block title %}🤖 AI 상품등록{% endblock %}
{% block content %}
<div class="container-fluid px-0">
  <h4 class="mb-3 fw-bold">🤖 AI 상품등록 자동화 <small class="text-muted fs-6">Phase 149</small></h4>

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
      </div>
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

async function runAnalysis() {
  const btn = document.getElementById('analyzeBtn');
  btn.disabled = true;
  btn.textContent = '🔄 분석 중...';

  const imageUrl = document.getElementById('imageUrl').value.trim();
  const markets = Array.from(document.querySelectorAll('input[name=markets]:checked')).map(e => e.value);
  const language = document.getElementById('language').value;
  const priceMode = document.getElementById('priceMode').value;

  if (!imageUrl && !document.getElementById('imageFiles').files.length) {
    alert('이미지 URL 또는 파일을 선택하세요.');
    btn.disabled = false;
    btn.textContent = '🤖 AI 자동 생성';
    return;
  }

  try {
    // 분석 API 호출
    const analyzeResp = await fetch('/api/ai-listing/analyze', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({image_url: imageUrl, language, markets})
    });
    const analyzeData = await analyzeResp.json();
    if (!analyzeData.ok) {
      alert('분석 실패: ' + (analyzeData.error || '알 수 없는 오류'));
      btn.disabled = false;
      btn.textContent = '🤖 AI 자동 생성';
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
    showResults(imageUrl, _analysis, _generated, markets);

  } catch (e) {
    alert('오류: ' + e.message);
  }

  btn.disabled = false;
  btn.textContent = '🤖 다시 분석';
}

function showResults(imageUrl, analysis, generated, markets) {
  document.getElementById('resultsSection').style.display = '';

  // 이미지 미리보기
  if (imageUrl) {
    const img = document.getElementById('previewImg');
    img.src = imageUrl;
    img.style.display = '';
  }

  // 분석 결과 카드
  const card = document.getElementById('analysisCard');
  card.innerHTML = [
    '<strong>카테고리</strong>: ' + (analysis.category || '-'),
    '<strong>브랜드</strong>: ' + (analysis.brand || '-'),
    '<strong>색상</strong>: ' + (analysis.colors || []).join(', '),
    '<strong>키워드</strong>: ' + (analysis.keywords || []).join(', '),
    '<strong>추정 가격</strong>: ₩' + ((analysis.estimated_price_range||{}).min||'-') + ' ~ ₩' + ((analysis.estimated_price_range||{}).max||'-'),
  ].map(s => '<div class="mb-1">' + s + '</div>').join('');

  // 마켓별 탭
  const tabs = document.getElementById('marketTabs');
  const content = document.getElementById('marketTabContent');
  tabs.innerHTML = '';
  content.innerHTML = '';
  markets.forEach((market, i) => {
    const active = i === 0 ? 'active' : '';
    tabs.innerHTML += `<li class="nav-item"><a class="nav-link ${active}" data-bs-toggle="tab" href="#tab_${market}">${market}</a></li>`;
    const mdata = (generated.markets || {})[market] || {};
    content.innerHTML += `
      <div class="tab-pane fade ${i===0?'show active':''}" id="tab_${market}">
        <div class="mb-2">
          <label class="fw-semibold small">제목 (${(mdata.title||'').length}자)</label>
          <input class="form-control form-control-sm" id="title_${market}" value="${(mdata.title||'').replace(/"/g,'&quot;')}">
        </div>
        <div class="mb-2">
          <label class="fw-semibold small">카테고리 코드</label>
          <input class="form-control form-control-sm" value="${mdata.category_code||''}" readonly>
        </div>
        <div class="mb-2">
          <label class="fw-semibold small">제안 가격 (원)</label>
          <input type="number" class="form-control form-control-sm" id="price_${market}" value="${mdata.suggested_price_krw||''}">
        </div>
        <div class="mb-2">
          <label class="fw-semibold small">설명</label>
          <textarea class="form-control form-control-sm" rows="3" id="desc_${market}">${mdata.description||''}</textarea>
        </div>
        <div class="mb-2">
          <label class="fw-semibold small">태그</label>
          <input class="form-control form-control-sm" value="${(mdata.tags||[]).join(', ')}">
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
    all_markets = ["coupang", "smartstore", "11st", "gmarket"]
    return render_template_string(
        _AI_CREATE_PAGE,
        enabled=_ENABLED,
        max_images=_MAX_IMAGES,
        max_daily=_MAX_DAILY_PER_USER,
        default_markets=_DEFAULT_MARKETS,
        all_markets=all_markets,
        default_lang=_DEFAULT_LANG,
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

    if not image_url and not page_url:
        return jsonify({"ok": False, "error": "image_url 또는 page_url 필수"}), 400

    try:
        from src.ai_listing.analyzer import analyze_image

        analysis = analyze_image(
            image_url=image_url,
            language=language,
            page_url=page_url,
        )
        listing_id = str(uuid.uuid4())
        return jsonify({"ok": True, "listing_id": listing_id, "analysis": analysis})
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
            generate_title,
            generate_description,
            generate_tags,
        )
        from src.ai_listing.category_mapper import get_category_code
        from src.ai_listing.price_suggester import suggest_price

        result: Dict[str, Any] = {}
        for market in markets:
            result[market] = {
                "title": generate_title(analysis, market, language),
                "description": generate_description(analysis, market, language),
                "tags": generate_tags(analysis, language),
                "category_code": get_category_code(analysis.get("category", ""), market),
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
        "message": "Phase 149 mock status",
    })


def ai_listing_stats() -> Dict[str, Any]:
    """AI 등록 24h 통계."""
    from src.ai_listing.analyzer import cache_stats
    from src.ai_listing.multi_publisher import publisher_stats

    cache = cache_stats()
    pub = publisher_stats()
    return {
        "enabled": _ENABLED,
        "vision_provider": os.getenv("AI_LISTING_VISION_PROVIDER", "mock"),
        "vision_model": os.getenv("AI_LISTING_VISION_MODEL", "gpt-4o-mini"),
        "max_daily_per_user": _MAX_DAILY_PER_USER,
        "default_markets": _DEFAULT_MARKETS,
        "cache_active": cache.get("active", 0),
        "cache_ttl_hours": cache.get("ttl_hours", 24),
        **pub,
    }
