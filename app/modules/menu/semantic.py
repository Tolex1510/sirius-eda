"""Semantic menu retrieval: embeddings for ranking, current DB rows for facts and eligibility."""
from hashlib import sha256
from redis import Redis
from sqlalchemy import String, cast, select
from app.core.config import settings
from app.database import SessionLocal
from app.models import Category, KnowledgeChunk, MenuItem
from app.modules.assistant.contracts import ModelUnavailable
from app.modules.assistant.router import assistant_service
from app.modules.menu.filters import eligible, explanation


def search_menu(query: str, limit: int=8):
    normalized=' '.join(query.lower().split())
    service=assistant_service()
    key='assistant:embedding:'+sha256((settings.OLLAMA_EMBED_MODEL+':'+normalized).encode()).hexdigest()
    cache=Redis.from_url(settings.REDIS_URL, socket_connect_timeout=1, socket_timeout=1)
    vector=None
    try:
        import json
        saved=cache.get(key)
        if saved: vector=json.loads(saved)
    except Exception:
        pass
    if vector is None:
        try:
            [vector]=service.model.embed([normalized])
        except ModelUnavailable:
            return lexical_fallback(normalized,limit)
        try:
            import json
            cache.setex(key,300,json.dumps(vector))
        except Exception:
            pass
    with SessionLocal() as db:
        distance=KnowledgeChunk.embedding.cosine_distance(vector)
        rows=db.execute(select(MenuItem,distance.label('distance'))
            .join(KnowledgeChunk,KnowledgeChunk.id=='menu-'+cast(MenuItem.id,String))
            .where(KnowledgeChunk.embedding_model==settings.OLLAMA_EMBED_MODEL,
                   MenuItem.is_archived.is_(False),MenuItem.is_available.is_(True))
            .order_by(distance,MenuItem.id).limit(100)).all()
        if not rows:
            db.rollback()
            return lexical_fallback(normalized,limit)
        categories=dict(db.execute(select(Category.id,Category.name)).all())
        import re
        stems={w[:4] for w in re.findall(r"[а-яёa-z]{3,}",normalized)}
        def rank(pair):
            item,distance=pair
            text=(item.name+' '+(item.description or '')+' '+' '.join(item.ingredients or [])).lower()
            words={w[:4] for w in re.findall(r"[а-яёa-z]{3,}",text)}
            return distance-0.025*len(stems & words),distance,item.id
        ranked=sorted(rows,key=rank)
        items=[row.to_entity() for row,d in ranked if d <= 0.65 and eligible(row,normalized,categories.get(row.category_id))][:limit]
        return {'items':items,'mode':'semantic','explanation':explanation(normalized)}


def lexical_fallback(query,limit):
    with SessionLocal() as db:
        words=query.split()
        categories=dict(db.execute(select(Category.id,Category.name)).all())
        rows=db.scalars(select(MenuItem).where(MenuItem.is_archived.is_(False),MenuItem.is_available.is_(True)).order_by(MenuItem.id))
        items=[r.to_entity() for r in rows if eligible(r,query,categories.get(r.category_id)) and all(w in (r.name+' '+r.description+' '+' '.join(r.ingredients or [])).lower() for w in words)]
        return {'items':items[:limit],'mode':'keyword','explanation':explanation(query,semantic=False)}
