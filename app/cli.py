"""
Консольные команды. Первого администратора нельзя создать через API:
регистрация всегда выдаёт роль student.

    python -m app.cli create-user --email admin@sirius.ru --role admin
    python -m app.cli seed-menu
"""
import argparse
import getpass

from app.dependencies import get_menu_repository, get_user_repository
from app.domain.entities import Role
from app.domain.exceptions import DomainError
from app.modules.menu.service import MenuService
from app.modules.users.service import UserService

SEED_CATEGORIES = (
    "Завтраки", "Салаты", "Супы", "Горячее", "Гарниры", "Паста",
    "Пицца", "Вок", "Гриль", "Выпечка", "Десерты", "Напитки",
)


def create_user(email: str, role: str) -> None:
    password = getpass.getpass("Пароль: ")
    repository_provider = get_user_repository()
    service = UserService(next(repository_provider))
    try:
        user = service.register(email=email, password=password, role=role)
    except DomainError as e:
        raise SystemExit(f"Ошибка: {e}")
    finally:
        repository_provider.close()
    print(f"Создан пользователь {user.id} {user.email} с ролью {user.role}")


def seed_menu(items_per_category: int) -> None:
    """Тестовое меню для нагрузочных замеров. Повторный запуск ничего не дублирует."""
    repository_provider = get_menu_repository()
    service = MenuService(next(repository_provider))
    created = 0
    try:
        for index, name in enumerate(SEED_CATEGORIES):
            category = service.repository.get_category_by_name(name) or service.create_category(name)
            for number in range(1, items_per_category + 1):
                item_name = f"{name} №{number}"
                if not service.repository.get_by_name(item_name):
                    service.create_item(item_name, price=90 + index * 15 + number * 5, category_id=category.id)
                    created += 1
    finally:
        repository_provider.close()
    print(f"Добавлено блюд: {created}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create-user", help="создать пользователя с любой ролью")
    create.add_argument("--email", required=True)
    create.add_argument("--role", choices=Role.ALL, default=Role.STUDENT)
    seed = commands.add_parser("seed-menu", help="заполнить меню тестовыми блюдами")
    seed.add_argument("--items-per-category", type=int, default=25)

    args = parser.parse_args()
    if args.command == "create-user":
        create_user(args.email, args.role)
    elif args.command == "seed-menu":
        seed_menu(args.items_per_category)


if __name__ == "__main__":
    main()
