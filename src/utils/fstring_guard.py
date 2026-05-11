from __future__ import annotations

import re

FSTRING_BACKSLASH_IN_EXPR_PATTERN = re.compile(
    r"(?:rf|fr|f)(?:"
    r"[\"'][^\"\n]*\{[^}\n]*\\[^}\n]*\}[^\"\n]*[\"']"
    r"|'''[\s\S]*?\{[^}]*\\[^}]*\}[\s\S]*?'''"
    r'|"""[\s\S]*?\{[^}]*\\[^}]*\}[\s\S]*?"""'
    r")"
)
