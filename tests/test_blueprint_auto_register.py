from __future__ import annotations

import importlib
import types

from flask import Blueprint, Flask

from src.order_webhook import _auto_register_blueprints


def test_auto_register_blueprints_registers_missing_blueprint(monkeypatch):
    app = Flask(__name__)
    bp = Blueprint("auto_stub_bp", __name__, url_prefix="/auto-stub")

    @bp.get("/ping")
    def ping():
        return "ok"

    fake_module = types.SimpleNamespace(bp=bp)

    def _fake_import_module(name: str):
        if name == "src.fake.routes":
            return fake_module
        raise ImportError(name)

    monkeypatch.setattr(importlib, "import_module", _fake_import_module)
    registered = _auto_register_blueprints(app, module_names=("src.fake.routes",))

    assert "auto_stub_bp" in registered
    assert "auto_stub_bp" in app.blueprints
    paths = {rule.rule for rule in app.url_map.iter_rules()}
    assert "/auto-stub/ping" in paths


def test_auto_register_blueprints_skips_already_registered(monkeypatch):
    app = Flask(__name__)
    bp = Blueprint("auto_stub_bp", __name__, url_prefix="/auto-stub")
    app.register_blueprint(bp)
    fake_module = types.SimpleNamespace(bp=bp)

    monkeypatch.setattr(importlib, "import_module", lambda _name: fake_module)
    registered = _auto_register_blueprints(app, module_names=("src.fake.routes",))

    assert registered == []
