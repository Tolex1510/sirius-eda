"""
Консольные команды. Первого администратора нельзя создать через API:
регистрация всегда выдаёт роль student.

    python -m app.cli create-user --email admin@sirius.ru --role admin
    python -m app.cli seed-menu
"""
import argparse
import getpass

from app.dependencies import menu_repository_scope, user_repository_scope
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
