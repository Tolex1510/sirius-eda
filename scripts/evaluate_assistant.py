"""Run the track F questionnaire through the real authenticated HTTP endpoint.

The token is generated inside the local API container and is never saved or printed.
Every question starts its own conversation. Reviews must be completed by a human.
"""
import argparse
import json
import math
from pathlib import Path
import statistics
import subprocess
import time
from datetime import datetime, UTC
from urllib.request import Request, urlopen
from urllib.error import HTTPError


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--email', default='lab9@demo.sirius.ru')
    parser.add_argument('--project', default='sirius-eda')
    parser.add_argument('--base-url', default='http://localhost:8080/api')
    parser.add_argument('--questions', default='docs/study/AI_EVAL.json')
    parser.add_argument('--output', default='docs/study/results/ai-eval-live.json')
    parser.add_argument('--interval', type=float, default=6.4)
    args = parser.parse_args()
    code = '''import json
from app.database import SessionLocal
from app.models import User
from app.core.jwt import create_access_token
from app.core.config import settings
with SessionLocal() as db:
 u=db.query(User).filter_by(email=EMAIL).one()
 print(json.dumps({'token':create_access_token(u.id),'user_id':u.id,'model':settings.OLLAMA_MODEL,'embedding_model':settings.OLLAMA_EMBED_MODEL}))
'''.replace('EMAIL', repr(args.email))
    auth = subprocess.run(['docker','compose','-p',args.project,'exec','-T','api','python','-c',code], check=True,capture_output=True,text=True)
    metadata = json.loads(auth.stdout.strip().splitlines()[-1])
    token = metadata.pop('token')
    questions = json.loads(Path(args.questions).read_text())
    output = Path(args.output);output.parent.mkdir(parents=True,exist_ok=True)
    report = {'started_utc':datetime.now(UTC).isoformat(), **metadata, 'independent_conversations':True,'results':[]}
    next_start = time.monotonic()
    for case in questions:
        time.sleep(max(0,next_start-time.monotonic()))
        start = time.monotonic();next_start=start+args.interval
        req=Request(args.base_url+'/assistant/messages',data=json.dumps({'message':case['question']}).encode(),headers={'Authorization':'Bearer '+token,'Content-Type':'application/json','X-Correlation-ID':f'track-f-eval-{case["id"]}'})
        row={'id':case['id'],'question':case['question'],'expected':case['expected'],'review':None}
        try:
            with urlopen(req,timeout=210) as response:
                data=json.load(response);row.update({'http_status':response.status,'answer':data['answer'],'mode':data.get('mode'),'available':data['available'],'sources':data['sources'],'latency_ms':round((time.monotonic()-start)*1000,2)})
        except HTTPError as error:
            row.update({'http_status':error.code,'error':error.read().decode()[:400],'latency_ms':round((time.monotonic()-start)*1000,2)})
        except Exception as error:
            row.update({'http_status':0,'error':type(error).__name__,'latency_ms':round((time.monotonic()-start)*1000,2)})
        report['results'].append(row)
        output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        print(f"{case['id']:02d}/{len(questions)} HTTP {row['http_status']} mode={row.get('mode')} {row['latency_ms']}ms",flush=True)
    values=sorted(r['latency_ms'] for r in report['results'])
    report['finished_utc']=datetime.now(UTC).isoformat()
    report['latency_ms']={'median':round(statistics.median(values),2),'p95':values[max(0,math.ceil(len(values)*.95)-1)],'max':max(values)}
    report['mode_counts']={mode:sum(r.get('mode','error')==mode for r in report['results']) for mode in sorted({r.get('mode','error') for r in report['results']})}
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'completed':len(values),'latency_ms':report['latency_ms'],'mode_counts':report['mode_counts']},ensure_ascii=False))

if __name__=='__main__': main()
