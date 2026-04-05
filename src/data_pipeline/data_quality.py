"""src/data_pipeline/data_quality.py — 데이터 품질 관리 (Phase 100)."""
from __future__ import annotations

import re
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional


@dataclass
class QualityViolation:
    rule_name: str
    field: str
    row_index: int
    value: object
    message: str

    def to_dict(self) -> dict:
        return {
            "rule_name": self.rule_name,
            "field": self.field,
            "row_index": self.row_index,
            "value": self.value,
            "message": self.message,
        }


@dataclass
class QualityReport:
    table_name: str
    checked_at: str
    total_rows: int
    passed_rows: int
    failed_rows: int
    score: float
    violations: list = field(default_factory=list)
    rule_results: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "table_name": self.table_name,
            "checked_at": self.checked_at,
            "total_rows": self.total_rows,
            "passed_rows": self.passed_rows,
            "failed_rows": self.failed_rows,
            "score": self.score,
            "violations": [v.to_dict() if hasattr(v, "to_dict") else v for v in self.violations],
            "rule_results": self.rule_results,
        }


@dataclass
class QualityAlert:
    alert_id: str
    table_name: str
    report: QualityReport
    threshold: float
    created_at: str

    def to_dict(self) -> dict:
        return {
            "alert_id": self.alert_id,
            "table_name": self.table_name,
            "report": self.report.to_dict(),
            "threshold": self.threshold,
            "created_at": self.created_at,
        }


class QualityRule(ABC):
    """데이터 품질 규칙 추상 기반 클래스."""

    @property
    @abstractmethod
    def rule_name(self) -> str:
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        ...

    @abstractmethod
    def check(self, data: list[dict]) -> tuple[int, list[QualityViolation]]:
        """(passed_count, violations) 반환."""
        ...


class NotNullRule(QualityRule):
    """Null/빈 값 검사."""

    def __init__(self, fields: list[str]) -> None:
        self._fields = fields

    @property
    def rule_name(self) -> str:
        return f"not_null({'|'.join(self._fields)})"

    @property
    def description(self) -> str:
        return f"필드 {self._fields}에 null 값 없음 검사"

    def check(self, data: list[dict]) -> tuple[int, list[QualityViolation]]:
        violations = []
        passed = 0
        for i, row in enumerate(data):
            row_ok = True
            for f in self._fields:
                val = row.get(f)
                if val is None or val == "":
                    violations.append(QualityViolation(
                        rule_name=self.rule_name, field=f, row_index=i,
                        value=val, message=f"필드 '{f}'이 null 또는 빈 값",
                    ))
                    row_ok = False
            if row_ok:
                passed += 1
        return passed, violations


class UniqueRule(QualityRule):
    """유일성 검사."""

    def __init__(self, fields: list[str]) -> None:
        self._fields = fields

    @property
    def rule_name(self) -> str:
        return f"unique({'|'.join(self._fields)})"

    @property
    def description(self) -> str:
        return f"필드 {self._fields} 조합의 유일성 검사"

    def check(self, data: list[dict]) -> tuple[int, list[QualityViolation]]:
        seen: dict = {}
        violations = []
        for i, row in enumerate(data):
            key = tuple(row.get(f) for f in self._fields)
            if key in seen:
                violations.append(QualityViolation(
                    rule_name=self.rule_name, field=str(self._fields), row_index=i,
                    value=key, message=f"중복 키: {key} (첫 등장: row {seen[key]})",
                ))
            else:
                seen[key] = i
        passed = len(data) - len(violations)
        return max(0, passed), violations


class RangeRule(QualityRule):
    """숫자 범위 검사."""

    def __init__(self, field: str, min_val=None, max_val=None) -> None:
        self._field = field
        self._min_val = min_val
        self._max_val = max_val

    @property
    def rule_name(self) -> str:
        return f"range({self._field},{self._min_val},{self._max_val})"

    @property
    def description(self) -> str:
        return f"필드 '{self._field}' 값이 [{self._min_val}, {self._max_val}] 범위 내"

    def check(self, data: list[dict]) -> tuple[int, list[QualityViolation]]:
        violations = []
        passed = 0
        for i, row in enumerate(data):
            val = row.get(self._field)
            if val is None:
                passed += 1
                continue
            try:
                num = float(val)
            except (TypeError, ValueError):
                violations.append(QualityViolation(
                    rule_name=self.rule_name, field=self._field, row_index=i,
                    value=val, message=f"숫자 변환 불가: {val}",
                ))
                continue
            ok = True
            if self._min_val is not None and num < self._min_val:
                ok = False
                violations.append(QualityViolation(
                    rule_name=self.rule_name, field=self._field, row_index=i,
                    value=num, message=f"{num} < 최솟값 {self._min_val}",
                ))
            if self._max_val is not None and num > self._max_val:
                ok = False
                violations.append(QualityViolation(
                    rule_name=self.rule_name, field=self._field, row_index=i,
                    value=num, message=f"{num} > 최댓값 {self._max_val}",
                ))
            if ok:
                passed += 1
        return passed, violations


class PatternRule(QualityRule):
    """정규식 패턴 검사."""

    def __init__(self, field: str, pattern: str) -> None:
        self._field = field
        self._pattern = pattern
        self._compiled = re.compile(pattern)

    @property
    def rule_name(self) -> str:
        return f"pattern({self._field})"

    @property
    def description(self) -> str:
        return f"필드 '{self._field}' 값이 패턴 '{self._pattern}'과 일치"

    def check(self, data: list[dict]) -> tuple[int, list[QualityViolation]]:
        violations = []
        passed = 0
        for i, row in enumerate(data):
            val = row.get(self._field)
            if val is None:
                passed += 1
                continue
            if self._compiled.search(str(val)):
                passed += 1
            else:
                violations.append(QualityViolation(
                    rule_name=self.rule_name, field=self._field, row_index=i,
                    value=val, message=f"패턴 불일치: '{val}' !~ '{self._pattern}'",
                ))
        return passed, violations


class ReferentialIntegrityRule(QualityRule):
    """참조 무결성 검사."""

    def __init__(self, field: str, valid_values: set) -> None:
        self._field = field
        self._valid_values = valid_values

    @property
    def rule_name(self) -> str:
        return f"referential_integrity({self._field})"

    @property
    def description(self) -> str:
        return f"필드 '{self._field}' 값이 유효 값 집합에 존재"

    def check(self, data: list[dict]) -> tuple[int, list[QualityViolation]]:
        violations = []
        passed = 0
        for i, row in enumerate(data):
            val = row.get(self._field)
            if val in self._valid_values:
                passed += 1
            else:
                violations.append(QualityViolation(
                    rule_name=self.rule_name, field=self._field, row_index=i,
                    value=val, message=f"유효하지 않은 값: {val}",
                ))
        return passed, violations


class FreshnessRule(QualityRule):
    """데이터 신선도 검사."""

    def __init__(self, timestamp_field: str, max_age_hours: int = 24) -> None:
        self._timestamp_field = timestamp_field
        self._max_age_hours = max_age_hours

    @property
    def rule_name(self) -> str:
        return f"freshness({self._timestamp_field},{self._max_age_hours}h)"

    @property
    def description(self) -> str:
        return f"필드 '{self._timestamp_field}' 값이 {self._max_age_hours}시간 이내"

    def check(self, data: list[dict]) -> tuple[int, list[QualityViolation]]:
        violations = []
        passed = 0
        cutoff = datetime.utcnow() - timedelta(hours=self._max_age_hours)

        for i, row in enumerate(data):
            val = row.get(self._timestamp_field)
            if val is None:
                passed += 1
                continue
            try:
                ts_str = str(val)[:19]
                ts = datetime.fromisoformat(ts_str)
                if ts >= cutoff:
                    passed += 1
                else:
                    violations.append(QualityViolation(
                        rule_name=self.rule_name, field=self._timestamp_field, row_index=i,
                        value=val, message=f"데이터가 너무 오래됨: {val}",
                    ))
            except (ValueError, TypeError):
                passed += 1  # 파싱 실패 시 통과
        return passed, violations


class DataQualityChecker:
    """데이터 품질 검사기."""

    def __init__(self) -> None:
        self._rules: dict[str, QualityRule] = {}
        self._reports: list[QualityReport] = []
        self._alerts: list[QualityAlert] = []

    def add_rule(self, rule: QualityRule) -> None:
        self._rules[rule.rule_name] = rule

    def remove_rule(self, rule_name: str) -> bool:
        if rule_name not in self._rules:
            return False
        del self._rules[rule_name]
        return True

    def check(self, data: list[dict], table_name: str) -> QualityReport:
        total = len(data)
        all_violations: list[QualityViolation] = []
        rule_results: dict = {}
        total_passed = 0

        for rule in self._rules.values():
            passed, violations = rule.check(data)
            all_violations.extend(violations)
            rule_results[rule.rule_name] = {
                "passed": passed,
                "violations": len(violations),
                "score": round(passed / max(1, total) * 100, 2),
            }
            total_passed += passed

        if self._rules:
            score = round(total_passed / max(1, len(self._rules) * max(1, total)) * 100, 2)
            score = min(100.0, score)
        else:
            score = 100.0

        failed_rows = len({v.row_index for v in all_violations})
        passed_rows = total - failed_rows

        report = QualityReport(
            table_name=table_name,
            checked_at=datetime.utcnow().isoformat(),
            total_rows=total,
            passed_rows=passed_rows,
            failed_rows=failed_rows,
            score=score,
            violations=all_violations,
            rule_results=rule_results,
        )
        self._reports.append(report)
        return report

    def get_reports(self, table_name: str | None = None) -> list[QualityReport]:
        if table_name is None:
            return list(self._reports)
        return [r for r in self._reports if r.table_name == table_name]

    def check_threshold(self, report: QualityReport, threshold: float = 80.0) -> Optional[QualityAlert]:
        if report.score >= threshold:
            return None
        alert = QualityAlert(
            alert_id=str(uuid.uuid4()),
            table_name=report.table_name,
            report=report,
            threshold=threshold,
            created_at=datetime.utcnow().isoformat(),
        )
        self._alerts.append(alert)
        return alert

    def send_alert(self, alert: QualityAlert) -> bool:
        try:
            from ..notifications.notification_hub import NotificationHub
            hub = NotificationHub()
            msg = (
                f"[데이터 품질 경고] 테이블: {alert.table_name}, "
                f"점수: {alert.report.score:.1f}% (기준: {alert.threshold}%)"
            )
            hub.send(channel="telegram", message=msg)
            return True
        except Exception:
            return False
