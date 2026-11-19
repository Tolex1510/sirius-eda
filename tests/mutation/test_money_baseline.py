"""Deliberately weak starting point; kept to reproduce the before measurement."""
from decimal import Decimal
from app.domain.money import money


def test_whole_rubles():
    assert money('100') == Decimal('100.00')
