"""Опциональная проверка настоящего pgvector; URL должен указывать на отдельную тестовую БД."""
import os
from uuid import uuid4
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.models import MenuItem
from app.modules.assistant.repository import SqlAssistantRepository


@pytest.mark.skipif(not os.getenv('ASSISTANT_PGVECTOR_URL'), reason='Требуется отдельная PostgreSQL/pgvector БД')
def test_public_index_round_trip_and_current_price():
    engine = create_engine(os.environ['ASSISTANT_PGVECTOR_URL'])
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    title = 'Vector test ' + uuid4().hex
    with sessions.begin() as db:
        row = MenuItem(name=title, price=100, is_available=True)
        db.add(row); db.flush(); item_id = row.id
    repo = SqlAssistantRepository(sessions, 'deterministic-qa-1024')

    class Model:
        def embed(self, texts):
            # Изолированная проверка механики pgvector. Это не качество AI-модели.
            return [[1.0 if n == (0 if title in text else 1) else 0.0 for n in range(1024)] for text in texts]

    model = Model()
    assert repo.index(model) > 0
    assert repo.index(model) == 0
    with sessions.begin() as db:
        db.get(MenuItem, item_id).price = 175
    sources = repo.search(model.embed([title])[0])
    assert sources[0].id == f'menu-{item_id}'
    # Retrieval uses the current price even before the next indexing pass.
    assert '175.00 RUB' in sources[0].text
    with sessions.begin() as db:
        db.delete(db.get(MenuItem, item_id))
    repo.index(model)
    assert f'menu-{item_id}' not in {s.id for s in repo.search(model.embed([title])[0])}
    engine.dispose()
