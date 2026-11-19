from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
import re
from sqlalchemy import select
from app.domain.exceptions import AccessDeniedError
from app.models import ChatConversation, ChatMessage, KnowledgeChunk, Category, MenuItem, Order, Payment, Delivery
from app.modules.assistant.contracts import AssistantRepository, Source
from app.modules.menu.filters import eligible
from app.modules.assistant.quality import rubles


def menu_text(item, category=""):
    section = f" Раздел: {category}." if category else ""
    portion = f" Порция: {item.portion_value} {item.portion_unit}." if item.portion_value else ""
    return (f'Блюдо: {item.name}. Цена: {item.price} RUB. '
            f'Доступно: {"да" if item.is_available else "нет"}. '
            f'{item.description or ""} Состав: {", ".join(item.ingredients or [])}. '
            f'Маркеры рецептуры: {", ".join(item.dietary_tags or [])}.' + portion + section)


def order_fact(o, p, d):
    statuses={'processing':'ожидает оплаты','paid':'оплачен','delivered':'доставлен','cancelled':'отменён'}
    delivery_statuses={'in_progress':'курьер назначен','on_the_way':'курьер в пути','completed':'доставлено','cancelled':'отменена'}
    if o.payment_source == 'internal_balance':
        payment='внутренний баланс (списано при оформлении)'
        refund='возвращено на внутренний баланс' if o.status=='cancelled' else 'нет'
    else:
        payment=p.status if p else 'платёж ещё не создан'
        refund=p.refund_status if p and p.refund_status else 'нет'
    return (f'Заказ {o.id}: {o.item.name if o.item else "Блюдо"}, {o.quantity} шт., {o.total_cost} RUB; '
            f'статус заказа: {statuses.get(o.status,o.status)}; оплата: {payment}; '
            f'возврат: {refund}; доставка: {delivery_statuses.get(d.status,d.status) if d else "не назначена"}.')


class SqlAssistantRepository(AssistantRepository):
    def __init__(self, sessions, embedding_model):
        self.sessions, self.embedding_model = sessions, embedding_model

    def search(self, embedding, query=""):
        with self.sessions() as db:
            # pgvector вычисляет cosine distance; индекс содержит только публичные данные.
            rows = db.scalars(select(KnowledgeChunk).where(KnowledgeChunk.embedding_model == self.embedding_model)
                              .order_by(KnowledgeChunk.embedding.cosine_distance(embedding)).limit(24))
            sources = []
            categories=dict(db.execute(select(Category.id,Category.name)).all())
            for row in rows:
                if row.id.startswith('menu-'):
                    item = db.get(MenuItem, int(row.id.removeprefix('menu-')))
                    if not item or item.is_archived or not item.is_available or not eligible(item, query, categories.get(item.category_id)):
                        continue
                    text = menu_text(item, categories.get(item.category_id, ""))
                else:
                    text = row.content
                sources.append(Source(row.id, text, row.url))
            return sources[:4]

    def order_summary(self, actor, order_id=None):
        with self.sessions() as db:
            query=select(Order,Payment,Delivery).outerjoin(Payment,Payment.order_id==Order.id).outerjoin(Delivery,Delivery.order_id==Order.id).where(Order.user_id==actor.id)
            if order_id is not None:
                query=query.where(Order.id==order_id)
            row=db.execute(query.order_by(Order.id.desc()).limit(1)).first()
            if row is None:
                return 'Такого заказа нет среди ваших заказов.' if order_id is not None else 'У вас пока нет заказов.'
            return ('Информация о вашем заказе.\n' if order_id is not None else 'Ваш последний заказ.\n')+order_fact(*row)

    def menu_summary(self, query=""):
        with self.sessions() as db:
            rows=db.execute(select(MenuItem,Category.name).outerjoin(Category,Category.id==MenuItem.category_id)
                .where(MenuItem.is_available.is_(True),MenuItem.is_archived.is_(False))
                .order_by(Category.name,MenuItem.name)).all()
            sections={}
            for item,category in rows:
                if eligible(item,query,category):
                    sections.setdefault(category or 'Другие блюда',[]).append(item)
            if not sections:
                return 'Сейчас подходящих доступных блюд нет. Попробуйте изменить пожелания или загляните в меню позже.'
            count=sum(len(items) for items in sections.values())
            lines=[f'Сейчас доступно {count} блюд и напитков. Например:']
            for category,items in sections.items():
                examples='; '.join(f'{item.name} — {rubles(item.price)}' for item in items[:2])
                lines.append(f'• {category}: {examples}.')
            lines.append('Полный список с составом и порциями — по ссылке «Полное меню» ниже.')
            return '\n'.join(lines)

    def named_items(self, query):
        stop={'сколько','стоит','стоимость','цена','есть','доступно','доступны','блюдо','блюда','меню','которого','нет','покажи','какая','какие'}
        stems={word[:4] for word in re.findall(r'[а-яёa-z]{3,}',query.lower()) if word not in stop}
        if not stems:
            return []
        with self.sessions() as db:
            rows=db.scalars(select(MenuItem).where(MenuItem.is_archived.is_(False)).order_by(MenuItem.name))
            found=[]
            for item in rows:
                words={word[:4] for word in re.findall(r'[а-яёa-z]{3,}',item.name.lower())}
                if stems & words:
                    found.append(Source(f'menu-{item.id}',menu_text(item),f'/menu/{item.id}'))
            return found[:5]

    def context(self, actor):
        with self.sessions() as db:
            rows = db.execute(select(Order, Payment, Delivery).outerjoin(Payment, Payment.order_id == Order.id)
                              .outerjoin(Delivery, Delivery.order_id == Order.id)
                              .where(Order.user_id == actor.id).order_by(Order.id.desc()).limit(5))
            facts = ['Ниже только последние пять заказов пользователя, а не вся история.']
            facts.extend(order_fact(o,p,d) for o,p,d in rows)
            facts.append('Названия, цены и состав блюд бери только из найденных источников ниже.')
            return '\n'.join(facts)

    def history(self, actor, conversation_id):
        with self.sessions() as db:
            conversation = db.get(ChatConversation, conversation_id)
            if not conversation:
                return []
            if conversation.user_id != actor.id:
                raise AccessDeniedError('Нет доступа к чужому диалогу')
            rows = list(db.scalars(select(ChatMessage).where(ChatMessage.conversation_id == conversation_id)
                                   .order_by(ChatMessage.id.desc()).limit(20)))
            return [{'role': m.role, 'content': m.content} for m in reversed(rows)]

    def save(self, actor, conversation_id, question, answer, sources):
        with self.sessions.begin() as db:
            conversation = db.get(ChatConversation, conversation_id)
            if conversation and conversation.user_id != actor.id:
                raise AccessDeniedError('Нет доступа к чужому диалогу')
            if not conversation:
                db.add(ChatConversation(id=conversation_id, user_id=actor.id))
                db.flush()
            db.add(ChatMessage(conversation_id=conversation_id, role='user', content=question, sources=[]))
            db.add(ChatMessage(conversation_id=conversation_id, role='assistant', content=answer,
                               sources=[{'id': s.id, 'url': s.url} for s in sources]))

    def index(self, model):
        """Изменившиеся записи переиндексируются, удалённые удаляются. Обучающие отчёты не индексируются."""
        with self.sessions() as db:
            categories=dict(db.execute(select(Category.id,Category.name)).all())
            docs = [Source(f'menu-{i.id}', menu_text(i,categories.get(i.category_id,"")), f'/menu/{i.id}')
                    for i in db.scalars(select(MenuItem).where(MenuItem.is_archived.is_(False)).order_by(MenuItem.id))]
            existing = {r.id: (r.checksum, r.embedding_model) for r in db.scalars(select(KnowledgeChunk))}
        knowledge_path = Path(__file__).resolve().parents[3] / 'docs' / 'knowledge' / 'service.md'
        text = knowledge_path.read_text()
        for n, part in enumerate(text.split('\n## ')):
            docs.append(Source(f'help-{n}', part.strip(), '/help'))
        pending = [(doc, sha256(doc.text.encode()).hexdigest()) for doc in docs
                   if existing.get(doc.id) != (sha256(doc.text.encode()).hexdigest(), self.embedding_model)]
        changed = 0
        for offset in range(0, len(pending), 8):
            batch = pending[offset:offset+8]
            vectors = model.embed([doc.text for doc, _ in batch])
            with self.sessions.begin() as db:
                for (doc, checksum), embedding in zip(batch, vectors, strict=True):
                    db.merge(KnowledgeChunk(id=doc.id, content=doc.text, url=doc.url, checksum=checksum,
                                            embedding=embedding, embedding_model=self.embedding_model,
                                            updated_at=datetime.now(UTC)))
            changed += len(batch)
        with self.sessions.begin() as db:
            db.query(KnowledgeChunk).filter(KnowledgeChunk.id.not_in([d.id for d in docs])).delete(synchronize_session=False)
        return changed
