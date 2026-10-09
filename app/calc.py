"""Commission calculation for plan RET-Q4-2026 (requirements 3.3)."""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

GATE = Decimal("0.50")

# (name, lower, upper, rate) with lower/upper as a share of quota
BANDS = [
    ("A", Decimal("0.00"), Decimal("0.80"), Decimal("0.010")),
    ("B", Decimal("0.80"), Decimal("1.00"), Decimal("0.025")),
    ("C", Decimal("1.00"), Decimal("1.50"), Decimal("0.040")),
    ("D", Decimal("1.50"), Decimal("2.00"), Decimal("0.050")),
]

CENT = Decimal("0.01")


@dataclass
class BandResult:
    band: str
    lower_pct: Decimal
    upper_pct: Decimal
    rate_pct: Decimal
    base: Decimal
    commission: Decimal


@dataclass
class CalcResult:
    quota: Decimal
    credited: Decimal
    attainment: Decimal
    attainment_pct: Decimal
    qualified: bool
    bands: list
    payout: Decimal


def calculate(credited_cents: int, quota_cents: int) -> CalcResult:
    quota = Decimal(quota_cents) / 100
    credited = Decimal(credited_cents) / 100
    attainment = credited / quota
    # BUG-006: display rounding is half-up (ties away from zero), REQ-CAL-06
    attainment_pct = (attainment * 100).quantize(CENT, rounding=ROUND_HALF_UP)
    # BUG-002: the gate uses the exact attainment, never the rounded display value
    qualified = attainment >= GATE

    bands = []
    total = Decimal("0")
    for name, lower, upper, rate in BANDS:
        base = min(credited, upper * quota) - lower * quota
        if base < 0:
            base = Decimal("0")
        commission = base * rate
        bands.append(BandResult(name, lower * 100, upper * 100, rate * 100, base, commission))
        total += commission

    # BUG-003: round once, half-up (Decimal's default context is half-even)
    payout = total.quantize(CENT, rounding=ROUND_HALF_UP) if qualified else Decimal("0.00")
    if payout < 0:
        payout = Decimal("0.00")
    return CalcResult(quota, credited, attainment, attainment_pct, qualified, bands, payout)


def display(value: Decimal) -> str:
    """Two-decimal display, half-up (REQ-STM-03)."""
    return f"{value.quantize(CENT, rounding=ROUND_HALF_UP):.2f}"
