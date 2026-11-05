from datetime import date
from types import SimpleNamespace

from myproject.services.schedule import (
    add_months, contract_periods, find_contract_period, month_label
)


def _contract(start=date(2026, 1, 1), months=3, payment_day=15, leaves=None):
    return SimpleNamespace(
        start_date=start,
        duration_months=months,
        payment_day=payment_day,
        academic_leaves=leaves or [],
    )


def _leave(start, end, cancelled_at=None):
    return SimpleNamespace(
        start_date=start, end_date=end, cancelled_at=cancelled_at
    )


def test_add_months_clamps_day_to_month_end():
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2026, 12, 31), 2) == date(2027, 2, 28)


def test_contract_periods_follow_start_date_and_payment_day():
    periods = contract_periods(_contract(months=3, payment_day=10))

    assert [period.month for period in periods] == [
        "2026-01", "2026-02", "2026-03"
    ]
    assert [period.due_date for period in periods] == [
        date(2026, 1, 10), date(2026, 2, 10), date(2026, 3, 10)
    ]


def test_full_leave_month_shifts_following_periods():
    contract = _contract(
        months=3,
        leaves=[_leave(date(2026, 2, 1), date(2026, 2, 28))],
    )

    periods = contract_periods(contract)

    assert [period.month for period in periods] == [
        "2026-01", "2026-03", "2026-04"
    ]


def test_partial_leave_month_does_not_shift_schedule():
    contract = _contract(
        months=3,
        leaves=[_leave(date(2026, 2, 1), date(2026, 2, 20))],
    )

    periods = contract_periods(contract)

    assert [period.month for period in periods] == [
        "2026-01", "2026-02", "2026-03"
    ]


def test_cancelled_leave_is_ignored():
    contract = _contract(
        months=3,
        leaves=[_leave(
            date(2026, 2, 1), date(2026, 2, 28),
            cancelled_at=date(2026, 3, 1)
        )],
    )

    periods = contract_periods(contract)

    assert [period.month for period in periods] == [
        "2026-01", "2026-02", "2026-03"
    ]


def test_find_contract_period_rejects_leave_and_out_of_range_months():
    contract = _contract(
        months=3,
        leaves=[_leave(date(2026, 2, 1), date(2026, 2, 28))],
    )

    assert find_contract_period(contract, "2026-03") is not None
    assert find_contract_period(contract, "2026-02") is None
    assert find_contract_period(contract, "2026-12") is None


def test_month_label_is_zero_padded():
    assert month_label(date(2026, 1, 1)) == "2026-01"
