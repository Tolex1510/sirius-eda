"""Check the full Alembic cycle against a disposable pgvector PostgreSQL."""
import os
import subprocess
import sys
from testcontainers.postgres import PostgresContainer

with PostgresContainer('pgvector/pgvector:pg16') as pg:
    env = dict(os.environ, DATABASE_URL=pg.get_connection_url(),
               SECRET_KEY='lab10-migration-check-more-than-32-characters',
               SENTRY_DSN='', OTEL_EXPORTER_OTLP_ENDPOINT='')
    for args in [('upgrade','head'), ('check',), ('downgrade','base'), ('upgrade','head'), ('check',)]:
        print('alembic',*args,flush=True)
        subprocess.run([sys.executable,'-m','alembic',*args],env=env,check=True)
