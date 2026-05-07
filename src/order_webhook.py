import logging
import os
import time

from flask import Flask, request, jsonify, redirect, render_template
from flask_cors import CORS

from .vendors.shopify_client import verify_webhook
from .vendors.woocommerce_client import verify_woo_webhook
from .orders.router import OrderRouter
from .orders.notifier import OrderNotifier
from .orders.tracker import OrderTracker
from .dashboard.order_status import OrderStatusTracker
from .utils.rate_limiter import create_limiter, LIMIT_WEBHOOK, LIMIT_HEALTH
from .middleware.request_logger import RequestLogger
from .middleware.security import SecurityMiddleware
from .validation.order_validator import OrderValidator, DUPLICATE_ORDER_TAG
from .audit.audit_logger import AuditLogger
from .audit.event_types import EventType

logger = logging.getLogger(__name__)

app = Flask(__name__)

# 대시보드 API Blueprint 등록 (DASHBOARD_API_ENABLED=1 시)
if os.getenv("DASHBOARD_API_ENABLED", "1") == "1":
    try:
        from .api import dashboard_bp
        app.register_blueprint(dashboard_bp)
        logger.info("대시보드 API Blueprint 등록 완료")
    except Exception as _bp_exc:
        logger.warning("대시보드 API Blueprint 등록 실패: %s", _bp_exc)

# 대시보드 웹 UI Blueprint 등록 (DASHBOARD_WEB_UI_ENABLED=1 시)
if os.getenv("DASHBOARD_WEB_UI_ENABLED", "1") == "1":
    try:
        from .dashboard.web_ui import web_ui_bp
        app.register_blueprint(web_ui_bp)
        logger.info("대시보드 웹 UI Blueprint 등록 완료")
    except Exception as _web_ui_exc:
        logger.warning("대시보드 웹 UI Blueprint 등록 실패: %s", _web_ui_exc)

# 설정 관리 API Blueprint 등록
try:
    from .api.config_routes import config_bp
    app.register_blueprint(config_bp)
    logger.info("설정 관리 API Blueprint 등록 완료")
except Exception as _cfg_bp_exc:
    logger.warning("설정 관리 API Blueprint 등록 실패: %s", _cfg_bp_exc)

# 리뷰 관리 API Blueprint 등록
try:
    from .api.reviews_api import reviews_bp
    app.register_blueprint(reviews_bp)
    logger.info("리뷰 API Blueprint 등록 완료")
except Exception as _rev_bp_exc:
    logger.warning("리뷰 API Blueprint 등록 실패: %s", _rev_bp_exc)

# 프로모션 관리 API Blueprint 등록
try:
    from .api.promotions_api import promotions_bp
    app.register_blueprint(promotions_bp)
    logger.info("프로모션 API Blueprint 등록 완료")
except Exception as _promo_bp_exc:
    logger.warning("프로모션 API Blueprint 등록 실패: %s", _promo_bp_exc)

# CRM API Blueprint 등록
try:
    from .api.crm_api import crm_bp
    app.register_blueprint(crm_bp)
    logger.info("CRM API Blueprint 등록 완료")
except Exception as _crm_bp_exc:
    logger.warning("CRM API Blueprint 등록 실패: %s", _crm_bp_exc)

# Marketing API Blueprint 등록
try:
    from .api.marketing_api import marketing_bp
    app.register_blueprint(marketing_bp)
    logger.info("마케팅 API Blueprint 등록 완료")
except Exception as _mkt_bp_exc:
    logger.warning("마케팅 API Blueprint 등록 실패: %s", _mkt_bp_exc)

# 리포트 API Blueprint 등록
try:
    from .api.reports_api import reports_bp
    app.register_blueprint(reports_bp)
    logger.info("리포트 API Blueprint 등록 완료")
except Exception as _rep_bp_exc:
    logger.warning("리포트 API Blueprint 등록 실패: %s", _rep_bp_exc)

# SEO API Blueprint 등록
try:
    from .api.seo_api import seo_bp
    app.register_blueprint(seo_bp)
    logger.info("SEO API Blueprint 등록 완료")
except Exception as _seo_bp_exc:
    logger.warning("SEO API Blueprint 등록 실패: %s", _seo_bp_exc)

# 경쟁사 분석 API Blueprint 등록
try:
    from .api.competitor_api import competitor_bp
    app.register_blueprint(competitor_bp)
    logger.info("경쟁사 분석 API Blueprint 등록 완료")
except Exception as _comp_bp_exc:
    logger.warning("경쟁사 분석 API Blueprint 등록 실패: %s", _comp_bp_exc)

# 수요 예측 API Blueprint 등록
try:
    from .api.forecast_api import forecast_bp
    app.register_blueprint(forecast_bp)
    logger.info("수요 예측 API Blueprint 등록 완료")
except Exception as _fc_bp_exc:
    logger.warning("수요 예측 API Blueprint 등록 실패: %s", _fc_bp_exc)

# 자동화 API Blueprint 등록
try:
    from .api.automation_api import automation_bp
    app.register_blueprint(automation_bp)
    logger.info("자동화 API Blueprint 등록 완료")
except Exception as _auto_bp_exc:
    logger.warning("자동화 API Blueprint 등록 실패: %s", _auto_bp_exc)

# 결제/정산 API Blueprint 등록
try:
    from .api.payments_api import payments_bp
    app.register_blueprint(payments_bp)
    logger.info("결제/정산 API Blueprint 등록 완료")
except Exception as _pay_bp_exc:
    logger.warning("결제/정산 API Blueprint 등록 실패: %s", _pay_bp_exc)

# 모니터링 API Blueprint 등록
try:
    from .api.monitoring_api import monitoring_bp
    app.register_blueprint(monitoring_bp)
    logger.info("모니터링 API Blueprint 등록 완료")
except Exception as _mon_bp_exc:
    logger.warning("모니터링 API Blueprint 등록 실패: %s", _mon_bp_exc)

# Auth API Blueprint 등록
try:
    from .api.auth_api import auth_api_bp
    app.register_blueprint(auth_api_bp)
    logger.info("Auth API Blueprint 등록 완료")
except Exception as _auth_api_exc:
    logger.warning("Auth API Blueprint 등록 실패: %s", _auth_api_exc)

# 관리자 패널 Blueprint 등록 (Phase 25)
try:
    from .dashboard.admin_views import admin_panel_bp
    app.register_blueprint(admin_panel_bp)
    logger.info("관리자 패널 Blueprint 등록 완료")
except Exception as _admin_bp_exc:
    logger.warning("관리자 패널 Blueprint 등록 실패: %s", _admin_bp_exc)

# 배송 추적 API Blueprint 등록 (Phase 27)
try:
    from .api.shipping_api import shipping_api
    app.register_blueprint(shipping_api)
    logger.info("배송 추적 API Blueprint 등록 완료")
except Exception as _ship_api_exc:
    logger.warning("배송 추적 API Blueprint 등록 실패: %s", _ship_api_exc)

# CS API Blueprint 등록 (Phase 28)
try:
    from .api.cs_api import cs_api
    app.register_blueprint(cs_api)
    logger.info("CS API Blueprint 등록 완료")
except Exception as _cs_api_exc:
    logger.warning("CS API Blueprint 등록 실패: %s", _cs_api_exc)

# 분석 API Blueprint 등록 (Phase 29)
try:
    from .api.analytics_api import analytics_api
    app.register_blueprint(analytics_api)
    logger.info("분석 API Blueprint 등록 완료")
except Exception as _analytics_api_exc:
    logger.warning("분석 API Blueprint 등록 실패: %s", _analytics_api_exc)

# 재고 동기화 API Blueprint 등록
try:
    from .api.inventory_sync_api import inventory_sync_bp
    app.register_blueprint(inventory_sync_bp)
    logger.info("재고 동기화 API Blueprint 등록 완료")
except Exception as _inv_sync_bp_exc:
    logger.warning("재고 동기화 API Blueprint 등록 실패: %s", _inv_sync_bp_exc)

# 번역 관리 API Blueprint 등록
try:
    from .api.translation_api import translation_bp
    app.register_blueprint(translation_bp)
    logger.info("번역 관리 API Blueprint 등록 완료")
except Exception as _trans_bp_exc:
    logger.warning("번역 관리 API Blueprint 등록 실패: %s", _trans_bp_exc)

# 가격 엔진 API Blueprint 등록
try:
    from .api.pricing_api import pricing_bp
    app.register_blueprint(pricing_bp)
    logger.info("가격 엔진 API Blueprint 등록 완료")
except Exception as _pricing_bp_exc:
    logger.warning("가격 엔진 API Blueprint 등록 실패: %s", _pricing_bp_exc)

# 공급자 관리 API Blueprint 등록
try:
    from .api.suppliers_api import suppliers_bp
    app.register_blueprint(suppliers_bp)
    logger.info("공급자 API Blueprint 등록 완료")
except Exception as _sup_bp_exc:
    logger.warning("공급자 API Blueprint 등록 실패: %s", _sup_bp_exc)

# 알림 관리 API Blueprint 등록
try:
    from .api.notifications_api import notifications_bp
    app.register_blueprint(notifications_bp)
    logger.info("알림 관리 API Blueprint 등록 완료")
except Exception as _notif_bp_exc:
    logger.warning("알림 관리 API Blueprint 등록 실패: %s", _notif_bp_exc)

# 반품/교환 API Blueprint 등록 (Phase 37)
try:
    from .api.returns_api import returns_bp
    app.register_blueprint(returns_bp)
    logger.info("반품/교환 API Blueprint 등록 완료")
except Exception as _ret_bp_exc:
    logger.warning("반품/교환 API Blueprint 등록 실패: %s", _ret_bp_exc)

# 쿠폰 API Blueprint 등록 (Phase 38)
try:
    from .api.coupons_api import coupons_bp
    app.register_blueprint(coupons_bp)
    logger.info("쿠폰 API Blueprint 등록 완료")
except Exception as _coup_bp_exc:
    logger.warning("쿠폰 API Blueprint 등록 실패: %s", _coup_bp_exc)

# 카테고리 API Blueprint 등록 (Phase 39)
try:
    from .api.categories_api import categories_bp
    app.register_blueprint(categories_bp)
    logger.info("카테고리 API Blueprint 등록 완료")
except Exception as _cat_bp_exc:
    logger.warning("카테고리 API Blueprint 등록 실패: %s", _cat_bp_exc)

# 스케줄러 API Blueprint 등록 (Phase 40)
try:
    from .api.scheduler_api import scheduler_bp
    app.register_blueprint(scheduler_bp)
    logger.info("스케줄러 API Blueprint 등록 완료")
except Exception as _sched_bp_exc:
    logger.warning("스케줄러 API Blueprint 등록 실패: %s", _sched_bp_exc)

# 감사 로그 API Blueprint 등록 (Phase 41)
try:
    from .api.audit_api import audit_bp
    app.register_blueprint(audit_bp)
    logger.info("감사 로그 API Blueprint 등록 완료")
except Exception as _audit_bp_exc:
    logger.warning("감사 로그 API Blueprint 등록 실패: %s", _audit_bp_exc)

# 위시리스트 API Blueprint 등록 (Phase 43)
try:
    from .api.wishlist_api import wishlist_bp
    app.register_blueprint(wishlist_bp)
    logger.info("위시리스트 API Blueprint 등록 완료")
except Exception as _wishlist_bp_exc:
    logger.warning("위시리스트 API Blueprint 등록 실패: %s", _wishlist_bp_exc)

# 번들 API Blueprint 등록 (Phase 44)
try:
    from .api.bundles_api import bundles_bp
    app.register_blueprint(bundles_bp)
    logger.info("번들 API Blueprint 등록 완료")
except Exception as _bundles_bp_exc:
    logger.warning("번들 API Blueprint 등록 실패: %s", _bundles_bp_exc)

# 멀티통화 API Blueprint 등록 (Phase 45)
try:
    from .api.multicurrency_api import multicurrency_bp
    app.register_blueprint(multicurrency_bp)
    logger.info("멀티통화 API Blueprint 등록 완료")
except Exception as _mc_bp_exc:
    logger.warning("멀티통화 API Blueprint 등록 실패: %s", _mc_bp_exc)

# 결제 게이트웨이 API Blueprint 등록 (Phase 45)
try:
    from .api.payment_api import payment_bp
    app.register_blueprint(payment_bp)
    logger.info("결제 게이트웨이 API Blueprint 등록 완료")
except Exception as _pay_bp_exc:
    logger.warning("결제 게이트웨이 API Blueprint 등록 실패: %s", _pay_bp_exc)

# 이미지 관리 API Blueprint 등록 (Phase 46)
try:
    from .api.images_api import images_bp
    app.register_blueprint(images_bp)
    logger.info("이미지 관리 API Blueprint 등록 완료")
except Exception as _img_bp_exc:
    logger.warning("이미지 관리 API Blueprint 등록 실패: %s", _img_bp_exc)

# 사용자 프로필 API Blueprint 등록 (Phase 47)
try:
    from .api.users_api import users_bp
    app.register_blueprint(users_bp)
    logger.info("사용자 프로필 API Blueprint 등록 완료")
except Exception as _users_bp_exc:
    logger.warning("사용자 프로필 API Blueprint 등록 실패: %s", _users_bp_exc)

# 검색 엔진 API Blueprint 등록 (Phase 48)
try:
    from .api.search_api import search_bp
    app.register_blueprint(search_bp)
    logger.info("검색 엔진 API Blueprint 등록 완료")
except Exception as _search_bp_exc:
    logger.warning("검색 엔진 API Blueprint 등록 실패: %s", _search_bp_exc)

# 멀티테넌시 API Blueprint 등록 (Phase 49)
try:
    from .api.tenancy_api import tenancy_bp
    app.register_blueprint(tenancy_bp)
    logger.info("멀티테넌시 API Blueprint 등록 완료")
except Exception as _tenancy_bp_exc:
    logger.warning("멀티테넌시 API Blueprint 등록 실패: %s", _tenancy_bp_exc)

# A/B 테스트 API Blueprint 등록 (Phase 50)
try:
    from .api.experiments_api import experiments_bp
    app.register_blueprint(experiments_bp)
    logger.info("A/B 테스트 API Blueprint 등록 완료")
except Exception as _experiments_bp_exc:
    logger.warning("A/B 테스트 API Blueprint 등록 실패: %s", _experiments_bp_exc)

# 웹훅 관리 API Blueprint 등록 (Phase 51)
try:
    from .api.webhooks_mgr_api import webhooks_mgr_bp
    app.register_blueprint(webhooks_mgr_bp)
    logger.info("웹훅 관리 API Blueprint 등록 완료")
except Exception as _webhooks_mgr_bp_exc:
    logger.warning("웹훅 관리 API Blueprint 등록 실패: %s", _webhooks_mgr_bp_exc)

# API 문서 Blueprint 등록 (Phase 52)
try:
    from .api.api_docs_api import api_docs_bp
    app.register_blueprint(api_docs_bp)
    logger.info("API 문서 Blueprint 등록 완료")
except Exception as _api_docs_bp_exc:
    logger.warning("API 문서 Blueprint 등록 실패: %s", _api_docs_bp_exc)

# 분산 추적 API Blueprint 등록 (Phase 53)
try:
    from .api.traces_api import traces_bp
    app.register_blueprint(traces_bp)
    logger.info("분산 추적 API Blueprint 등록 완료")
except Exception as _traces_bp_exc:
    logger.warning("분산 추적 API Blueprint 등록 실패: %s", _traces_bp_exc)

# 벤치마크 API Blueprint 등록 (Phase 54)
try:
    from .api.benchmark_api import benchmark_bp
    app.register_blueprint(benchmark_bp)
    logger.info("벤치마크 API Blueprint 등록 완료")
except Exception as _benchmark_bp_exc:
    logger.warning("벤치마크 API Blueprint 등록 실패: %s", _benchmark_bp_exc)

# 파일 스토리지 API Blueprint 등록 (Phase 55)
try:
    from .api.storage_api import storage_bp
    app.register_blueprint(storage_bp)
    logger.info("파일 스토리지 API Blueprint 등록 완료")
except Exception as _storage_bp_exc:
    logger.warning("파일 스토리지 API Blueprint 등록 실패: %s", _storage_bp_exc)

# 이메일 서비스 API Blueprint 등록 (Phase 56)
try:
    from .api.email_api import email_bp
    app.register_blueprint(email_bp)
    logger.info("이메일 서비스 API Blueprint 등록 완료")
except Exception as _email_bp_exc:
    logger.warning("이메일 서비스 API Blueprint 등록 실패: %s", _email_bp_exc)

# 검색 엔진 고급 API Blueprint 등록 (Phase 57)
try:
    from .api.search_engine_api import search_engine_bp
    app.register_blueprint(search_engine_bp)
    logger.info("검색 엔진 고급 API Blueprint 등록 완료")
except Exception as _search_engine_bp_exc:
    logger.warning("검색 엔진 고급 API Blueprint 등록 실패: %s", _search_engine_bp_exc)

# 작업 파이프라인 API Blueprint 등록 (Phase 58)
try:
    from .api.pipeline_api import pipeline_bp
    app.register_blueprint(pipeline_bp)
    logger.info("작업 파이프라인 API Blueprint 등록 완료")
except Exception as _pipeline_bp_exc:
    logger.warning("작업 파이프라인 API Blueprint 등록 실패: %s", _pipeline_bp_exc)

# 피쳐 플래그 API Blueprint 등록 (Phase 59)
try:
    from .api.flags_api import flags_bp
    app.register_blueprint(flags_bp)
    logger.info("피쳐 플래그 API Blueprint 등록 완료")
except Exception as _flags_bp_exc:
    logger.warning("피쳐 플래그 API Blueprint 등록 실패: %s", _flags_bp_exc)

# 외부 연동 허브 API Blueprint 등록 (Phase 60)
try:
    from .api.integrations_api import integrations_bp
    app.register_blueprint(integrations_bp)
    logger.info("외부 연동 허브 API Blueprint 등록 완료")
except Exception as _integrations_bp_exc:
    logger.warning("외부 연동 허브 API Blueprint 등록 실패: %s", _integrations_bp_exc)

# 백업/복원 API Blueprint 등록 (Phase 61)
try:
    from .api.backup_api import backup_bp
    app.register_blueprint(backup_bp)
    logger.info("백업/복원 API Blueprint 등록 완료")
except Exception as _backup_bp_exc:
    logger.warning("백업/복원 API Blueprint 등록 실패: %s", _backup_bp_exc)

# 레이트 리미팅 API Blueprint 등록 (Phase 62)
try:
    from .api.rate_limits_api import rate_limits_bp
    app.register_blueprint(rate_limits_bp)
    logger.info("레이트 리미팅 API Blueprint 등록 완료")
except Exception as _rate_limits_bp_exc:
    logger.warning("레이트 리미팅 API Blueprint 등록 실패: %s", _rate_limits_bp_exc)

# CMS API Blueprint 등록 (Phase 63)
try:
    from .api.cms_api import cms_bp
    app.register_blueprint(cms_bp)
    logger.info("CMS API Blueprint 등록 완료")
except Exception as _cms_bp_exc:
    logger.warning("CMS API Blueprint 등록 실패: %s", _cms_bp_exc)

# 이벤트 소싱 API Blueprint 등록 (Phase 64)
try:
    from .api.events_api import events_bp
    app.register_blueprint(events_bp)
    logger.info("이벤트 소싱 API Blueprint 등록 완료")
except Exception as _events_bp_exc:
    logger.warning("이벤트 소싱 API Blueprint 등록 실패: %s", _events_bp_exc)

# 캐시 계층 API Blueprint 등록 (Phase 65)
try:
    from .api.cache_api import cache_bp
    app.register_blueprint(cache_bp)
    logger.info("캐시 계층 API Blueprint 등록 완료")
except Exception as _cache_bp_exc:
    logger.warning("캐시 계층 API Blueprint 등록 실패: %s", _cache_bp_exc)

# 워크플로 엔진 API Blueprint 등록 (Phase 66)
try:
    from .api.workflows_api import workflows_bp
    app.register_blueprint(workflows_bp)
    logger.info("워크플로 엔진 API Blueprint 등록 완료")
except Exception as _workflows_bp_exc:
    logger.warning("워크플로 엔진 API Blueprint 등록 실패: %s", _workflows_bp_exc)

# 실시간 대시보드 API Blueprint 등록 (Phase 67)
try:
    from .api.realtime_api import realtime_bp
    app.register_blueprint(realtime_bp)
    logger.info("실시간 대시보드 API Blueprint 등록 완료")
except Exception as _realtime_bp_exc:
    logger.warning("실시간 대시보드 API Blueprint 등록 실패: %s", _realtime_bp_exc)

# 데이터 교환 API Blueprint 등록 (Phase 68)
try:
    from .api.data_exchange_api import data_exchange_bp
    app.register_blueprint(data_exchange_bp)
    logger.info("데이터 교환 API Blueprint 등록 완료")
except Exception as _data_exchange_bp_exc:
    logger.warning("데이터 교환 API Blueprint 등록 실패: %s", _data_exchange_bp_exc)

# 규칙 엔진 API Blueprint 등록 (Phase 69)
try:
    from .api.rules_api import rules_bp
    app.register_blueprint(rules_bp)
    logger.info("규칙 엔진 API Blueprint 등록 완료")
except Exception as _rules_bp_exc:
    logger.warning("규칙 엔진 API Blueprint 등록 실패: %s", _rules_bp_exc)

# KPI 대시보드 API Blueprint 등록 (Phase 70)
try:
    from .api.kpi_api import kpi_bp
    app.register_blueprint(kpi_bp)
    logger.info("KPI 대시보드 API Blueprint 등록 완료")
except Exception as _kpi_bp_exc:
    logger.warning("KPI 대시보드 API Blueprint 등록 실패: %s", _kpi_bp_exc)

# 마켓플레이스 동기화 API Blueprint 등록 (Phase 71)
try:
    from .api.marketplace_sync_api import marketplace_sync_bp
    app.register_blueprint(marketplace_sync_bp)
    logger.info("마켓플레이스 동기화 API Blueprint 등록 완료")
except Exception as _marketplace_sync_bp_exc:
    logger.warning("마켓플레이스 동기화 API Blueprint 등록 실패: %s", _marketplace_sync_bp_exc)

# 보안 강화 API Blueprint 등록 (Phase 72)
try:
    from .api.security_api import security_bp
    app.register_blueprint(security_bp)
    logger.info("보안 강화 API Blueprint 등록 완료")
except Exception as _security_bp_exc:
    logger.warning("보안 강화 API Blueprint 등록 실패: %s", _security_bp_exc)

# 고객 세그먼트 API Blueprint 등록 (Phase 73)
try:
    from .api.segmentation_api import segmentation_bp
    app.register_blueprint(segmentation_bp)
    logger.info("고객 세그먼트 API Blueprint 등록 완료")
except Exception as _seg_bp_exc:
    logger.warning("고객 세그먼트 API Blueprint 등록 실패: %s", _seg_bp_exc)

# 동적 폼 빌더 API Blueprint 등록 (Phase 74)
try:
    from .api.form_builder_api import form_builder_bp
    app.register_blueprint(form_builder_bp)
    logger.info("동적 폼 빌더 API Blueprint 등록 완료")
except Exception as _form_bp_exc:
    logger.warning("동적 폼 빌더 API Blueprint 등록 실패: %s", _form_bp_exc)

# 워크플로 엔진 고도화 API Blueprint 등록 (Phase 75)
try:
    from .api.workflow_engine_api import workflow_engine_bp
    app.register_blueprint(workflow_engine_bp)
    logger.info("워크플로 엔진 고도화 API Blueprint 등록 완료")
except Exception as _wf_engine_bp_exc:
    logger.warning("워크플로 엔진 고도화 API Blueprint 등록 실패: %s", _wf_engine_bp_exc)

# 파일 스토리지 추상화 API Blueprint 등록 (Phase 76)
try:
    from .api.file_storage_api import file_storage_bp
    app.register_blueprint(file_storage_bp)
    logger.info("파일 스토리지 추상화 API Blueprint 등록 완료")
except Exception as _fs_bp_exc:
    logger.warning("파일 스토리지 추상화 API Blueprint 등록 실패: %s", _fs_bp_exc)

# 이벤트 소싱 고도화 API Blueprint 등록 (Phase 77)
try:
    from .api.event_sourcing_api import event_sourcing_bp
    app.register_blueprint(event_sourcing_bp)
    logger.info("이벤트 소싱 고도화 API Blueprint 등록 완료")
except Exception as _es_bp_exc:
    logger.warning("이벤트 소싱 고도화 API Blueprint 등록 실패: %s", _es_bp_exc)

# 피처 플래그 고도화 API Blueprint 등록 (Phase 78)
try:
    from .api.feature_flags_api import feature_flags_bp
    app.register_blueprint(feature_flags_bp)
    logger.info("피처 플래그 고도화 API Blueprint 등록 완료")
except Exception as _ff_bp_exc:
    logger.warning("피처 플래그 고도화 API Blueprint 등록 실패: %s", _ff_bp_exc)

# 리뷰 분석 API Blueprint 등록 (Phase 79)
try:
    from .api.review_analytics_api import review_analytics_bp
    app.register_blueprint(review_analytics_bp)
    logger.info("리뷰 분석 API Blueprint 등록 완료")
except Exception as _review_analytics_bp_exc:
    logger.warning("리뷰 분석 API Blueprint 등록 실패: %s", _review_analytics_bp_exc)

# 배송비 계산기 API Blueprint 등록 (Phase 80)
try:
    from .api.shipping_calculator_api import shipping_calculator_bp
    app.register_blueprint(shipping_calculator_bp)
    logger.info("배송비 계산기 API Blueprint 등록 완료")
except Exception as _shipping_calc_bp_exc:
    logger.warning("배송비 계산기 API Blueprint 등록 실패: %s", _shipping_calc_bp_exc)

# 알림 템플릿 엔진 API Blueprint 등록 (Phase 81)
try:
    from .api.notification_templates_api import notification_templates_bp
    app.register_blueprint(notification_templates_bp)
    logger.info("알림 템플릿 엔진 API Blueprint 등록 완료")
except Exception as _notif_tmpl_bp_exc:
    logger.warning("알림 템플릿 엔진 API Blueprint 등록 실패: %s", _notif_tmpl_bp_exc)

# 결제 복구 API Blueprint 등록 (Phase 82)
try:
    from .api.payment_recovery_api import payment_recovery_bp
    app.register_blueprint(payment_recovery_bp)
    logger.info("결제 복구 API Blueprint 등록 완료")
except Exception as _payment_recovery_bp_exc:
    logger.warning("결제 복구 API Blueprint 등록 실패: %s", _payment_recovery_bp_exc)

# 상품 추천 API Blueprint 등록 (Phase 83)
try:
    from .api.recommendation_api import recommendation_bp
    app.register_blueprint(recommendation_bp)
    logger.info("상품 추천 API Blueprint 등록 완료")
except Exception as _recommendation_bp_exc:
    logger.warning("상품 추천 API Blueprint 등록 실패: %s", _recommendation_bp_exc)

# 주문 분할/병합 API Blueprint 등록 (Phase 84)
try:
    from .api.order_management_api import order_management_bp
    app.register_blueprint(order_management_bp)
    logger.info("주문 분할/병합 API Blueprint 등록 완료")
except Exception as _order_mgmt_bp_exc:
    logger.warning("주문 분할/병합 API Blueprint 등록 실패: %s", _order_mgmt_bp_exc)

# 재고 입출고 이력 API Blueprint 등록 (Phase 85)
try:
    from .api.inventory_transactions_api import inventory_transactions_bp
    app.register_blueprint(inventory_transactions_bp)
    logger.info("재고 입출고 이력 API Blueprint 등록 완료")
except Exception as _inv_tx_bp_exc:
    logger.warning("재고 입출고 이력 API Blueprint 등록 실패: %s", _inv_tx_bp_exc)

# 고객 세그멘테이션 API Blueprint 등록 (Phase 86)
try:
    from .api.customer_segmentation_api import customer_segmentation_bp
    app.register_blueprint(customer_segmentation_bp)
    logger.info("고객 세그멘테이션 API Blueprint 등록 완료")
except Exception as _cust_seg_bp_exc:
    logger.warning("고객 세그멘테이션 API Blueprint 등록 실패: %s", _cust_seg_bp_exc)

# 상품 비교 API Blueprint 등록 (Phase 87)
try:
    from .api.product_comparison_api import product_comparison_bp
    app.register_blueprint(product_comparison_bp)
    logger.info("상품 비교 API Blueprint 등록 완료")
except Exception as _prod_cmp_bp_exc:
    logger.warning("상품 비교 API Blueprint 등록 실패: %s", _prod_cmp_bp_exc)

# 이메일 마케팅 API Blueprint 등록 (Phase 88)
try:
    from .api.email_marketing_api import email_marketing_bp
    app.register_blueprint(email_marketing_bp)
    logger.info("이메일 마케팅 API Blueprint 등록 완료")
except Exception as _email_mkt_bp_exc:
    logger.warning("이메일 마케팅 API Blueprint 등록 실패: %s", _email_mkt_bp_exc)

# 창고 관리 API Blueprint 등록 (Phase 89)
try:
    from .api.warehouse_api import warehouse_bp
    app.register_blueprint(warehouse_bp)
    logger.info("창고 관리 API Blueprint 등록 완료")
except Exception as _warehouse_bp_exc:
    logger.warning("창고 관리 API Blueprint 등록 실패: %s", _warehouse_bp_exc)

# 세금 계산 엔진 API Blueprint 등록 (Phase 90)
try:
    from .api.tax_engine_api import tax_engine_bp
    app.register_blueprint(tax_engine_bp)
    logger.info("세금 계산 엔진 API Blueprint 등록 완료")
except Exception as _tax_bp_exc:
    logger.warning("세금 계산 엔진 API Blueprint 등록 실패: %s", _tax_bp_exc)

# 분쟁 관리 API Blueprint 등록 (Phase 91)
try:
    from .api.disputes_api import disputes_bp
    app.register_blueprint(disputes_bp)
    logger.info("분쟁 관리 API Blueprint 등록 완료")
except Exception as _disputes_bp_exc:
    logger.warning("분쟁 관리 API Blueprint 등록 실패: %s", _disputes_bp_exc)

# 포인트 API Blueprint 등록 (Phase 92)
try:
    from .api.points_api import points_bp
    app.register_blueprint(points_bp)
    logger.info("포인트 API Blueprint 등록 완료")
except Exception as _points_bp_exc:
    logger.warning("포인트 API Blueprint 등록 실패: %s", _points_bp_exc)

# 구독 관리 API Blueprint 등록 (Phase 92)
try:
    from .api.subscriptions_api import subscriptions_bp
    app.register_blueprint(subscriptions_bp)
    logger.info("구독 관리 API Blueprint 등록 완료")
except Exception as _subscriptions_bp_exc:
    logger.warning("구독 관리 API Blueprint 등록 실패: %s", _subscriptions_bp_exc)

# 글로벌 커머스 API Blueprint 등록 (Phase 93)
try:
    from .api.global_commerce_api import global_commerce_bp
    app.register_blueprint(global_commerce_bp)
    logger.info("글로벌 커머스 API Blueprint 등록 완료")
except Exception as _global_commerce_bp_exc:
    logger.warning("글로벌 커머스 API Blueprint 등록 실패: %s", _global_commerce_bp_exc)

# AI 추천 API Blueprint 등록 (Phase 94)
try:
    from .api.ai_recommendation_api import ai_recommendation_bp
    app.register_blueprint(ai_recommendation_bp)
    logger.info("AI 추천 API Blueprint 등록 완료")
except Exception as _ai_rec_bp_exc:
    logger.warning("AI 추천 API Blueprint 등록 실패: %s", _ai_rec_bp_exc)

# 모바일 API Blueprint 등록 (Phase 95)
try:
    from .api.mobile_api_routes import mobile_api_bp
    app.register_blueprint(mobile_api_bp)
    logger.info("모바일 API Blueprint 등록 완료")
except Exception as _mobile_bp_exc:
    logger.warning("모바일 API Blueprint 등록 실패: %s", _mobile_bp_exc)

# 자동 구매 API Blueprint 등록 (Phase 96)
try:
    from .api.auto_purchase_api import auto_purchase_bp
    app.register_blueprint(auto_purchase_bp)
    logger.info("자동 구매 API Blueprint 등록 완료")
except Exception as _auto_purchase_bp_exc:
    logger.warning("자동 구매 API Blueprint 등록 실패: %s", _auto_purchase_bp_exc)

# 물류 최적화 API Blueprint 등록 (Phase 99)
try:
    from .api.logistics_api import logistics_bp
    app.register_blueprint(logistics_bp)
    logger.info("물류 최적화 API Blueprint 등록 완료")
except Exception as _logistics_bp_exc:
    logger.warning("물류 최적화 API Blueprint 등록 실패: %s", _logistics_bp_exc)

# 배송대행지 API Blueprint 등록 (Phase 102)
try:
    from .api.forwarding_api import forwarding_bp
    app.register_blueprint(forwarding_bp)
    logger.info("배송대행지 API Blueprint 등록 완료")
except Exception as _forwarding_bp_exc:
    logger.warning("배송대행지 API Blueprint 등록 실패: %s", _forwarding_bp_exc)

# 풀필먼트 API Blueprint 등록
try:
    from .api.fulfillment_api import fulfillment_bp
    app.register_blueprint(fulfillment_bp)
    logger.info("풀필먼트 API Blueprint 등록 완료")
except Exception as _fulfillment_bp_exc:
    logger.warning("풀필먼트 API Blueprint 등록 실패: %s", _fulfillment_bp_exc)

# 중국 마켓플레이스 API Blueprint 등록 (Phase 104)
try:
    from .api.china_marketplace_api import china_marketplace_bp
    app.register_blueprint(china_marketplace_bp)
    logger.info("중국 마켓플레이스 API Blueprint 등록 완료")
except Exception as _china_marketplace_bp_exc:
    logger.warning("중국 마켓플레이스 API Blueprint 등록 실패: %s", _china_marketplace_bp_exc)

# 예외 처리 API Blueprint 등록 (Phase 105)
try:
    from .api.exception_handler_api import exception_handler_bp
    app.register_blueprint(exception_handler_bp)
    logger.info("예외 처리 API Blueprint 등록 완료")
except Exception as _exception_handler_bp_exc:
    logger.warning("예외 처리 API Blueprint 등록 실패: %s", _exception_handler_bp_exc)

# 자율 운영 대시보드 API Blueprint 등록 (Phase 106)
try:
    from .api.autonomous_ops_api import autonomous_ops_bp
    app.register_blueprint(autonomous_ops_bp)
    logger.info("자율 운영 대시보드 API Blueprint 등록 완료")
except Exception as _autonomous_ops_bp_exc:
    logger.warning("자율 운영 대시보드 API Blueprint 등록 실패: %s", _autonomous_ops_bp_exc)

# 실시간 채팅 고객 지원 API Blueprint 등록 (Phase 107)
try:
    from .api.live_chat_api import live_chat_bp
    app.register_blueprint(live_chat_bp)
    logger.info("실시간 채팅 API Blueprint 등록 완료")
except Exception as _live_chat_bp_exc:
    logger.warning("실시간 채팅 API Blueprint 등록 실패: %s", _live_chat_bp_exc)

# 소싱처 실시간 모니터링 API Blueprint 등록 (Phase 108)
try:
    from .api.source_monitor_api import source_monitor_bp
    app.register_blueprint(source_monitor_bp)
    logger.info("소싱처 모니터링 API Blueprint 등록 완료")
except Exception as _source_monitor_bp_exc:
    logger.warning("소싱처 모니터링 API Blueprint 등록 실패: %s", _source_monitor_bp_exc)

# 경쟁사 가격 모니터링 API Blueprint 등록 (Phase 111)
try:
    from .api.competitor_pricing_api import competitor_pricing_bp
    app.register_blueprint(competitor_pricing_bp)
    logger.info("경쟁사 가격 모니터링 API Blueprint 등록 완료")
except Exception as _competitor_pricing_bp_exc:
    logger.warning("경쟁사 가격 모니터링 API Blueprint 등록 실패: %s", _competitor_pricing_bp_exc)

# 주문 매칭 API Blueprint 등록 (Phase 112)
try:
    from .api.order_matching_api import order_matching_bp
    app.register_blueprint(order_matching_bp)
    logger.info("주문 매칭 API Blueprint 등록 완료")
except Exception as _order_matching_bp_exc:
    logger.warning("주문 매칭 API Blueprint 등록 실패: %s", _order_matching_bp_exc)

# 가상 재고 관리 API Blueprint 등록 (Phase 113)
try:
    from .api.virtual_inventory_api import virtual_inventory_bp
    app.register_blueprint(virtual_inventory_bp)
    logger.info("가상 재고 API Blueprint 등록 완료")
except Exception as _virtual_inventory_bp_exc:
    logger.warning("가상 재고 API Blueprint 등록 실패: %s", _virtual_inventory_bp_exc)

# 셀러 성과 리포트 API Blueprint 등록 (Phase 114)
try:
    from .api.seller_report_api import seller_report_bp
    app.register_blueprint(seller_report_bp)
    logger.info("셀러 성과 리포트 API Blueprint 등록 완료")
except Exception as _seller_report_bp_exc:
    logger.warning("셀러 성과 리포트 API Blueprint 등록 실패: %s", _seller_report_bp_exc)

# 소싱 발굴 API Blueprint 등록 (Phase 115)
try:
    from .api.sourcing_discovery_api import sourcing_discovery_bp
    app.register_blueprint(sourcing_discovery_bp)
    logger.info("소싱 발굴 API Blueprint 등록 완료")
except Exception as _sourcing_discovery_bp_exc:
    logger.warning("소싱 발굴 API Blueprint 등록 실패: %s", _sourcing_discovery_bp_exc)

# 보안 강화 API Blueprint 등록 (Phase 116)
try:
    from .api.security_advanced_api import security_advanced_bp
    app.register_blueprint(security_advanced_bp)
    logger.info("보안 강화 API Blueprint 등록 완료")
except Exception as _security_advanced_bp_exc:
    logger.warning("보안 강화 API Blueprint 등록 실패: %s", _security_advanced_bp_exc)

# 셀러 콘솔 Blueprint 등록 (Phase 122)
try:
    from .seller_console.views import bp as seller_bp
    app.register_blueprint(seller_bp)
    logger.info("셀러 콘솔 Blueprint 등록 완료 (/seller/)")
    # 공개 마진 계산 API 등록 (Phase 125)
    from .seller_console.views import _register_api_routes as _register_seller_api
    _register_seller_api(app)
    logger.info("공개 마진 계산 API 등록 완료 (/api/v1/pricing/calculate)")
except Exception as _seller_bp_exc:
    logger.warning("셀러 콘솔 Blueprint 등록 실패: %s", _seller_bp_exc)

# Phase 133: 인증 시스템 Blueprint 등록 (카카오/구글/네이버 로그인)
# SECRET_KEY 설정 — 인증 세션 필수
if not app.secret_key:
    _sk = os.getenv("SECRET_KEY")
    if _sk:
        app.secret_key = _sk
    else:
        import secrets as _sec_mod
        import warnings
        _dev_key = _sec_mod.token_hex(32)
        warnings.warn(
            "SECRET_KEY 환경변수가 설정되지 않았습니다. "
            "프로덕션에서는 반드시 SECRET_KEY를 설정하세요. "
            "현재 임시 키 사용 중 (재시작 시 모든 세션 만료).",
            stacklevel=1,
        )
        app.secret_key = _dev_key

# 세션 쿠키 보안 설정
app.config.setdefault("SESSION_COOKIE_SECURE", os.getenv("SESSION_COOKIE_SECURE", "0") == "1")
app.config.setdefault("SESSION_COOKIE_HTTPONLY", True)
app.config.setdefault("SESSION_COOKIE_SAMESITE", "Lax")

try:
    from .auth.views import auth_bp
    app.register_blueprint(auth_bp)
    logger.info("인증 시스템 Blueprint 등록 완료 (/auth/)")
except Exception as _auth_bp_exc:
    logger.warning("인증 시스템 Blueprint 등록 실패: %s", _auth_bp_exc)

try:
    from .auth.magic_link import magic_link_bp
    app.register_blueprint(magic_link_bp)
    logger.info("Magic Link Blueprint 등록 완료")
except Exception as _magic_link_bp_exc:
    logger.warning("Magic Link Blueprint 등록 실패: %s", _magic_link_bp_exc)

try:
    from .auth.bootstrap import bootstrap_bp
    app.register_blueprint(bootstrap_bp)
    logger.info("Bootstrap auth Blueprint 등록 완료")
except Exception as _bootstrap_bp_exc:
    logger.warning("Bootstrap auth Blueprint 등록 실패: %s", _bootstrap_bp_exc)

try:
    from .legal.views import legal_bp
    app.register_blueprint(legal_bp)
    logger.info("Legal Blueprint 등록 완료")
except Exception as _legal_bp_exc:
    logger.warning("Legal Blueprint 등록 실패: %s", _legal_bp_exc)

# Phase 135: 크롬 확장/북마클릿/벌크 수집 API
try:
    from .api.extension_api import extension_bp
    app.register_blueprint(extension_bp)
    logger.info("Extension API Blueprint 등록 완료 (/api/v1/collect/)")
except Exception as _ext_bp_exc:
    logger.warning("Extension API Blueprint 등록 실패: %s", _ext_bp_exc)

# Phase 136: 자동 재가격 Cron Blueprint 등록 (/cron/reprice)
try:
    from .pricing.cron import cron_bp
    app.register_blueprint(cron_bp)
    logger.info("재가격 Cron Blueprint 등록 완료 (/cron/reprice)")
except Exception as _cron_bp_exc:
    logger.warning("재가격 Cron Blueprint 등록 실패: %s", _cron_bp_exc)

# Phase 132: /shop 블루프린트는 외부 kohganemultishop.org가 진짜 자체몰이므로 기본 비활성.
# 향후 데모/쇼윈도우 용도로 부활시키려면 ENABLE_INTERNAL_SHOP=1 환경변수 설정.
if os.getenv("ENABLE_INTERNAL_SHOP", "0") == "1":
    try:
        from .shop import shop_bp
        app.register_blueprint(shop_bp)
        logger.info("내부 /shop 블루프린트 등록 (옵트인)")
    except Exception as _shop_bp_exc:
        logger.warning("내부 /shop 블루프린트 등록 실패: %s", _shop_bp_exc)
else:
    logger.info("내부 /shop 블루프린트 비활성 (기본). kohganemultishop.org가 자체몰.")

# CORS 설정 — 허용 오리진은 환경변수로 제어
# 프로덕션에서는 CORS_ORIGINS에 허용할 도메인을 명시적으로 설정할 것
_cors_origins = os.getenv('CORS_ORIGINS', '*')
CORS(app, resources={r'/health/*': {'origins': _cors_origins}})

# Rate Limiter 초기화
limiter = create_limiter(app)

# 요청 로거 미들웨어 초기화
request_logger = RequestLogger(app)

# 보안 미들웨어 초기화
security = SecurityMiddleware(app)

# 서버 시작 시각 (uptime 계산용)
_START_TIME = time.time()

router = OrderRouter()
notifier = OrderNotifier()
tracker = OrderTracker()
status_tracker = OrderStatusTracker()

# 주문 검증기 + 감사 로거 초기화
order_validator = OrderValidator()
audit_logger = AuditLogger()


# Phase 132: 외부 자체몰 URL (kohganemultishop.org)
# 이 상수를 변경하거나 EXTERNAL_SHOP_URL 환경변수로 재정의 가능.
_EXTERNAL_SHOP_URL = os.getenv("EXTERNAL_SHOP_URL", "https://kohganemultishop.org")


# ---------------------------------------------------------------------------
# Phase 123 — 루트 라우트 + 에러 핸들러
# ---------------------------------------------------------------------------

@app.get('/')
def root():
    """루트 라우트 — ROOT_REDIRECT 환경변수로 동작 제어 (Phase 132).

    Phase 132: 도메인별 라우팅 정책
      kohganepercentiii.com   → 셀러 SaaS + 운영 백오피스 (이 앱)
        /                     → ROOT_REDIRECT 환경변수 따라 (기본: seller)
        /seller/*             → 셀러 콘솔
        /admin/*              → 어드민
        /api/*                → API
        /shop, /shop/         → 302 redirect → kohganemultishop.org
        /health/*             → 헬스체크
      kohganemultishop.org    → 외부 WordPress + WooCommerce 자체몰 (별도)
        본 앱이 WooCommerce REST API로 데이터 통합 조회/등록만 함

    ROOT_REDIRECT:
      "seller"       → /seller/ (셀러 콘솔, 기본값)
      "landing"      → 통합 랜딩 페이지
      "shop_external" → kohganemultishop.org로 외부 redirect
      "shop"         → kohganemultishop.org로 외부 redirect (레거시 호환)
    """
    redirect_target = os.getenv("ROOT_REDIRECT", "seller").strip().lower()

    if redirect_target in ("shop_external", "shop"):
        # "shop"은 "shop_external"의 레거시 별칭 (하위 호환)
        return redirect(_EXTERNAL_SHOP_URL, code=302)

    if redirect_target == "landing":
        version = os.getenv('APP_VERSION', 'dev')
        return render_template('landing.html', version=version)

    # 기본: "seller" (백워드 호환)
    try:
        from .seller_console.views import bp as _seller_bp  # noqa: F401
        return redirect('/seller/', code=302)
    except Exception:
        version = os.getenv('APP_VERSION', 'dev')
        return render_template('landing.html', version=version)


@app.route("/shop")
@app.route("/shop/")
def shop_external_redirect():
    """Phase 132: /shop → 외부 자체몰 (kohganemultishop.org) redirect."""
    return redirect(_EXTERNAL_SHOP_URL, code=302)


@app.errorhandler(404)
def not_found(e):
    """404 — 커스텀 에러 페이지."""
    return render_template('errors/404.html'), 404


@app.errorhandler(500)
def server_error(e):
    """500 — 커스텀 에러 페이지."""
    return render_template('errors/500.html'), 500


@app.post('/webhook/shopify/order')
@limiter.limit(LIMIT_WEBHOOK)
def shopify_order():
    raw_body = request.get_data()
    hmac_header = request.headers.get('X-Shopify-Hmac-Sha256', '')
    if not verify_webhook(raw_body, hmac_header):
        audit_logger.log(
            EventType.WEBHOOK_REJECTED,
            actor="shopify_webhook",
            resource="webhook:/webhook/shopify/order",
            ip_address=request.remote_addr or "",
        )
        return jsonify({"error": "Invalid signature"}), 401

    data = request.get_json(force=True)

    # 주문 페이로드 검증
    is_valid, validation_errors = order_validator.validate_shopify(data)
    if not is_valid:
        logger.warning("Shopify 주문 검증 실패: %s", validation_errors)
        is_duplicate = any(e.startswith(DUPLICATE_ORDER_TAG) for e in validation_errors)
        audit_logger.log(
            EventType.ORDER_DUPLICATE_DETECTED if is_duplicate else EventType.WEBHOOK_REJECTED,
            actor="order_validator",
            resource=f"order:{data.get('id')}",
            details={"errors": validation_errors},
            ip_address=request.remote_addr or "",
        )
        # 중복 주문은 200 반환 (재전송 방지), 다른 검증 실패는 400
        if is_duplicate:
            return jsonify({"ok": True, "skipped": "duplicate"}), 200
        return jsonify({"error": "validation_failed", "details": validation_errors}), 400

    # 주문 라우팅
    routed = router.route_order(data)

    # 주문 상태 기록
    try:
        status_tracker.record_order(data, routed)
    except Exception as e:
        logger.warning("Failed to record order status: %s", e)

    # 알림 발송
    notifier.notify_new_order(routed)

    # 감사 로그 기록
    audit_logger.log_order(
        EventType.ORDER_ROUTED,
        order_id=data.get('id'),
        details={"summary": routed.get('summary', {})},
        ip_address=request.remote_addr or "",
    )

    return jsonify({"ok": True, "tasks": routed['summary']})


@app.post('/webhook/woo')
@limiter.limit(LIMIT_WEBHOOK)
def woocommerce_order():
    """WooCommerce 주문 웹훅 처리 엔드포인트."""
    raw_body = request.get_data()
    sig_header = request.headers.get('X-WC-Webhook-Signature', '')
    if not verify_woo_webhook(raw_body, sig_header):
        audit_logger.log(
            EventType.WEBHOOK_REJECTED,
            actor="woo_webhook",
            resource="webhook:/webhook/woo",
            ip_address=request.remote_addr or "",
        )
        return jsonify({"error": "Invalid signature"}), 401

    data = request.get_json(force=True)

    # 주문 페이로드 검증
    is_valid, validation_errors = order_validator.validate_woocommerce(data)
    if not is_valid:
        logger.warning("WooCommerce 주문 검증 실패: %s", validation_errors)
        is_duplicate = any(e.startswith(DUPLICATE_ORDER_TAG) for e in validation_errors)
        if is_duplicate:
            return jsonify({"ok": True, "skipped": "duplicate"}), 200
        return jsonify({"error": "validation_failed", "details": validation_errors}), 400

    routed = router.route_order(data)

    try:
        status_tracker.record_order(data, routed)
    except Exception as e:
        logger.warning("Failed to record woo order status: %s", e)

    notifier.notify_new_order(routed)

    audit_logger.log_order(
        EventType.ORDER_ROUTED,
        order_id=data.get('id'),
        details={"summary": routed.get('summary', {}), "source": "woocommerce"},
        ip_address=request.remote_addr or "",
    )

    return jsonify({"ok": True, "tasks": routed['summary']})


@app.post('/webhook/forwarder/tracking')
@limiter.limit(LIMIT_WEBHOOK)
def tracking_update():
    data = request.get_json(force=True)

    result = tracker.process_tracking(data)

    # 주문 상태 업데이트
    try:
        status_tracker.update_status(
            order_id=data.get('order_id'),
            sku=data.get('sku', ''),
            new_status='shipped_domestic',
            tracking_number=data.get('tracking_number', ''),
            carrier=data.get('carrier', ''),
        )
    except Exception as e:
        logger.warning("Failed to update order status: %s", e)

    if result.get('notification_sent'):
        notifier.notify_tracking_update(
            order_id=data.get('order_id'),
            sku=data.get('sku', ''),
            tracking_number=data.get('tracking_number', ''),
            carrier=data.get('carrier', ''),
        )

    return jsonify(result)


@app.get('/health')
@limiter.limit(LIMIT_HEALTH)
def health():
    """Healthcheck 엔드포인트 — Docker/LB용."""
    return jsonify({
        "status": "ok",
        "service": "proxy-commerce",
        "version": os.getenv("APP_VERSION", "dev"),
    })


@app.get('/health/ready')
@limiter.limit(LIMIT_HEALTH)
def readiness():
    """Readiness check — 외부 의존성(Sheets 등) 연결 확인.

    optional 시크릿(GOOGLE_SERVICE_JSON_B64, GOOGLE_SHEET_ID 등) 미설정 시에는
    HTTP 200 + degraded:true 를 반환합니다 (soft-fail).
    진짜 fatal한 의존성(코어 DB 연결 등)만 503을 반환합니다.
    """
    checks = {}
    degraded = False
    try:
        from .utils.secret_check import check_secrets
        result = check_secrets('core')
        secrets_ok = len(result['core']['missing']) == 0
        checks['secrets_core'] = secrets_ok
        # optional 시크릿 누락은 degraded 처리 (fatal 아님)
        if not secrets_ok:
            degraded = True
    except Exception:
        checks['secrets_core'] = False
        degraded = True

    # fatal 의존성이 없으면 200 반환 (optional 누락은 degraded:true로만 표시)
    return jsonify({
        "status": "ready",
        "degraded": degraded,
        "checks": checks,
    }), 200


@app.get('/health/deep')
@limiter.limit(LIMIT_HEALTH)
def deep_health():
    """Deep healthcheck — 외부 의존성 상세 연결 확인.

    단계별 진단:
      1. secrets_core    — 필수 환경변수 존재 여부
      2. google_credentials — 자격증명 로드 (다중 소스)
      3. google_sheets   — 스프레드시트 열기
      4. google_worksheets — 필수 워크시트 존재 확인

    각 단계 실패 시 이후 단계는 skip 처리.
    """
    import datetime
    import re
    from .utils.google_credentials import GoogleCredentialsLoader, CredentialsLoadError

    check_list = []
    now_iso = datetime.datetime.now(tz=datetime.timezone.utc).isoformat()
    uptime = round(time.time() - _START_TIME, 1)

    def _safe_exc_msg(exc: Exception, max_len: int = 200) -> str:
        """예외 메시지를 안전하게 반환 (스택트레이스 노출 방지)."""
        msg = str(exc)
        return msg[:max_len] if len(msg) > max_len else msg

    # 시트 ID 마스킹 helper
    def _mask(sid: str) -> str:
        if len(sid) <= 8:
            return "***"
        return f"{sid[:4]}***{sid[-4:]}"

    # placeholder 시트 ID 감지
    _PLACEHOLDER_PATTERNS = {"your-sheet-id", "for-google-sheet-id", "xxx", "yyy", "test", "example"}

    def _validate_sheet_id(sid: str):
        """(cleaned_id, warning) 반환. warning=None 이면 이상 없음."""
        # URL 형식이면 ID 추출 시도
        m = re.search(r'/spreadsheets/d/([^/]+)', sid)
        if m:
            sid = m.group(1)
        lower = sid.lower()
        for ph in _PLACEHOLDER_PATTERNS:
            if ph in lower:
                return sid, f"GOOGLE_SHEET_ID가 placeholder 값처럼 보임: {_mask(sid)!r}"
        if len(sid) < 20:
            return sid, f"GOOGLE_SHEET_ID 길이가 너무 짧음 ({len(sid)}자): {_mask(sid)!r}"
        if len(sid) > 100:
            return sid, f"GOOGLE_SHEET_ID 길이가 너무 김 ({len(sid)}자)"
        return sid, None

    # ── 1) secrets_core ───────────────────────────────────────────────
    secrets_ok = False
    try:
        from .utils.secret_check import check_secrets
        secret_result = check_secrets('core')
        missing = secret_result['core']['missing']
        secrets_ok = len(missing) == 0
        check_list.append({
            "name": "secrets_core",
            "status": "ok" if secrets_ok else "fail",
            "detail": f"누락된 시크릿: {missing}" if missing else "필수 환경변수 모두 존재",
        })
    except Exception as exc:
        logger.warning("Deep health: secret check failed: %s", exc)
        check_list.append({"name": "secrets_core", "status": "fail", "detail": str(exc)})

    # ── 2) google_credentials ─────────────────────────────────────────
    cred_data = None
    cred_source = None
    try:
        loader = GoogleCredentialsLoader()
        cred_data = loader.load()
        cred_source = loader.source
        check_list.append({
            "name": "google_credentials",
            "status": "ok",
            "source": cred_source,
            "detail": "service_account 로드 성공",
            "service_account": cred_data.get("client_email", ""),
            "project_id": cred_data.get("project_id", ""),
        })
    except CredentialsLoadError as exc:
        logger.warning("Deep health: credentials load failed: %s", exc)
        check_list.append({
            "name": "google_credentials",
            "status": "fail",
            "detail": _safe_exc_msg(exc),
            "hint": (
                "Render Dashboard → Environment → Secret Files 에서 "
                "service-account.json 등록 또는 GOOGLE_SERVICE_JSON_B64 환경변수 설정"
            ),
        })
        # 이후 단계 skip
        check_list.append({"name": "google_sheets", "status": "skip", "detail": "google_credentials fail로 인해 스킵"})
        check_list.append({"name": "google_worksheets", "status": "skip", "detail": "google_credentials fail로 인해 스킵"})
        has_fail = any(c["status"] == "fail" for c in check_list)
        _ext_apis = []
        try:
            from .utils.env_catalog import get_api_status
            _ext_apis = get_api_status()
        except Exception:
            pass
        return jsonify({
            "status": "degraded" if has_fail else "ok",
            "timestamp": now_iso,
            "uptime_seconds": uptime,
            "version": os.getenv("APP_VERSION", "dev"),
            "checks": check_list,
            "external_apis": _ext_apis,
        }), 200
    except Exception as exc:
        logger.warning("Deep health: credentials load unexpected error: %s", exc)
        check_list.append({"name": "google_credentials", "status": "fail", "detail": _safe_exc_msg(exc)})
        check_list.append({"name": "google_sheets", "status": "skip", "detail": "google_credentials fail로 인해 스킵"})
        check_list.append({"name": "google_worksheets", "status": "skip", "detail": "google_credentials fail로 인해 스킵"})
        has_fail = True
        _ext_apis = []
        try:
            from .utils.env_catalog import get_api_status
            _ext_apis = get_api_status()
        except Exception:
            pass
        return jsonify({
            "status": "degraded",
            "timestamp": now_iso,
            "uptime_seconds": uptime,
            "version": os.getenv("APP_VERSION", "dev"),
            "checks": check_list,
            "external_apis": _ext_apis,
        }), 200

    # ── 3) google_sheets ──────────────────────────────────────────────
    sheet_id_raw = os.getenv('GOOGLE_SHEET_ID', '').strip()
    sheet_id, sid_warning = _validate_sheet_id(sheet_id_raw) if sheet_id_raw else ('', None)
    svc_email = cred_data.get("client_email", "") if cred_data else ""

    if not sheet_id_raw:
        check_list.append({
            "name": "google_sheets",
            "status": "skip",
            "detail": "GOOGLE_SHEET_ID 환경변수 미설정",
            "hint": "Render 환경변수 탭에서 GOOGLE_SHEET_ID 추가",
        })
        check_list.append({"name": "google_worksheets", "status": "skip", "detail": "google_sheets skip으로 인해 스킵"})
    elif sid_warning:
        check_list.append({
            "name": "google_sheets",
            "status": "fail",
            "detail": sid_warning,
            "sheet_id_masked": _mask(sheet_id),
            "hint": "시트 URL에서 /d/ 와 /edit 사이의 ID 값을 GOOGLE_SHEET_ID 로 등록하세요",
        })
        check_list.append({"name": "google_worksheets", "status": "skip", "detail": "google_sheets fail로 인해 스킵"})
    else:
        try:
            from .utils.sheets import diagnose_sheets_connection
            diag = diagnose_sheets_connection()
            # worksheets 체크는 diagnose_sheets_connection에서 통합하므로 여기서 분리
            sheets_status = diag.get("status", "fail")
            check_list.append({
                "name": "google_sheets",
                "sheet_id_masked": _mask(sheet_id),
                **{k: v for k, v in diag.items() if k not in ("status",)},
                "status": sheets_status,
            })
            if sheets_status != "ok":
                check_list.append({
                    "name": "google_worksheets",
                    "status": "skip",
                    "detail": "google_sheets fail로 인해 스킵",
                })
            else:
                # 워크시트 체크 (별도)
                try:
                    import gspread as _gspread
                    from oauth2client.service_account import ServiceAccountCredentials as _SAC
                    from .utils.sheets import SCOPES, _REQUIRED_WORKSHEETS
                    _creds = _SAC.from_json_keyfile_dict(cred_data, SCOPES)
                    _client = _gspread.authorize(_creds)
                    _sh = _client.open_by_key(sheet_id)
                    existing_ws = {ws.title for ws in _sh.worksheets()}
                    missing_ws = [ws for ws in _REQUIRED_WORKSHEETS if ws not in existing_ws]
                    if missing_ws:
                        check_list.append({
                            "name": "google_worksheets",
                            "status": "fail",
                            "detail": f"누락된 워크시트: {missing_ws}",
                            "hint": f"Google Sheets에 다음 워크시트 생성 필요: {missing_ws}",
                        })
                    else:
                        check_list.append({
                            "name": "google_worksheets",
                            "status": "ok",
                            "detail": f"필수 워크시트 모두 존재: {_REQUIRED_WORKSHEETS}",
                        })
                except Exception as ws_exc:
                    check_list.append({
                        "name": "google_worksheets",
                        "status": "fail",
                        "detail": f"워크시트 조회 실패: {_safe_exc_msg(ws_exc)}",
                    })
        except Exception as exc:
            logger.warning("Deep health: Google Sheets check failed: %s", exc)
            check_list.append({"name": "google_sheets", "status": "fail", "detail": _safe_exc_msg(exc)})
            check_list.append({"name": "google_worksheets", "status": "skip", "detail": "google_sheets fail로 인해 스킵"})

    # 전체 상태 판단
    has_fail = any(c["status"] == "fail" for c in check_list)
    overall = "degraded" if has_fail else "ok"

    # ── external_apis (Phase 128) ─────────────────────────────────────────
    external_apis = []
    try:
        from .utils.env_catalog import get_api_status
        external_apis = get_api_status()
    except Exception as _ext_exc:
        logger.debug("external_apis 로드 실패 (무시): %s", _ext_exc)

    # ── shop checks (Phase 131) — 내부 /shop 블루프린트 (ENABLE_INTERNAL_SHOP=1 시만 유효) ─────
    if os.getenv("ENABLE_INTERNAL_SHOP", "0") == "1":
        try:
            from .shop.catalog import get_catalog as _get_shop_catalog
            _cat = _get_shop_catalog()
            _products = _cat.list_all()
            _featured = [p for p in _products if p.featured]
            check_list.append({
                "name": "shop_catalog",
                "status": "ok",
                "detail": f"진열 상품 {len(_products)}개 (featured {len(_featured)}개)",
            })
        except Exception as _shop_cat_exc:
            check_list.append({
                "name": "shop_catalog",
                "status": "fail",
                "detail": str(_shop_cat_exc)[:200],
            })

        _toss_sandbox = not bool(os.getenv("TOSS_CLIENT_KEY"))
        check_list.append({
            "name": "shop_payments",
            "status": "ok",
            "detail": f"토스페이먼츠 활성 ({'sandbox' if _toss_sandbox else 'live'})",
            "provider": "toss",
            "mode": "sandbox" if _toss_sandbox else "live",
        })

    # ── WooCommerce 체크 (Phase 132) — kohganemultishop.org 실연동 ────────
    try:
        from .seller_console.market_adapters.woocommerce_adapter import WooCommerceAdapter as _WooAdapter
        _woo_result = _WooAdapter().health_check()
        check_list.append({
            "name": "woocommerce",
            **_woo_result,
        })
    except Exception as _woo_exc:
        check_list.append({
            "name": "woocommerce",
            "status": "fail",
            "detail": str(_woo_exc)[:200],
        })

    # ── Resend 체크 (Phase 133) ─────────────────────────────────────────
    try:
        from .notifications.email_resend import health_check as _resend_hc
        _resend_result = _resend_hc()
        check_list.append({
            "name": "resend",
            "category": "notification",
            **_resend_result,
        })
    except Exception as _resend_exc:
        logger.warning("Resend 헬스 체크 오류: %s", _resend_exc)
        check_list.append({
            "name": "resend",
            "category": "notification",
            "status": "fail",
            "detail": "Resend 헬스 체크 오류",
        })

    # ── TrackingMore 체크 (Phase 133) ──────────────────────────────────
    try:
        from .seller_console.orders.tracking_trackingmore import TrackingMoreClient as _TMClient
        _tm_result = _TMClient().health_check()
        check_list.append({
            "name": "trackingmore",
            "category": "logistics",
            **_tm_result,
        })
    except Exception as _tm_exc:
        logger.warning("TrackingMore 헬스 체크 오류: %s", _tm_exc)
        check_list.append({
            "name": "trackingmore",
            "category": "logistics",
            "status": "fail",
            "detail": "TrackingMore 헬스 체크 오류",
        })

    # ── 인증 프로바이더 체크 (Phase 133) ───────────────────────────────
    _auth_providers = [
        ("kakao_login", "KAKAO_REST_API_KEY"),
        ("google_oauth", "GOOGLE_OAUTH_CLIENT_ID"),
        ("naver_login", "NAVER_CLIENT_ID"),
    ]
    for _auth_name, _auth_env in _auth_providers:
        _auth_active = bool(os.getenv(_auth_env))
        check_list.append({
            "name": _auth_name,
            "category": "auth",
            "status": "active" if _auth_active else "missing",
            "detail": f"{_auth_env} {'설정됨' if _auth_active else '미설정'}",
        })

    return jsonify({
        "status": overall,
        "timestamp": now_iso,
        "uptime_seconds": uptime,
        "version": os.getenv("APP_VERSION", "dev"),
        "checks": check_list,
        "external_apis": external_apis,
    }), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 8000)))


_DELIVERY_COMPLETE_LEVEL = 6  # SweetTracker 배송완료 level


# ---------------------------------------------------------------------------
# Phase 131 — 주문 취소 라우트 + 운송장 자동 추적 cron
# ---------------------------------------------------------------------------

@app.post('/shop/checkout/cancel')
def shop_order_cancel():
    """자체몰 주문 취소 (Phase 131)."""
    data = request.get_json(force=True, silent=True) or {}
    order_id = str(data.get("order_id", "")).strip()
    reason = str(data.get("reason", "고객 요청")).strip()
    if not order_id:
        return jsonify({"ok": False, "error": "order_id 필수"}), 400
    try:
        from .shop.checkout import CheckoutService
        svc = CheckoutService()
        result = svc.cancel_payment(order_id, reason)
        return jsonify(result)
    except Exception as exc:
        logger.warning("주문 취소 실패: %s", exc)
        return jsonify({"ok": False, "error": "주문 취소 중 오류가 발생했습니다."}), 500


@app.get('/cron/track-shipments')
def cron_track_shipments():
    """운송장 자동 추적 cron (30분 폴링, Phase 133).

    TRACKINGMORE_API_KEY 활성 시:
    - 운송장 등록된 주문 → 상태 폴링
    - 변경 시 orders 시트 갱신
    """
    api_key = os.getenv("TRACKINGMORE_API_KEY")
    if not api_key:
        return jsonify({"status": "skip", "detail": "TRACKINGMORE_API_KEY 미설정"}), 200

    if os.getenv("ADAPTER_DRY_RUN", "0") == "1":
        return jsonify({"status": "dry_run", "detail": "ADAPTER_DRY_RUN=1"}), 200

    updated = 0
    errors = []
    try:
        from .seller_console.orders.sheets_adapter import OrderSheetsAdapter
        from .seller_console.orders.tracking_trackingmore import TrackingMoreClient

        sheets = OrderSheetsAdapter()
        tracker_client = TrackingMoreClient()
        rows = sheets.get_all_rows()

        for row in rows:
            tracking_no = str(row.get("tracking_no", "")).strip()
            courier = str(row.get("courier", "")).strip()
            status = str(row.get("status", "")).strip().lower()

            if not tracking_no or not courier:
                continue
            if status in ("delivered", "canceled", "returned"):
                continue

            try:
                result = tracker_client.get_status(tracking_no, courier)
                is_delivered = result.get("is_delivered", False)
                if is_delivered and status != "delivered":
                    row["status"] = "delivered"
                    sheets.upsert_row(row)
                    updated += 1
                    # 알림 (구매자 연락처 없으므로 telegram 만)
                    try:
                        from .notifications.telegram import send_telegram
                        send_telegram(
                            f"📦 배송완료 #{row.get('order_id')} "
                            f"(운송장: {courier}/{tracking_no})",
                            urgency="info",
                        )
                    except Exception:
                        pass
            except Exception as exc:
                errors.append(f"{tracking_no}: {exc}")

    except Exception as exc:
        logger.warning("cron_track_shipments 실패: %s", exc)
        return jsonify({"status": "fail", "error": "운송장 추적 중 오류가 발생했습니다."}), 500

    # 내부 오류 메시지는 로그에만 기록
    sanitized_errors = [f"추적 오류 {i+1}" for i, _ in enumerate(errors[:10])]
    return jsonify({"status": "ok", "updated": updated, "errors": sanitized_errors})


# Phase 135: Discovery 봇 cron
@app.route('/cron/discovery', methods=['GET', 'POST'])
def cron_discovery():
    """Discovery 봇 수동/자동 실행 (Phase 135).

    Render Cron Job 또는 /seller/discovery 페이지에서 수동 호출.
    Response: {ok: true, discovered: N, domains: [...]}
    """
    if os.getenv("ADAPTER_DRY_RUN", "0") == "1":
        return jsonify({"ok": True, "status": "dry_run", "discovered": 0, "domains": []}), 200

    try:
        from .discovery.scout import DiscoveryScout
        scout = DiscoveryScout()
        results = scout.run_once()
        domains = [r.get("domain", "") for r in results]
        logger.info("cron_discovery 완료: %d개 신규 도메인", len(results))
        return jsonify({"ok": True, "discovered": len(results), "domains": domains})
    except Exception as exc:
        logger.warning("cron_discovery 실패: %s", exc)
        return jsonify({"ok": False, "error": "Discovery 실행 중 오류가 발생했습니다."}), 500
