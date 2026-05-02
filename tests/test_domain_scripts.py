"""
tests/test_domain_scripts.py — render_domain_attach.py / cloudflare_setup.py 단위 테스트.

mock된 Render API로 list/add/remove 동작을 검증합니다.
실제 API 호출 없이 stdlib unittest.mock만 사용합니다.
"""
from __future__ import annotations

import json
import sys
import os
import unittest
from io import StringIO
from unittest.mock import MagicMock, patch, call

# scripts 디렉토리를 경로에 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))


# ══════════════════════════════════════════════════════════
# render_domain_attach.py 테스트
# ══════════════════════════════════════════════════════════

class TestRenderDomainAttach(unittest.TestCase):
    """render_domain_attach.py 동작 검증."""

    def _make_resp(self, body: dict, status: int = 200):
        """urllib mock 응답 객체를 생성합니다."""
        m = MagicMock()
        m.read.return_value = json.dumps(body).encode()
        m.status = status
        m.__enter__ = lambda s: s
        m.__exit__ = MagicMock(return_value=False)
        return m

    def test_list_custom_domains_empty(self):
        """도메인 없을 때 빈 목록 출력."""
        import render_domain_attach as rda
        with patch('render_domain_attach._render_request', return_value=[]) as mock_req:
            with patch('sys.stdout', new_callable=StringIO) as mock_out:
                count = rda.list_custom_domains('srv-test', 'token123')
        self.assertEqual(count, 0)
        mock_req.assert_called_once_with('GET', '/services/srv-test/custom-domains', 'token123')

    def test_list_custom_domains_shows_slot_usage(self):
        """도메인 목록에 슬롯 사용량(n/2)이 출력된다."""
        import render_domain_attach as rda
        domains = [
            {'name': 'example.com', 'verificationStatus': 'verified'},
            {'name': 'www.example.com', 'verificationStatus': 'pending'},
        ]
        with patch('render_domain_attach._render_request', return_value=domains):
            with patch('sys.stdout', new_callable=StringIO) as mock_out:
                count = rda.list_custom_domains('srv-test', 'token123')
                output = mock_out.getvalue()
        self.assertEqual(count, 2)
        self.assertIn('2/2', output)

    def test_get_current_domains_list_response(self):
        """API가 list를 직접 반환할 때 정상 파싱."""
        import render_domain_attach as rda
        domains = [{'name': 'a.com', 'verificationStatus': 'verified'}]
        with patch('render_domain_attach._render_request', return_value=domains):
            result = rda.get_current_domains('srv-test', 'token')
        self.assertEqual(result, domains)

    def test_get_current_domains_dict_response(self):
        """API가 dict로 반환할 때 customDomains 키 파싱."""
        import render_domain_attach as rda
        domains = [{'name': 'a.com', 'verificationStatus': 'verified'}]
        with patch('render_domain_attach._render_request', return_value={'customDomains': domains}):
            result = rda.get_current_domains('srv-test', 'token')
        self.assertEqual(result, domains)

    def test_check_slot_availability_returns_count_and_list(self):
        """슬롯 확인 함수가 (개수, 목록) 튜플을 반환한다."""
        import render_domain_attach as rda
        domains = [
            {'name': 'a.com', 'id': 'id-1', 'verificationStatus': 'verified'},
            {'name': 'b.com', 'id': 'id-2', 'verificationStatus': 'verified'},
        ]
        with patch('render_domain_attach.get_current_domains', return_value=domains):
            count, lst = rda.check_slot_availability('srv-test', 'token')
        self.assertEqual(count, 2)
        self.assertEqual(lst, domains)

    def test_add_custom_domain_success(self):
        """도메인 추가 성공 시 domain id 반환."""
        import render_domain_attach as rda
        with patch('render_domain_attach._render_request', return_value={'id': 'dom-123'}):
            with patch('sys.stdout', new_callable=StringIO):
                result = rda.add_custom_domain('srv-test', 'new.com', 'token')
        self.assertEqual(result, 'dom-123')

    def test_add_custom_domain_already_exists(self):
        """이미 추가된 도메인 — None 반환, 에러 아님."""
        import render_domain_attach as rda
        with patch('render_domain_attach._render_request', return_value={'status': 'already_exists'}):
            with patch('sys.stdout', new_callable=StringIO):
                result = rda.add_custom_domain('srv-test', 'existing.com', 'token')
        self.assertIsNone(result)

    def test_remove_custom_domain_success(self):
        """도메인 제거 성공."""
        import render_domain_attach as rda
        domains = [{'name': 'old.com', 'id': 'dom-456', 'verificationStatus': 'verified'}]
        with patch('render_domain_attach.get_current_domains', return_value=domains):
            with patch('render_domain_attach._render_request', return_value={'status': 'deleted'}):
                with patch('sys.stdout', new_callable=StringIO):
                    result = rda.remove_custom_domain('srv-test', 'old.com', 'token')
        self.assertTrue(result)

    def test_remove_custom_domain_not_found(self):
        """등록되지 않은 도메인 제거 시도 — False 반환."""
        import render_domain_attach as rda
        with patch('render_domain_attach.get_current_domains', return_value=[]):
            with patch('sys.stdout', new_callable=StringIO):
                result = rda.remove_custom_domain('srv-test', 'notexist.com', 'token')
        self.assertFalse(result)

    def test_main_list_domains_flag(self):
        """--list-domains 플래그 → list_custom_domains 호출 후 exit 0."""
        import render_domain_attach as rda
        with patch('sys.argv', ['rda', '--list-domains']):
            with patch.dict('os.environ', {'RENDER_API_TOKEN': 'tok'}):
                with patch('render_domain_attach.list_custom_domains', return_value=0) as mock_list:
                    with patch('render_domain_attach.get_onrender_host', return_value='proxy-commerce-h5x2.onrender.com'):
                        with patch('sys.stdout', new_callable=StringIO):
                            code = rda.main()
        self.assertEqual(code, 0)
        mock_list.assert_called_once()

    def test_main_remove_domain_flag(self):
        """--remove-domain 플래그 → remove_custom_domain 호출."""
        import render_domain_attach as rda
        with patch('sys.argv', ['rda', '--remove-domain', 'old.com']):
            with patch.dict('os.environ', {'RENDER_API_TOKEN': 'tok'}):
                with patch('render_domain_attach.remove_custom_domain', return_value=True) as mock_rm:
                    with patch('sys.stdout', new_callable=StringIO):
                        code = rda.main()
        self.assertEqual(code, 0)
        mock_rm.assert_called_once()

    def test_main_slot_full_exits_code_2(self):
        """Hobby Tier 슬롯 가득 차면 exit code 2 반환."""
        import render_domain_attach as rda
        domains = [
            {'name': 'a.com', 'id': 'id-1'},
            {'name': 'b.com', 'id': 'id-2'},
        ]
        with patch('sys.argv', ['rda', '--domains', 'c.com', '--no-poll']):
            with patch.dict('os.environ', {'RENDER_API_TOKEN': 'tok'}):
                with patch('render_domain_attach.check_slot_availability', return_value=(2, domains)):
                    with patch('sys.stdout', new_callable=StringIO):
                        code = rda.main()
        self.assertEqual(code, 2)

    def test_main_no_token_exits_1(self):
        """RENDER_API_TOKEN 없으면 exit code 1 반환."""
        import render_domain_attach as rda
        env = {k: v for k, v in os.environ.items() if k != 'RENDER_API_TOKEN'}
        with patch('sys.argv', ['rda', '--list-domains']):
            with patch.dict('os.environ', env, clear=True):
                with patch('sys.stdout', new_callable=StringIO):
                    code = rda.main()
        self.assertEqual(code, 1)

    def test_get_onrender_host_extracts_hostname(self):
        """serviceDetails.url에서 onrender.com 호스트명을 추출한다."""
        import render_domain_attach as rda
        service_info = {'serviceDetails': {'url': 'https://proxy-commerce-h5x2.onrender.com'}}
        with patch('render_domain_attach.get_service_info', return_value=service_info):
            host = rda.get_onrender_host('srv-test', 'token')
        self.assertEqual(host, 'proxy-commerce-h5x2.onrender.com')

    def test_get_onrender_host_returns_none_on_empty(self):
        """url 필드가 없을 때 None 반환."""
        import render_domain_attach as rda
        with patch('render_domain_attach.get_service_info', return_value={}):
            host = rda.get_onrender_host('srv-test', 'token')
        self.assertIsNone(host)


# ══════════════════════════════════════════════════════════
# cloudflare_setup.py 테스트
# ══════════════════════════════════════════════════════════

class TestCloudflareSetup(unittest.TestCase):
    """cloudflare_setup.py 동작 검증."""

    def test_render_get_service_url_extracts_host(self):
        """Render API 응답에서 onrender.com 호스트를 추출한다."""
        import cloudflare_setup as cs
        mock_resp_body = json.dumps({
            'serviceDetails': {'url': 'https://proxy-commerce-abc.onrender.com'}
        }).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = mock_resp_body
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch('urllib.request.urlopen', return_value=mock_resp):
            host = cs._render_get_service_url('srv-test', 'render-tok')
        self.assertEqual(host, 'proxy-commerce-abc.onrender.com')

    def test_render_get_service_url_returns_none_on_error(self):
        """Render API 호출 실패 시 None 반환 (sys.exit 없음)."""
        import cloudflare_setup as cs
        import urllib.error
        with patch('urllib.request.urlopen', side_effect=Exception('network error')):
            with patch('sys.stdout', new_callable=StringIO):
                host = cs._render_get_service_url('srv-test', 'token')
        self.assertIsNone(host)

    def test_upsert_dns_record_creates_new(self):
        """기존 레코드 없으면 POST로 생성."""
        import cloudflare_setup as cs
        with patch('cloudflare_setup._list_dns_records', return_value=[]):
            with patch('cloudflare_setup._cf_request') as mock_req:
                with patch('sys.stdout', new_callable=StringIO):
                    cs.upsert_dns_record(
                        'zone-1', 'example.com', 'CNAME', 'target.onrender.com',
                        False, 'cf-tok', False
                    )
        # POST가 호출되어야 함
        calls = mock_req.call_args_list
        methods = [c[0][0] for c in calls]
        self.assertIn('POST', methods)

    def test_upsert_dns_record_updates_existing(self):
        """기존 레코드 있으면 PUT으로 업데이트 (idempotent)."""
        import cloudflare_setup as cs
        existing = [{'id': 'rec-1', 'content': 'old-target.onrender.com'}]
        with patch('cloudflare_setup._list_dns_records', return_value=existing):
            with patch('cloudflare_setup._cf_request') as mock_req:
                with patch('sys.stdout', new_callable=StringIO):
                    cs.upsert_dns_record(
                        'zone-1', 'example.com', 'CNAME', 'new-target.onrender.com',
                        False, 'cf-tok', False
                    )
        calls = mock_req.call_args_list
        methods = [c[0][0] for c in calls]
        self.assertIn('PUT', methods)

    def test_upsert_dns_record_dry_run_no_api_call(self):
        """dry-run 모드에서 실제 API 호출 없음."""
        import cloudflare_setup as cs
        existing = [{'id': 'rec-1', 'content': 'old.onrender.com'}]
        with patch('cloudflare_setup._list_dns_records', return_value=existing):
            with patch('cloudflare_setup._cf_request') as mock_req:
                with patch('sys.stdout', new_callable=StringIO):
                    # dry_run=True → PUT/POST 호출 안 함
                    cs.upsert_dns_record(
                        'zone-1', 'example.com', 'CNAME', 'new.onrender.com',
                        False, 'cf-tok', True
                    )
        # dry-run이면 _cf_request의 modifying 호출 없어야 함
        # (PUT은 dry_run=True로 전달되어 내부에서 스킵됨)
        for c in mock_req.call_args_list:
            method = c[0][0]
            dry = c[0][4] if len(c[0]) > 4 else c[1].get('dry_run', False)
            if method == 'PUT':
                self.assertTrue(dry)

    def test_main_target_auto_fetches_render_host(self):
        """--target auto 모드에서 Render API 호출 후 target을 자동 설정."""
        import cloudflare_setup as cs
        with patch('sys.argv', ['cs', '--apex', 'example.com', '--target', 'auto',
                                '--service-id', 'srv-test', '--dry-run']):
            with patch.dict('os.environ', {
                'CF_API_TOKEN': 'cf-tok',
                'RENDER_API_TOKEN': 'render-tok',
            }):
                with patch('cloudflare_setup._render_get_service_url',
                           return_value='proxy-commerce-abc.onrender.com') as mock_auto:
                    with patch('cloudflare_setup.get_zone_id', return_value='zone-1'):
                        with patch('cloudflare_setup.upsert_dns_record'):
                            with patch('cloudflare_setup.set_ssl_mode'):
                                with patch('cloudflare_setup.set_always_use_https'):
                                    with patch('sys.stdout', new_callable=StringIO):
                                        code = cs.main()
        self.assertEqual(code, 0)
        mock_auto.assert_called_once_with('srv-test', 'render-tok')

    def test_main_target_auto_fails_without_render_token(self):
        """--target auto 모드에서 RENDER_API_TOKEN 없으면 exit 1."""
        import cloudflare_setup as cs
        env = {k: v for k, v in os.environ.items() if k != 'RENDER_API_TOKEN'}
        env['CF_API_TOKEN'] = 'cf-tok'
        with patch('sys.argv', ['cs', '--target', 'auto']):
            with patch.dict('os.environ', env, clear=True):
                with patch('sys.stdout', new_callable=StringIO):
                    code = cs.main()
        self.assertEqual(code, 1)

    def test_main_no_cf_token_exits_1(self):
        """CF_API_TOKEN 없으면 exit 1."""
        import cloudflare_setup as cs
        env = {k: v for k, v in os.environ.items() if k != 'CF_API_TOKEN'}
        with patch('sys.argv', ['cs']):
            with patch.dict('os.environ', env, clear=True):
                with patch('sys.stdout', new_callable=StringIO):
                    code = cs.main()
        self.assertEqual(code, 1)

    def test_verify_dns_propagation_dry_run(self):
        """dry_run=True이면 실제 DNS 조회 없이 True 반환."""
        import cloudflare_setup as cs
        with patch('sys.stdout', new_callable=StringIO):
            result = cs.verify_dns_propagation('example.com', 'target.onrender.com', dry_run=True)
        self.assertTrue(result)

    def test_verify_dns_propagation_cname_match(self):
        """DoH 응답이 예상 CNAME과 일치하면 True 반환."""
        import cloudflare_setup as cs
        doh_resp = json.dumps({
            'Answer': [{'type': 5, 'data': 'proxy-commerce-abc.onrender.com.'}]
        }).encode()
        mock_doh = MagicMock()
        mock_doh.read.return_value = doh_resp
        mock_doh.__enter__ = lambda s: s
        mock_doh.__exit__ = MagicMock(return_value=False)

        import socket
        with patch('urllib.request.urlopen', return_value=mock_doh):
            with patch('socket.getaddrinfo', return_value=[(None, None, None, None, ('1.2.3.4', 0))]):
                with patch('sys.stdout', new_callable=StringIO):
                    result = cs.verify_dns_propagation(
                        'example.com', 'proxy-commerce-abc.onrender.com', dry_run=False
                    )
        self.assertTrue(result)


# ══════════════════════════════════════════════════════════
# 슬롯 만석 에러 핸들링 통합 검증
# ══════════════════════════════════════════════════════════

class TestSlotFullErrorHandling(unittest.TestCase):
    """Hobby Tier 슬롯 2/2 에러 핸들링을 end-to-end로 검증."""

    def test_slot_full_message_contains_remove_hint(self):
        """슬롯 가득 시 출력에 --remove-domain 가이드가 포함된다."""
        import render_domain_attach as rda

        domains = [
            {'name': 'kohganemultishop.org', 'id': 'id-1'},
            {'name': 'www.kohganemultishop.org', 'id': 'id-2'},
        ]
        with patch('sys.argv', ['rda', '--domains', 'kohganepercentiii.com', '--no-poll']):
            with patch.dict('os.environ', {'RENDER_API_TOKEN': 'tok'}):
                with patch('render_domain_attach.check_slot_availability', return_value=(2, domains)):
                    with patch('sys.stdout', new_callable=StringIO) as mock_out:
                        code = rda.main()
                        output = mock_out.getvalue()

        self.assertEqual(code, 2)
        self.assertIn('--remove-domain', output)
        self.assertIn('kohganemultishop.org', output)

    def test_slot_full_exit_code_is_2_not_1(self):
        """슬롯 만석 에러는 일반 에러(1)와 구분되는 exit code 2를 반환한다."""
        import render_domain_attach as rda

        domains = [{'name': 'a.com', 'id': 'id-1'}, {'name': 'b.com', 'id': 'id-2'}]
        with patch('sys.argv', ['rda', '--domains', 'c.com', '--no-poll']):
            with patch.dict('os.environ', {'RENDER_API_TOKEN': 'tok'}):
                with patch('render_domain_attach.check_slot_availability', return_value=(2, domains)):
                    with patch('sys.stdout', new_callable=StringIO):
                        code = rda.main()

        self.assertEqual(code, 2)
        self.assertNotEqual(code, 1)


if __name__ == '__main__':
    unittest.main()
