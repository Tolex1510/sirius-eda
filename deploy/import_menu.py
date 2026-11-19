"""Idempotent curated menu import. Existing orders retain their original item rows."""
import json
from pathlib import Path
from sqlalchemy import select
from app.database import SessionLocal
from app.models import Category, MenuItem, KnowledgeChunk
from app.core.config import settings
from redis import Redis


def main():
    data=json.loads((Path(__file__).resolve().parents[1]/'data/menu/catalog.json').read_text())['items']
    slugs=[i['slug'] for i in data]
    if len(set(slugs))!=len(slugs) or not all(i['price']>0 and i['ingredients'] for i in data):
        raise ValueError('Invalid menu catalogue')
    with SessionLocal.begin() as db:
        for row in db.scalars(select(MenuItem)):
            if row.catalog_slug not in slugs:
                row.is_available=False
                row.is_archived=True
        for i in data:
            category=db.scalar(select(Category).where(Category.name==i['category']))
            if not category:
                category=Category(name=i['category']);db.add(category);db.flush()
            row=db.scalar(select(MenuItem).where(MenuItem.catalog_slug==i['slug']))
            if not row:
                row=MenuItem(catalog_slug=i['slug']);db.add(row)
            for key in ['name','price','description','ingredients','dietary_tags','is_available']:
                setattr(row,key,i[key])
            row.category_id=category.id
            row.portion_value=i['portion']['value'];row.portion_unit=i['portion']['unit'];row.is_archived=False
        db.query(KnowledgeChunk).filter(KnowledgeChunk.id.like('menu-%')).delete(synchronize_session=False)
    cache=Redis.from_url(settings.REDIS_URL)
    keys=list(cache.scan_iter('menu:*'))
    if keys: cache.delete(*keys)
    print(f'Imported {len(data)} dishes; archived old items; cleared menu cache and obsolete menu embeddings.')

if __name__=='__main__': main()
