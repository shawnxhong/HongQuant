from __future__ import annotations

from datetime import date

from hongquant.options.expiries import (
    expiries_within,
    front_friday,
    is_opex_week,
    is_triple_witching_week,
    monthly_opex,
    next_friday,
    triple_witching,
)


def test_front_friday_on_monday():
    assert front_friday(date(2025, 5, 5)) == date(2025, 5, 9)  # Mon → Fri


def test_front_friday_on_friday():
    assert front_friday(date(2025, 5, 9)) == date(2025, 5, 9)  # Fri → same day


def test_front_friday_on_saturday():
    assert front_friday(date(2025, 5, 10)) == date(2025, 5, 16)  # Sat → next Fri


def test_front_friday_on_wednesday():
    assert front_friday(date(2025, 5, 7)) == date(2025, 5, 9)  # Wed → Fri


def test_next_friday():
    assert next_friday(date(2025, 5, 5)) == date(2025, 5, 16)


def test_next_friday_from_friday():
    assert next_friday(date(2025, 5, 9)) == date(2025, 5, 16)


def test_monthly_opex_jan_2025():
    # Third Friday of Jan 2025 = Jan 17
    assert monthly_opex(2025, 1) == date(2025, 1, 17)


def test_monthly_opex_mar_2025():
    # Third Friday of Mar 2025 = Mar 21
    assert monthly_opex(2025, 3) == date(2025, 3, 21)


def test_monthly_opex_dec_2025():
    # Third Friday of Dec 2025 = Dec 19
    assert monthly_opex(2025, 12) == date(2025, 12, 19)


def test_triple_witching_q1_2025():
    assert triple_witching(2025, 1) == monthly_opex(2025, 3)


def test_triple_witching_q2_2025():
    assert triple_witching(2025, 2) == monthly_opex(2025, 6)


def test_triple_witching_q3_2026():
    assert triple_witching(2026, 3) == monthly_opex(2026, 9)


def test_expiries_within():
    exps = expiries_within(date(2025, 5, 5), 21)
    assert date(2025, 5, 9) in exps
    assert date(2025, 5, 16) in exps
    assert date(2025, 5, 23) in exps
    assert date(2025, 5, 30) not in exps  # >21 days from May 5


def test_is_opex_week_true():
    # Third Friday of May 2025 = May 16; so May 12-16 is opex week
    assert is_opex_week(date(2025, 5, 12))


def test_is_opex_week_false():
    # May 23 is the 4th Friday of May 2025, not monthly opex
    assert not is_opex_week(date(2025, 5, 19))


def test_is_triple_witching():
    # Q1 2025 triple witching = Mar 21; week of Mar 17-21
    assert is_triple_witching_week(date(2025, 3, 17))
    assert not is_triple_witching_week(date(2025, 3, 24))
