"""
Консольные команды. Первого администратора нельзя создать через API:
регистрация всегда выдаёт роль student.

    python -m app.cli create-user --email admin@sirius.ru --role admin
    python -m app.cli seed-menu
    python -m app.cli load-users --count 50 > tokens.txt
    python -m app.cli dlq-list
    python -m app.cli dlq-replay
    python -m app.cli track-delivery --delivery-id 1 --user-id 2
    python -m app.cli delivery-chat --delivery-id 1 --user-id 2
"""
import argparse
from datetime import datetime
import getpass
import secrets
import sys

from app.core.jwt import create_access_token

from app.dependencies import menu_repository_scope, user_repository_scope
from app.domain.entities import Role, User
from app.domain.exceptions import DomainError
from app.modules.menu.service import MenuService
from app.modules.users.service import UserService

SEED_CATEGORIES = (
    "Завтраки", "Салаты", "Супы", "Горячее", "Гарниры", "Паста",
    "Пицца", "Вок", "Гриль", "Выпечка", "Десерты", "Напитки",
)


def create_user(email: str, role: str) -> None:
    password = getpass.getpass("Пароль: ")
    with user_repository_scope() as repository:
        try:
            user = UserService(repository).register(email=email, password=password, role=role)
        except DomainError as e:
            raise SystemExit(f"Ошибка: {e}")
    print(f"Создан пользователь {user.id} {user.email} с ролью {user.role}")


def seed_menu(items_per_category: int) -> None:
    """Тестовое меню для нагрузочных замеров. Повторный запуск ничего не дублирует."""
    created = 0
    with menu_repository_scope() as repository:
        service = MenuService(repository)
        for index, name in enumerate(SEED_CATEGORIES):
            category = repository.get_category_by_name(name) or service.create_category(name)
            for number in range(1, items_per_category + 1):
                item_name = f"{name} №{number}"
                if not repository.get_by_name(item_name):
                    service.create_item(item_name, price=90 + index * 15 + number * 5, category_id=category.id)
                    created += 1
    print(f"Добавлено блюд: {created}")


def load_users(count: int) -> None:
    """Студенты для нагрузочных замеров заказов. Печатает access-токены по одному в строке.
    Логин через API не подходит: rate limiting пустит только 5 входов в минуту с одного IP."""
    with user_repository_scope() as repository:
        service = UserService(repository)
        for number in range(1, count + 1):
            email = f"load{number}@sirius.test"
            user = repository.get_by_email(email) or service.register(
                email=email, password=secrets.token_urlsafe(16), phone=f"+7900{number:07d}"
            )
            repository.update_balance(user.id, 10_000_000)
            print(create_access_token(user.id))


def dlq_list() -> None:
    from app.tasks.dead_letters import list_dead_letters

    letters = list_dead_letters()
    for letter in letters:
        print(f"{letter['failed_at']}  {letter['task']}{letter['args']}  {letter['error']}")
    print(f"В DLQ задач: {len(letters)}")


def dlq_replay() -> None:
    from app.tasks.dead_letters import replay_dead_letters

    print(f"Возвращено в очередь: {replay_dead_letters()}")


def load_user(user_id: int) -> User:
    with user_repository_scope() as repository:
        user = repository.get_by_id(user_id)
    if not user:
        raise SystemExit(f"Пользователь {user_id} не найден")
    return user


def track_delivery(delivery_id: int, user_id: int) -> None:
    """Подписка на Server Streaming TrackDelivery микросервиса доставки."""
    from app.modules.delivery.gateway import DeliveryUnavailableError
    from app.modules.delivery.grpc_client import delivery_grpc_gateway

    try:
        for delivery in delivery_grpc_gateway().track(delivery_id, load_user(user_id)):
            print(f"{datetime.now():%H:%M:%S}  доставка {delivery.id}: {delivery.status}", flush=True)
    except (DomainError, DeliveryUnavailableError) as e:
        raise SystemExit(f"Ошибка: {e}")


def delivery_chat(delivery_id: int, user_id: int) -> None:
    """Bidirectional Streaming ChatWithCourier: строки из stdin уходят в чат, ответы печатаются сразу."""
    from app.modules.delivery.gateway import DeliveryUnavailableError
    from app.modules.delivery.grpc_client import delivery_grpc_gateway

    user = load_user(user_id)
    print(f"Чат доставки {delivery_id}, вы {user.email} ({user.role}). Enter отправляет, Ctrl+D выходит.", flush=True)
    outgoing = (line.rstrip("\n") for line in sys.stdin)
    try:
        for message in delivery_grpc_gateway().chat(delivery_id, user, outgoing):
            who = "вы" if message.author_id == user.id else f"{message.author_role} {message.author_id}"
            print(f"[{message.sent_at.astimezone():%H:%M:%S}] {who}: {message.text}", flush=True)
    except (DomainError, DeliveryUnavailableError) as e:
        raise SystemExit(f"Ошибка: {e}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create-user", help="создать пользователя с любой ролью")
    create.add_argument("--email", required=True)
    create.add_argument("--role", choices=Role.ALL, default=Role.STUDENT)
    seed = commands.add_parser("seed-menu", help="заполнить меню тестовыми блюдами")
    seed.add_argument("--items-per-category", type=int, default=25)
    load = commands.add_parser("load-users", help="студенты с балансом для замеров, печатает токены")
    load.add_argument("--count", type=int, default=50)
    commands.add_parser("dlq-list", help="задачи в Dead Letter Queue")
    commands.add_parser("dlq-replay", help="вернуть задачи из DLQ в рабочую очередь")
    for name, help_text in (("track-delivery", "следить за статусом доставки через gRPC-стрим"),
                            ("delivery-chat", "чат заказчика и курьера через gRPC")):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("--delivery-id", type=int, required=True)
        command.add_argument("--user-id", type=int, required=True, help="от чьего имени")

    args = parser.parse_args()
    if args.command == "create-user":
        create_user(args.email, args.role)
    elif args.command == "seed-menu":
        seed_menu(args.items_per_category)
    elif args.command == "load-users":
        load_users(args.count)
    elif args.command == "dlq-list":
        dlq_list()
    elif args.command == "dlq-replay":
        dlq_replay()
    elif args.command == "track-delivery":
        track_delivery(args.delivery_id, args.user_id)
    elif args.command == "delivery-chat":
        delivery_chat(args.delivery_id, args.user_id)


if __name__ == "__main__":
    main()
