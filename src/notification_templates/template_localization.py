"""src/notification_templates/template_localization.py — 템플릿 현지화."""
from __future__ import annotations


class TemplateLocalization:
    """템플릿 현지화 관리자."""

    def __init__(self) -> None:
        self._supported = ['ko', 'en', 'ja', 'zh']
        self._locale_templates: dict[str, dict] = {}

    def supported_locales(self) -> list:
        """지원 언어 목록을 반환한다."""
        return list(self._supported)

    def translate(self, template_name: str, locale: str) -> dict:
        """템플릿을 번역한다."""
        key = f'{template_name}|{locale}'
        return self._locale_templates.get(key, {})

    def set_locale_template(self, template_name: str, locale: str, subject: str, body: str) -> None:
        """로케일 템플릿을 설정한다."""
        key = f'{template_name}|{locale}'
        self._locale_templates[key] = {'subject': subject, 'body': body}

    def get_locale_template(self, template_name: str, locale: str) -> dict | None:
        """로케일 템플릿을 반환한다."""
        key = f'{template_name}|{locale}'
        return self._locale_templates.get(key)
