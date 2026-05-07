from __future__ import annotations

from flask import Blueprint, render_template

onboarding_bp = Blueprint("onboarding", __name__, template_folder="templates")


@onboarding_bp.get("/onboarding")
def onboarding():
    return render_template("onboarding.html")
