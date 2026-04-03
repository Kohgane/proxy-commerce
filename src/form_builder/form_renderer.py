"""src/form_builder/form_renderer.py — 폼 HTML 렌더링 (서버사이드)."""
from __future__ import annotations

import html
from typing import Any, Dict

from .form_definition import FormDefinition, FormField, FieldType


class FormRenderer:
    """폼 HTML 렌더링 (서버사이드, 순수 Python)."""

    def render(self, form: FormDefinition, values: Dict[str, Any] = None) -> str:
        """폼을 HTML 문자열로 렌더링."""
        values = values or {}
        lines = [
            f'<form id="{html.escape(form.form_id)}" '
            f'name="{html.escape(form.name)}" method="post">',
            f'  <h2>{html.escape(form.name)}</h2>',
        ]
        if form.description:
            lines.append(f'  <p>{html.escape(form.description)}</p>')

        for field in form.fields:
            lines.append(self._render_field(field, values.get(field.name)))

        lines.append('  <button type="submit">제출</button>')
        lines.append("</form>")
        return "\n".join(lines)

    def _render_field(self, field: FormField, value: Any = None) -> str:
        ft = field.field_type
        name = html.escape(field.name)
        label = html.escape(field.label)
        required = ' required' if field.required else ''
        placeholder = f' placeholder="{html.escape(field.placeholder)}"' if field.placeholder else ''
        val_str = html.escape(str(value)) if value is not None else ""

        label_html = f'  <label for="{name}">{label}{"*" if field.required else ""}</label>'

        if ft == FieldType.TEXTAREA:
            input_html = (
                f'  <textarea id="{name}" name="{name}"{required}{placeholder}>'
                f'{val_str}</textarea>'
            )
        elif ft == FieldType.SELECT:
            opts = "".join(
                f'<option value="{html.escape(str(o))}"'
                f'{"selected" if str(o) == val_str else ""}>{html.escape(str(o))}</option>'
                for o in field.options
            )
            input_html = f'  <select id="{name}" name="{name}"{required}>{opts}</select>'
        elif ft == FieldType.CHECKBOX:
            checked = ' checked' if value else ''
            input_html = (
                f'  <input type="checkbox" id="{name}" name="{name}" '
                f'value="true"{checked}{required}>'
            )
        elif ft == FieldType.DATE:
            input_html = (
                f'  <input type="date" id="{name}" name="{name}" '
                f'value="{val_str}"{required}{placeholder}>'
            )
        elif ft == FieldType.NUMBER:
            input_html = (
                f'  <input type="number" id="{name}" name="{name}" '
                f'value="{val_str}"{required}{placeholder}>'
            )
        elif ft == FieldType.FILE:
            input_html = f'  <input type="file" id="{name}" name="{name}"{required}>'
        elif ft == FieldType.EMAIL:
            input_html = (
                f'  <input type="email" id="{name}" name="{name}" '
                f'value="{val_str}"{required}{placeholder}>'
            )
        elif ft == FieldType.PHONE:
            input_html = (
                f'  <input type="tel" id="{name}" name="{name}" '
                f'value="{val_str}"{required}{placeholder}>'
            )
        else:
            input_html = (
                f'  <input type="text" id="{name}" name="{name}" '
                f'value="{val_str}"{required}{placeholder}>'
            )

        return f'  <div class="form-group">\n{label_html}\n{input_html}\n  </div>'
