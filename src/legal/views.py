"""정적 법률 페이지 Blueprint."""
from __future__ import annotations

from flask import Blueprint, render_template

legal_bp = Blueprint("legal", __name__, template_folder="templates")


@legal_bp.get("/privacy")
def privacy():
    return render_template("legal/privacy.html")


@legal_bp.get("/terms")
def terms():
    return render_template("legal/terms.html")
