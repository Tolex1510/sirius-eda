"""Boundary checks added after inspecting surviving money mutations."""
from decimal import Decimal
import pytest
from app.domain.money import money


@pytest.mark.parametrize('value,expected', [('1.005','1.01'), ('-1.005','-1.01'), ('0.004','0.00'), ('123.456','123.46')])
def test_rounds_half_up_to_kopecks(value, expected):
    assert money(value) == Decimal(expected)


@pytest.mark.parametrize('value', ['NaN', 'Infinity', '-Infinity', None, 'not-money'])
def test_rejects_non_finite_and_invalid_amounts(value):
    with pytest.raises(ValueError):
        money(value)
