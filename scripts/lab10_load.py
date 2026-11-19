#!/usr/bin/env python3
"""Bounded Locust experiment in disposable PostgreSQL/Redis; no main Compose or AI.

.venv/bin/python scripts/lab10_load.py --seconds 25
All child processes and containers are cleaned up even on failure.
"""
import argparse
import csv
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from contextlib import ExitStack

import httpx
import psutil
from redis import Redis
from sqlalchemy import create_engine, text
from testcontainers.core.container import DockerContainer
from testcontainers.postgres import PostgresContainer

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/lab10/results'
SEED = '''
from sqlalchemy import select
from app.database import SessionLocal
from app.models import Role, User, MenuItem
from app.core.jwt import create_access_token
with SessionLocal.begin() as db:
    role = db.scalar(select(Role).where(Role.name=='student'))
    for n in range(48):
        db.add(MenuItem(name=f"Load fixture {n}",price=100,is_available=True))
    for n in range(200):
        u=User(email=f"lab10-{n}@isolated.test",balance=10000000,role_id=role.id)
        db.add(u); db.flush()
        print(create_access_token(u.id))
'''


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def stop(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill(); process.wait()


def main():
    global OUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=int, default=25)
    parser.add_argument('--monitoring', action='store_true', help='Start disposable Grafana/Prometheus (Linux)')
    parser.add_argument('--out', type=Path, default=OUT)
    parser.add_argument('--only-200', action='store_true', help='Two short comparison runs instead of four')
    args = parser.parse_args()
    global_output = args.out.resolve()
    if args.seconds < 15 or args.seconds > 180:
        parser.error('--seconds must be between 15 and 180')
    os.chdir(ROOT)
    OUT = global_output
    OUT.mkdir(parents=True, exist_ok=True)
    with ExitStack() as stack:
        pg = stack.enter_context(PostgresContainer('pgvector/pgvector:pg16'))
        redis_container = stack.enter_context(DockerContainer('redis:7-alpine').with_exposed_ports(6379))
        redis_url = f'redis://{redis_container.get_container_host_ip()}:{redis_container.get_exposed_port(6379)}/0'
        redis = Redis.from_url(redis_url)
        for _ in range(50):
            try:
                if redis.ping(): break
            except Exception:
                time.sleep(.1)
        env = dict(os.environ, DATABASE_URL=pg.get_connection_url(), REPOSITORY_BACKEND='postgres',
                   SECRET_KEY='lab10-disposable-fixture-secret-more-than-32-characters',
                   REDIS_URL=redis_url, MENU_CACHE_ENABLED='true', DELIVERY_BACKEND='local',
                   SENTRY_DSN='', OTEL_EXPORTER_OTLP_ENDPOINT='', PAYMENT_PROVIDER='demo',
                   FAKE_EMAIL_FAIL_EVERY='0', FAKE_SMS_FLAKY_EVERY='0', BCRYPT_ROUNDS='4',
                   ACCESS_TOKEN_TTL_MINUTES='60', OLLAMA_URL='http://127.0.0.1:1', DEBUG='false')
        subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'], env=env, check=True,
                       stdout=subprocess.DEVNULL)
        temporary = stack.enter_context(tempfile.TemporaryDirectory(prefix='sirius-lab10-'))
        token_path = Path(temporary) / 'tokens'
        token_path.touch(mode=0o600)
        with token_path.open('w') as tokens:
            subprocess.run([sys.executable, '-c', SEED], env=env, stdout=tokens, check=True)
        engine = create_engine(pg.get_connection_url())
        stack.callback(engine.dispose)
        all_results = []
        api_port = free_port()
        monitor = None
        if args.monitoring:
            from lab10_monitoring import monitoring
            monitor = stack.enter_context(monitoring(stack, api_port, OUT))
        cases = [('sync', 200), ('celery', 200)] if args.only_200 else [('sync', 50), ('sync', 200), ('celery', 50), ('celery', 200)]
        for mode, users in cases:
            label = f'{mode}-{users}'
            print(f'Starting {label}: {args.seconds}s', flush=True)
            run_env = dict(env, ORDER_TASKS_MODE=mode, LOCUST_TOKENS=str(token_path))
            port = api_port; host = f'http://127.0.0.1:{port}'
            samples = []
            with ExitStack() as run:
                log = run.enter_context((OUT / f'{label}-api.log').open('w'))
                api = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1',
                                        '--port', str(port), '--no-access-log', '--log-level', 'warning'],
                                       env=run_env, stdout=log, stderr=log)
                run.callback(stop, api)
                if mode == 'celery':
                    worker_log = run.enter_context((OUT / f'{label}-worker.log').open('w'))
                    worker = subprocess.Popen([sys.executable, '-m', 'celery', '-A', 'app.core.celery_app',
                                               'worker', '--pool', 'threads', '--concurrency', '16',
                                               '--loglevel', 'warning', '--without-gossip', '--without-mingle'],
                                              env=run_env, stdout=worker_log, stderr=worker_log)
                    run.callback(stop, worker)
                with httpx.Client(trust_env=False, timeout=5) as client:
                    for _ in range(100):
                        if api.poll() is not None:
                            raise RuntimeError(f'{label}: API stopped, see {log.name}')
                        try:
                            if client.get(host + '/health').status_code == 200: break
                        except httpx.HTTPError:
                            pass
                        time.sleep(.1)
                    else:
                        raise RuntimeError('API readiness timeout')
                    before = client.get(host + '/metrics').text
                    (OUT / f'{label}-metrics-before.prom').write_text(before)
                    locust_log = run.enter_context((OUT / f'{label}-locust.log').open('w'))
                    load = subprocess.Popen([sys.executable, '-m', 'locust', '-f', 'locustfile_lab10.py',
                                             '--host', host, '--headless', '-u', str(users), '-r', '50',
                                             '-t', f'{args.seconds}s', '--stop-timeout', '10',
                                             '--csv', str(OUT / label), '--csv-full-history',
                                             '--html', str(OUT / f'{label}.html'), '--only-summary'],
                                            env=run_env, stdout=locust_log, stderr=locust_log)
                    run.callback(stop, load)
                    process = psutil.Process(api.pid); process.cpu_percent()
                    deadline = time.monotonic() + args.seconds + 30
                    while load.poll() is None:
                        if time.monotonic() > deadline:
                            raise RuntimeError('Locust exceeded bounded run time')
                        with engine.connect() as db:
                            active = db.scalar(text("select count(*) from pg_stat_activity where datname=current_database() and state='active'"))
                        samples.append({'time':time.time(), 'api_cpu_percent':process.cpu_percent(),
                                        'api_rss_mib':round(process.memory_info().rss/2**20, 1),
                                        'db_active_connections':active, 'celery_pending':redis.llen('default')})
                        if monitor:
                            monitor[0].update({key:value for key,value in samples[-1].items() if key != 'time'})
                        time.sleep(2)
                    if load.returncode:
                        raise RuntimeError(f'Locust failed for {label}: see {locust_log.name}')
                    (OUT / f'{label}-metrics-after.prom').write_text(client.get(host + '/metrics').text)
            (OUT / f'{label}-system.json').write_text(json.dumps(samples, indent=2)+'\n')
            with (OUT / f'{label}_stats.csv').open() as f:
                stats = list(csv.DictReader(f))
            aggregate = next(row for row in stats if row['Name'] == 'Aggregated')
            result = {'label':label, 'users':users, 'notifier':mode, 'duration_seconds':args.seconds,
                      'requests':int(aggregate['Request Count']), 'failures':int(aggregate['Failure Count']),
                      'rps':float(aggregate['Requests/s']), 'p95_ms':float(aggregate['95%']),
                      'max_api_cpu_percent':max(s['api_cpu_percent'] for s in samples),
                      'max_db_active_connections':max(s['db_active_connections'] for s in samples),
                      'max_celery_pending':max(s['celery_pending'] for s in samples),
                      'end_celery_pending':samples[-1]['celery_pending'],
                      'endpoints':stats[:-1]}
            all_results.append(result)
            (OUT / 'load-summary.json').write_text(json.dumps(all_results, ensure_ascii=False, indent=2)+'\n')
            print(json.dumps({k:v for k,v in result.items() if k!='endpoints'}), flush=True)
            # These are disposable fixtures; clear queued background work before the next measurement.
            redis.flushdb()
        if monitor:
            _, graf_url, prom_url = monitor
            with httpx.Client(trust_env=False, timeout=10) as client:
                queries = {'cpu':'max_over_time(lab10_api_cpu_percent[5m])', 'queue':'max_over_time(lab10_celery_pending[5m])', 'p95':'histogram_quantile(0.95, sum by(le) (rate(http_request_duration_seconds_bucket[30s])))'}
                snapshot = {name:client.get(prom_url+'/api/v1/query',params={'query':query}).json() for name,query in queries.items()}
                (OUT/'prometheus-evidence.json').write_text(json.dumps(snapshot,indent=2)+'\n')
            script = ROOT/'scripts/lab10_grafana.cjs'
            subprocess.run(['node',str(script),graf_url,str(OUT/'grafana.png')],check=True,timeout=45)
        print('Disposable processes and containers will now stop.', flush=True)


if __name__ == '__main__':
    main()
