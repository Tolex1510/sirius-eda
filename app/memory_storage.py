"""
Общее in-memory хранилище для репозиториев всех модулей.
Модули ссылаются друг на друга (заказ на пользователя и блюдо),
поэтому таблицы должны быть общими, как в настоящей СУБД.
"""
from dataclasses import dataclass, field
from datetime import date
from itertools import count

from app.domain.entities import (
    Category, DailyOrderStats, Delivery, KitchenTicket, MenuItem, Order, RefreshTokenRecord, User,
)
from app.domain.events import Event, Receipt


@dataclass
class InMemoryStorage:
    users: dict[int, User] = field(default_factory=dict)
    menu_items: dict[int, MenuItem] = field(default_factory=dict)
    categories: dict[int, Category] = field(default_factory=dict)
    orders: dict[int, Order] = field(default_factory=dict)
    deliveries: dict[int, Delivery] = field(default_factory=dict)
    order_stats: dict[date, DailyOrderStats] = field(default_factory=dict)
    refresh_tokens: dict[int, RefreshTokenRecord] = field(default_factory=dict)
    # (provider, subject) -> user_id
    external_accounts: dict[tuple[str, str], int] = field(default_factory=dict)
    kitchen_tickets: dict[int, KitchenTicket] = field(default_factory=dict)
    # Transactional Outbox и Inbox: события к отправке и отметки об обработанных.
    outbox: list[Event] = field(default_factory=list)
    receipts: set[Receipt] = field(default_factory=set)
    _ids: dict[str, count] = field(default_factory=dict)

    def next_id(self, table: str) -> int:
        return next(self._ids.setdefault(table, count(1)))
