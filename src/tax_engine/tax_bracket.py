"""금액 구간별 세율 적용."""
from __future__ import annotations

class TaxBracket:
    def __init__(self) -> None:
        # (max_amount, rate) - sorted by max_amount ascending
        self._brackets: list[tuple[float, float]] = []

    def add_bracket(self, max_amount: float, rate: float) -> None:
        self._brackets.append((max_amount, rate))
        self._brackets.sort(key=lambda x: x[0])

    def get_rate(self, amount: float) -> float:
        for max_amt, rate in self._brackets:
            if amount <= max_amt:
                return rate
        return self._brackets[-1][1] if self._brackets else 0.0

    def calculate(self, amount: float) -> dict:
        rate = self.get_rate(amount)
        tax = round(amount * rate, 2)
        return {"amount": amount, "rate": rate, "tax": tax}
