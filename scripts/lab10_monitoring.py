"""Optional disposable Prometheus + Grafana for lab10_load.py (Linux host network)."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import socket
import tempfile
import threading
import time

import httpx
from testcontainers.core.container import DockerContainer


def port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0)); return sock.getsockname()[1]


@contextmanager
def monitoring(stack, api_port, output):
    directory = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix='sirius-lab10-monitor-')))
    directory.chmod(0o755)
    prom_port, graf_port, exporter_port = port(), port(), port()
    latest = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = '\n'.join(f'lab10_{key} {value}' for key,value in dict(latest).items()).encode()
            self.send_response(200); self.send_header('Content-Type','text/plain; version=0.0.4'); self.end_headers(); self.wfile.write(body)
        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(('127.0.0.1',exporter_port),Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    stack.callback(server.server_close); stack.callback(server.shutdown)
    prom = directory / 'prometheus.yml'
    prom.write_text(f'''global:
  scrape_interval: 2s
scrape_configs:
  - job_name: sirius-lab10-api
    static_configs:
      - targets: ['127.0.0.1:{api_port}']
  - job_name: sirius-lab10-system
    static_configs:
      - targets: ['127.0.0.1:{exporter_port}']
''')
    (directory/'datasources').mkdir(); (directory/'dashboards').mkdir(); (directory/'panels').mkdir()
    (directory/'datasources/local.yml').write_text(f'''apiVersion: 1
datasources:
  - name: Lab10 Prometheus
    uid: lab10-prom
    type: prometheus
    access: proxy
    url: http://127.0.0.1:{prom_port}
    isDefault: true
''')
    (directory/'dashboards/local.yml').write_text('''apiVersion: 1
providers:
  - name: Lab10
    type: file
    options:
      path: /var/lib/grafana/lab10
''')
    specs = [
        ('HTTP RPS', 'sum(rate(http_requests_total[15s]))', 'reqps'),
        ('HTTP p95', 'histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket[15s])))', 's'),
        ('API CPU: 100% = one core', 'lab10_api_cpu_percent', 'percent'),
        ('PostgreSQL active connections (includes sampler)', 'lab10_db_active_connections', 'short'),
        ('Celery pending tasks', 'lab10_celery_pending', 'short'),
        ('HTTP 5xx RPS', 'sum(rate(http_requests_total{status=~"5.."}[15s])) or vector(0)', 'reqps'),
    ]
    dashboard = {'uid':'sirius-lab10','title':'Lab 10 — load and bottlenecks', 'schemaVersion':39,
                 'time':{'from':'now-5m','to':'now'},'refresh':'5s','panels':[
                     {'id':n+1,'type':'timeseries','title':name,'datasource':{'type':'prometheus','uid':'lab10-prom'},
                      'gridPos':{'x':(n%2)*12,'y':(n//2)*8,'w':12,'h':8},
                      'targets':[{'expr':expr,'refId':'A'}],
                      'fieldConfig':{'defaults':{'unit':unit},'overrides':[]}}
                     for n,(name,expr,unit) in enumerate(specs)]}
    (directory/'panels/lab10.json').write_text(json.dumps(dashboard))
    (output/'grafana-dashboard.json').write_text(json.dumps(dashboard,indent=2)+'\n')
    stack.enter_context(DockerContainer('prom/prometheus:v3.5.0').with_kwargs(network_mode='host')
                        .with_volume_mapping(str(prom),'/etc/prometheus/prometheus.yml','ro')
                        .with_command(f'--config.file=/etc/prometheus/prometheus.yml --web.listen-address=127.0.0.1:{prom_port}'))
    stack.enter_context(DockerContainer('grafana/grafana:12.4.0').with_kwargs(network_mode='host')
                        .with_env('GF_SERVER_HTTP_ADDR','127.0.0.1').with_env('GF_SERVER_HTTP_PORT',str(graf_port))
                        .with_env('GF_AUTH_ANONYMOUS_ENABLED','true').with_env('GF_AUTH_ANONYMOUS_ORG_ROLE','Viewer')
                        .with_env('GF_ANALYTICS_REPORTING_ENABLED','false').with_env('GF_ANALYTICS_CHECK_FOR_UPDATES','false')
                        .with_volume_mapping(str(directory/'datasources'),'/etc/grafana/provisioning/datasources','ro')
                        .with_volume_mapping(str(directory/'dashboards'),'/etc/grafana/provisioning/dashboards','ro')
                        .with_volume_mapping(str(directory/'panels'),'/var/lib/grafana/lab10','ro'))
    client = stack.enter_context(httpx.Client(trust_env=False,timeout=10))
    graf_url = f'http://127.0.0.1:{graf_port}'
    for _ in range(100):
        try:
            if client.get(graf_url+'/api/health').status_code == 200: break
        except httpx.HTTPError:
            pass
        time.sleep(.2)
    else:
        raise RuntimeError('Grafana startup timeout')
    print(f'Grafana: {graf_url}/d/sirius-lab10', flush=True)
    yield latest, graf_url, f'http://127.0.0.1:{prom_port}'
