"""tests/test_form_builder.py — Phase 74: 동적 폼 빌더 테스트."""
from __future__ import annotations

import pytest

from src.form_builder import (
    FormDefinition, FormField, FieldType,
    FormManager, FormValidator, FormSubmission, FormRenderer
)


class TestFieldType:
    def test_field_type_values(self):
        assert FieldType.TEXT.value == "text"
        assert FieldType.NUMBER.value == "number"
        assert FieldType.SELECT.value == "select"
        assert FieldType.CHECKBOX.value == "checkbox"
        assert FieldType.DATE.value == "date"


class TestFormField:
    def test_to_dict(self):
        field = FormField(
            name="username",
            field_type=FieldType.TEXT,
            label="사용자명",
            required=True,
        )
        d = field.to_dict()
        assert d["name"] == "username"
        assert d["field_type"] == "text"
        assert d["required"] is True

    def test_from_dict(self):
        field = FormField.from_dict({
            "name": "email",
            "field_type": "email",
            "label": "이메일",
            "required": True,
        })
        assert field.name == "email"
        assert field.field_type == FieldType.EMAIL


class TestFormDefinition:
    def test_to_dict(self):
        form = FormDefinition(
            name="회원가입",
            fields=[
                FormField("username", FieldType.TEXT, "사용자명", required=True),
            ],
        )
        d = form.to_dict()
        assert d["name"] == "회원가입"
        assert len(d["fields"]) == 1
        assert "form_id" in d


class TestFormManager:
    def setup_method(self):
        self.mgr = FormManager()

    def test_create_form(self):
        form = self.mgr.create(
            name="주문서",
            fields=[
                {"name": "name", "field_type": "text", "label": "이름", "required": True},
            ],
        )
        assert form.name == "주문서"
        assert len(form.fields) == 1

    def test_create_duplicate_raises(self):
        self.mgr.create(name="form1")
        with pytest.raises(ValueError):
            self.mgr.create(name="form1")

    def test_get_form(self):
        form = self.mgr.create(name="form_get")
        retrieved = self.mgr.get(form.form_id)
        assert retrieved is not None
        assert retrieved.name == "form_get"

    def test_get_by_name(self):
        form = self.mgr.create(name="named_form")
        retrieved = self.mgr.get_by_name("named_form")
        assert retrieved is not None
        assert retrieved.form_id == form.form_id

    def test_update_form_increments_version(self):
        form = self.mgr.create(name="versioned")
        assert form.version == 1
        updated = self.mgr.update(form.form_id, description="updated")
        assert updated.version == 2

    def test_delete_form(self):
        form = self.mgr.create(name="to_delete")
        self.mgr.delete(form.form_id)
        assert self.mgr.get(form.form_id) is None

    def test_list_forms(self):
        self.mgr.create(name="f1")
        self.mgr.create(name="f2")
        forms = self.mgr.list()
        assert len(forms) == 2

    def test_version_history(self):
        form = self.mgr.create(name="hist_form")
        self.mgr.update(form.form_id, description="v2")
        history = self.mgr.get_version_history(form.form_id)
        assert len(history) == 2


class TestFormValidator:
    def setup_method(self):
        self.validator = FormValidator()
        self.form = FormDefinition(
            name="test",
            fields=[
                FormField("name", FieldType.TEXT, "이름", required=True),
                FormField("age", FieldType.NUMBER, "나이",
                          validation={"min": 0, "max": 150}),
                FormField("email", FieldType.EMAIL, "이메일"),
                FormField("category", FieldType.SELECT, "카테고리",
                          options=["A", "B", "C"]),
            ],
        )

    def test_valid_data(self):
        data = {"name": "홍길동", "age": 30, "email": "test@example.com", "category": "A"}
        is_valid, errors = self.validator.validate(self.form, data)
        assert is_valid is True
        assert errors == []

    def test_required_field_missing(self):
        data = {"age": 30}
        is_valid, errors = self.validator.validate(self.form, data)
        assert is_valid is False
        assert any("name" in e or "이름" in e for e in errors)

    def test_number_range_violation(self):
        data = {"name": "test", "age": 200}
        is_valid, errors = self.validator.validate(self.form, data)
        assert is_valid is False

    def test_invalid_email(self):
        data = {"name": "test", "email": "not-an-email"}
        is_valid, errors = self.validator.validate(self.form, data)
        assert is_valid is False

    def test_invalid_select_option(self):
        data = {"name": "test", "category": "X"}
        is_valid, errors = self.validator.validate(self.form, data)
        assert is_valid is False

    def test_custom_rule_fields_match(self):
        form = FormDefinition(
            name="pw",
            fields=[
                FormField("password", FieldType.TEXT, "비밀번호", required=True),
                FormField("password_confirm", FieldType.TEXT, "비밀번호 확인", required=True),
            ],
            validation_rules={
                "pw_match": {
                    "type": "fields_match",
                    "fields": ["password", "password_confirm"],
                    "message": "비밀번호가 일치하지 않습니다",
                }
            },
        )
        is_valid, errors = self.validator.validate(form, {"password": "abc", "password_confirm": "xyz"})
        assert is_valid is False
        assert any("비밀번호가 일치하지 않습니다" in e for e in errors)


class TestFormSubmission:
    def setup_method(self):
        self.store = FormSubmission()

    def test_submit(self):
        record = self.store.submit("form1", {"name": "홍길동"}, submitter_id="user1")
        assert record["form_id"] == "form1"
        assert record["data"]["name"] == "홍길동"
        assert "submission_id" in record

    def test_get_submission(self):
        record = self.store.submit("form1", {"name": "test"})
        retrieved = self.store.get(record["submission_id"])
        assert retrieved is not None

    def test_list_by_form(self):
        self.store.submit("form_a", {"x": 1})
        self.store.submit("form_a", {"x": 2})
        self.store.submit("form_b", {"y": 3})
        submissions = self.store.list_by_form("form_a")
        assert len(submissions) == 2

    def test_delete_submission(self):
        record = self.store.submit("form1", {})
        self.store.delete(record["submission_id"])
        assert self.store.get(record["submission_id"]) is None


class TestFormRenderer:
    def setup_method(self):
        self.renderer = FormRenderer()
        self.form = FormDefinition(
            name="테스트 폼",
            fields=[
                FormField("name", FieldType.TEXT, "이름", required=True),
                FormField("age", FieldType.NUMBER, "나이"),
                FormField("category", FieldType.SELECT, "카테고리", options=["A", "B"]),
            ],
        )

    def test_render_contains_form_tag(self):
        html = self.renderer.render(self.form)
        assert "<form" in html
        assert "</form>" in html

    def test_render_contains_fields(self):
        html = self.renderer.render(self.form)
        assert 'name="name"' in html
        assert 'name="age"' in html

    def test_render_required_field(self):
        html = self.renderer.render(self.form)
        assert "required" in html

    def test_render_select_options(self):
        html = self.renderer.render(self.form)
        assert "<select" in html
        assert "<option" in html

    def test_render_with_values(self):
        html = self.renderer.render(self.form, values={"name": "홍길동"})
        assert "홍길동" in html
