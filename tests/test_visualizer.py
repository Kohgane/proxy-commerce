"""tests/test_visualizer.py — 시각화 도구 테스트 (순수 함수, 모킹 불필요)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.reporting.visualizer import render_bar_chart, render_table


class TestRenderBarChart:
    def test_render_bar_chart_basic(self):
        """기본 바 차트는 제목을 포함한 문자열을 반환해야 한다."""
        data = {"A": 10, "B": 20, "C": 5}
        result = render_bar_chart(data, "테스트 차트")
        assert isinstance(result, str)
        assert "테스트 차트" in result
        assert "A" in result
        assert "B" in result

    def test_render_bar_chart_empty(self):
        """빈 데이터는 오류 없이 처리되어야 한다."""
        result = render_bar_chart({}, "빈 차트")
        assert isinstance(result, str)
        assert "빈 차트" in result

    def test_render_bar_chart_width(self):
        """width 파라미터가 적용되어야 한다."""
        data = {"X": 100}
        result_narrow = render_bar_chart(data, "T", width=10)
        result_wide = render_bar_chart(data, "T", width=40)
        # 더 넓은 차트가 더 많은 블록 문자를 가져야 함
        assert result_wide.count("█") >= result_narrow.count("█")

    def test_render_bar_chart_values_shown(self):
        """차트에 값이 표시되어야 한다."""
        data = {"항목": 42}
        result = render_bar_chart(data, "값 표시 테스트")
        assert "42" in result

    def test_render_bar_chart_single_item(self):
        """단일 항목도 정상적으로 렌더링되어야 한다."""
        result = render_bar_chart({"only": 1}, "단일")
        assert "only" in result


class TestRenderTable:
    def test_render_table_basic(self):
        """기본 테이블은 헤더를 포함한 문자열을 반환해야 한다."""
        headers = ["이름", "값"]
        rows = [["A", "100"], ["B", "200"]]
        result = render_table(headers, rows)
        assert isinstance(result, str)
        assert "이름" in result
        assert "값" in result
        assert "A" in result

    def test_render_table_alignment_right(self):
        """right 정렬 옵션이 적용되어야 한다."""
        headers = ["col"]
        rows = [["x"]]
        result = render_table(headers, rows, align='right')
        assert isinstance(result, str)

    def test_render_table_alignment_left(self):
        """left 정렬 옵션이 적용되어야 한다."""
        headers = ["col"]
        rows = [["x"]]
        result = render_table(headers, rows, align='left')
        assert isinstance(result, str)

    def test_render_table_empty_rows(self):
        """빈 행 목록은 헤더만 있는 테이블을 반환해야 한다."""
        headers = ["H1", "H2"]
        result = render_table(headers, [])
        assert "H1" in result
        assert "H2" in result

    def test_render_table_separator(self):
        """헤더와 데이터 사이에 구분선이 있어야 한다."""
        headers = ["A", "B"]
        rows = [["1", "2"]]
        result = render_table(headers, rows)
        assert "-" in result
