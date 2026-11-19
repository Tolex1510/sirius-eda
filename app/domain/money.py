"""Денежные значения: рубли, две цифры после запятой, без арифметики Float."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def money(value) -> Decimal:
    try:
        result = Decimal(str(value))
        if not result.is_finite():
            raise ValueError("Сумма должна быть конечным числом")
        return result.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError):
        raise ValueError("Некорректная сумма")
