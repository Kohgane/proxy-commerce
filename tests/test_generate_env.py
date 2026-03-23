"""Tests for scripts/generate_env.py."""

from scripts.generate_env import substitute_placeholders, generate_env


class TestSubstitutePlaceholders:
    def test_replaces_staging_placeholder(self, monkeypatch):
        monkeypatch.setenv('STAGING_GOOGLE_SHEET_ID', 'real-sheet-id')
        text = 'GOOGLE_SHEET_ID=${STAGING_GOOGLE_SHEET_ID}'
        result, unresolved = substitute_placeholders(text)
        assert result == 'GOOGLE_SHEET_ID=real-sheet-id'
        assert unresolved == []

    def test_replaces_production_placeholder(self, monkeypatch):
        monkeypatch.setenv('PROD_SHOPIFY_SHOP', 'my-prod-store.myshopify.com')
        text = 'SHOPIFY_SHOP=${PROD_SHOPIFY_SHOP}'
        result, unresolved = substitute_placeholders(text)
        assert result == 'SHOPIFY_SHOP=my-prod-store.myshopify.com'
        assert unresolved == []

    def test_warns_about_unreplaced_placeholders(self, monkeypatch):
        monkeypatch.delenv('STAGING_MISSING_VAR', raising=False)
        text = 'SOME_KEY=${STAGING_MISSING_VAR}'
        result, unresolved = substitute_placeholders(text)
        assert result == 'SOME_KEY=${STAGING_MISSING_VAR}'
        assert 'STAGING_MISSING_VAR' in unresolved

    def test_replaces_multiple_placeholders(self, monkeypatch):
        monkeypatch.setenv('STAGING_FOO', 'foo_value')
        monkeypatch.setenv('STAGING_BAR', 'bar_value')
        text = 'FOO=${STAGING_FOO}\nBAR=${STAGING_BAR}'
        result, unresolved = substitute_placeholders(text)
        assert 'FOO=foo_value' in result
        assert 'BAR=bar_value' in result
        assert unresolved == []

    def test_partial_substitution_returns_unresolved(self, monkeypatch):
        monkeypatch.setenv('STAGING_PRESENT', 'val')
        monkeypatch.delenv('STAGING_ABSENT', raising=False)
        text = 'A=${STAGING_PRESENT}\nB=${STAGING_ABSENT}'
        result, unresolved = substitute_placeholders(text)
        assert 'A=val' in result
        assert 'STAGING_ABSENT' in unresolved


class TestGenerateEnv:
    def test_staging_template_substitution(self, tmp_path, monkeypatch):
        template = tmp_path / '.env.staging'
        output = tmp_path / '.env'
        template.write_text('GOOGLE_SHEET_ID=${STAGING_GOOGLE_SHEET_ID}\n')

        monkeypatch.setenv('STAGING_GOOGLE_SHEET_ID', 'staging-sheet-123')
        monkeypatch.chdir(tmp_path)

        all_resolved = generate_env('staging', str(output))

        assert all_resolved is True
        content = output.read_text()
        assert 'staging-sheet-123' in content

    def test_production_template_substitution(self, tmp_path, monkeypatch):
        template = tmp_path / '.env.production'
        output = tmp_path / '.env'
        template.write_text('SHOPIFY_SHOP=${PROD_SHOPIFY_SHOP}\n')

        monkeypatch.setenv('PROD_SHOPIFY_SHOP', 'prod-store.myshopify.com')
        monkeypatch.chdir(tmp_path)

        all_resolved = generate_env('production', str(output))

        assert all_resolved is True
        content = output.read_text()
        assert 'SHOPIFY_SHOP=prod-store.myshopify.com' in content

    def test_returns_false_with_unresolved_placeholders(self, tmp_path, monkeypatch):
        template = tmp_path / '.env.staging'
        output = tmp_path / '.env'
        template.write_text('MISSING_KEY=${STAGING_MISSING_VAR}\n')

        monkeypatch.delenv('STAGING_MISSING_VAR', raising=False)
        monkeypatch.chdir(tmp_path)

        all_resolved = generate_env('staging', str(output))

        assert all_resolved is False
        content = output.read_text()
        assert '${STAGING_MISSING_VAR}' in content

    def test_warning_logged_for_unreplaced_placeholders(self, tmp_path, monkeypatch, caplog):
        import logging
        template = tmp_path / '.env.staging'
        output = tmp_path / '.env'
        template.write_text('X=${STAGING_UNSET_VAR}\n')

        monkeypatch.delenv('STAGING_UNSET_VAR', raising=False)
        monkeypatch.chdir(tmp_path)

        with caplog.at_level(logging.WARNING, logger='scripts.generate_env'):
            generate_env('staging', str(output))

        assert any('STAGING_UNSET_VAR' in rec.message for rec in caplog.records)
