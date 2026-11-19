"""Real PostgreSQL, migrations and per-test cleanup; never uses application DATABASE_URL."""
import os
import subprocess
import sys

import fakeredis
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from testcontainers.postgres import PostgresContainer


@pytest.fixture(scope="session")
def postgres_engine():
    with PostgresContainer("pgvector/pgvector:pg16") as postgres:
        url = postgres.get_connection_url()
        env = dict(os.environ, DATABASE_URL=url, REPOSITORY_BACKEND="postgres",
                   SECRET_KEY="lab10-isolated-test-secret-at-least-32-characters",
                   SENTRY_DSN="", OTEL_EXPORTER_OTLP_ENDPOINT="")
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], env=env, check=True)
        engine = create_engine(url, pool_pre_ping=True)
        try:
            yield engine
        finally:
            engine.dispose()


@pytest.fixture
def sql_sessions(postgres_engine):
    from app.database import Base
    from app import models  # register all tables
    tables = ', '.join('"' + t.name + '"' for t in Base.metadata.sorted_tables)

    def clean():
        with postgres_engine.begin() as connection:
            connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))

    clean()
    sessions = sessionmaker(bind=postgres_engine)
    with sessions.begin() as db:
        db.add_all(models.Role(name=r) for r in ("student", "cook", "courier", "admin"))
    try:
        yield sessions
    finally:
        clean()


@pytest.fixture
def sql_client(sql_sessions):
    from fastapi.testclient import TestClient
    from app import dependencies as dep
    from app.core.rate_limit import get_redis
    from app.main import app
    from app.modules.auth.repository import SqlAlchemyAuthRepository
    from app.modules.menu.repository import SqlAlchemyMenuRepository
    from app.modules.orders.repository import SqlAlchemyOrderRepository
    from app.modules.users.repository import SqlAlchemyUserRepository
    from tests.conftest import RecordingNotifier

    def provider(cls):
        def dependency():
            with sql_sessions() as db:
                yield cls(db)
        return dependency

    old = app.dependency_overrides.copy()
    app.dependency_overrides.update({
        dep.get_auth_repository: provider(SqlAlchemyAuthRepository),
        dep.get_user_repository: provider(SqlAlchemyUserRepository),
        dep.get_order_repository: provider(SqlAlchemyOrderRepository),
        dep.get_menu_repository: provider(SqlAlchemyMenuRepository),
        dep.get_order_notifier: lambda: RecordingNotifier(),
        get_redis: lambda: fakeredis.FakeRedis(),
    })
    # Without lifespan: global application pools must never warm the developer DB.
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides = old


@pytest.fixture
def account(sql_sessions):
    from app.core.jwt import create_access_token
    from app.models import MenuItem, Role, User
    from sqlalchemy import select
    with sql_sessions.begin() as db:
        role = db.scalar(select(Role).where(Role.name == "student"))
        user = User(email="integration@sirius.test", balance=1000, role_id=role.id)
        item = MenuItem(name="Сырники", price=150, is_available=True)
        db.add_all([user, item]); db.flush()
        return user.id, item.id, {"Authorization": "Bearer " + create_access_token(user.id)}
