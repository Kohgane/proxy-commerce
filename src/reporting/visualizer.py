"""src/reporting/visualizer.py — 텍스트 기반 시각화 도구.

순수 stdlib만 사용하여 바 차트와 테이블을 텍스트로 렌더링한다.
"""


def render_bar_chart(data: dict, title: str, width: int = 40) -> str:
    """바 차트를 텍스트로 렌더링한다.

    Args:
        data: {레이블: 값} 딕셔너리.
        title: 차트 제목.
        width: 막대의 최대 문자 너비 (기본 40).

    Returns:
        텍스트 차트 문자열.
    """
    if not data:
        lines = [title, "─" * (width + 20), "(데이터 없음)"]
        return '\n'.join(lines)

    max_val = max(float(v) for v in data.values()) if data else 1.0
    if max_val == 0:
        max_val = 1.0

    max_label_len = max(len(str(k)) for k in data) if data else 1
    lines = [title, "─" * (max_label_len + width + 15)]

    for label, value in data.items():
        try:
            fval = float(value)
        except (ValueError, TypeError):
            fval = 0.0
        filled = int(fval / max_val * width)
        empty = width - filled
        bar = "█" * filled + "░" * empty
        label_str = str(label).rjust(max_label_len)
        lines.append(f"{label_str} |{bar}| {fval:,.0f}")

    return '\n'.join(lines)


def render_table(headers: list, rows: list, align: str = 'right') -> str:
    """테이블을 텍스트로 렌더링한다.

    Args:
        headers: 헤더 문자열 리스트.
        rows: 각 행이 값 리스트인 2차원 리스트.
        align: 'right' 또는 'left' (기본 'right').

    Returns:
        텍스트 테이블 문자열.
    """
    if not headers:
        return ""

    all_rows = [headers] + [[str(cell) for cell in row] for row in rows]

    col_widths = []
    for col_idx in range(len(headers)):
        col_width = max(
            len(str(row[col_idx])) if col_idx < len(row) else 0
            for row in all_rows
        )
        col_widths.append(col_width)

    def fmt_row(row: list) -> str:
        cells = []
        for i, width in enumerate(col_widths):
            cell = str(row[i]) if i < len(row) else ""
            if align == 'right':
                cells.append(cell.rjust(width))
            else:
                cells.append(cell.ljust(width))
        return " | ".join(cells)

    separator = "-+-".join("-" * w for w in col_widths)

    lines = [fmt_row(headers), separator]
    for row in rows:
        lines.append(fmt_row([str(c) for c in row]))

    return '\n'.join(lines)
