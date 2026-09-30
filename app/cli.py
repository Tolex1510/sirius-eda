"""
Консольные команды. Первого администратора нельзя создать через API:
регистрация всегда выдаёт роль student.

    python -m app.cli create-user --email admin@sirius.ru --role admin
"""
import argparse
import getpass

from app.dependencies import get_user_repository
from app.domain.entities import Role
from app.domain.exceptions import DomainError
from app.modules.users.service import UserService


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


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create-user", help="создать пользователя с любой ролью")
    create.add_argument("--email", required=True)
    create.add_argument("--role", choices=Role.ALL, default=Role.STUDENT)

    args = parser.parse_args()
    if args.command == "create-user":
        create_user(args.email, args.role)


if __name__ == "__main__":
    main()
