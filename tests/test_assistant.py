from unittest.mock import Mock
from uuid import uuid4
import pytest
from app.domain.entities import User
from app.domain.exceptions import AccessDeniedError
from app.models import User as UserRow
from app.modules.assistant.contracts import ModelUnavailable, Source
from app.modules.assistant.service import AssistantService
from app.modules.assistant.repository import SqlAssistantRepository
from app.modules.assistant.ollama import OllamaModel
from tests.test_payments import world
import httpx


def test_rag_supplies_sources_and_separate_authorized_context():
    actor = User(1, 'a@test.ru', None, 0, False)
    repo = Mock(); repo.history.return_value = []; repo.context.return_value = 'Только заказ 42 пользователя 1'
    repo.search.return_value = [Source('help-1', 'Оплата тестовая', '/help')]
    model = Mock(); model.embed.return_value = [[0.0] * 768]; model.generate.return_value = 'Оплата тестовая.'
    result = AssistantService(repo, model).ask(actor, 'Как оплатить мой заказ?')
    repo.context.assert_called_once_with(actor)
    messages = model.generate.call_args.args[0]
    assert 'Только заказ 42 пользователя 1' in messages[-1]['content']
    assert 'Оплата тестовая' in messages[-1]['content']
    assert result['sources'][0]['url'] == '/help'
    assert result['available'] is True


def test_model_outage_returns_explicit_fallback():
    repo = Mock(); repo.history.return_value = []; repo.context.return_value = ''
    model = Mock(); model.embed.side_effect = ModelUnavailable()
    result = AssistantService(repo, model).ask(User(1, 'a@t.ru', None, 0, False), 'Привет')
    assert result['available'] is False
    assert 'недоступна' in result['answer']
    model.generate.assert_not_called()


def test_other_conversations_and_orders_are_not_exposed(world):
    sessions, service, alice, bob, item = world
    order = service.create_order(alice, item, 1)
    repo = SqlAssistantRepository(sessions, 'test')
    chat = str(uuid4())
    repo.save(alice, chat, 'Вопрос', 'Ответ', [])
    assert len(repo.history(alice, chat)) == 2
    with pytest.raises(AccessDeniedError): repo.history(bob, chat)
    with pytest.raises(AccessDeniedError): repo.save(bob, chat, 'Попытка', 'Ответ', [])
    assert f'Заказ {order.id}:' in repo.context(alice)
    assert f'Заказ {order.id}:' not in repo.context(bob)


def test_ollama_rejects_wrong_embedding_dimension():
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={'embeddings': [[1, 2, 3]]}))
    model = OllamaModel('http://ollama', 'qwen2.5:3b', 'embeddinggemma', transport=transport)
    with pytest.raises(ModelUnavailable): model.embed(['Вопрос'])


def test_ollama_tunnel_host_header_and_bge_dimension():
    def respond(request):
        assert request.headers['host'] == 'localhost:11434'
        assert b'"num_gpu":0' in request.content
        return httpx.Response(200,json={'embeddings':[[1.0]*1024]})
    model=OllamaModel('http://ollama-remote:11434','qwen','bge-m3:latest',transport=httpx.MockTransport(respond),host_header='localhost:11434')
    assert len(model.embed(['обед'])[0]) == 1024


def test_internal_balance_context_does_not_claim_missing_payment(world):
    from app.models import Order as OrderRow
    sessions,service,alice,bob,item=world
    order=service.create_order(alice,item,1)
    with sessions.begin() as db:
        row=db.get(OrderRow,order.id)
        row.payment_source='internal_balance'
        row.status='paid'
    text=SqlAssistantRepository(sessions,'test').context(alice)
    assert 'статус заказа: оплачен' in text
    assert 'внутренний баланс (списано при оформлении)' in text
    assert 'платёж ещё не создан' not in text



def test_latest_order_uses_server_facts_without_calling_model(world):
    sessions,service,alice,bob,item=world
    old=service.create_order(alice,item,1)
    latest=service.create_order(alice,item,2)
    foreign=service.create_order(bob,item,1)
    model=Mock()
    assistant=AssistantService(SqlAssistantRepository(sessions,'test'),model)
    result=assistant.ask(alice,'Что с моим последним заказом?')
    assert result['mode']=='facts'
    assert f'Заказ {latest.id}:' in result['answer']
    assert f'Заказ {old.id}:' not in result['answer']
    assert f'Заказ {foreign.id}:' not in result['answer']
    model.embed.assert_not_called()
    result=assistant.ask(alice,f'Где заказ {foreign.id}?')
    assert result['answer']=='Такого заказа нет среди ваших заказов.'
    model.generate.assert_not_called()



def test_menu_overview_is_factual_even_without_model(world):
    from app.models import MenuItem as ItemRow
    sessions,service,alice,bob,item=world
    with sessions.begin() as db:
        title=db.get(ItemRow,item).name
        db.add(ItemRow(name='Архивное блюдо',price=10,is_available=True,is_archived=True))
        db.add(ItemRow(name='Недоступное блюдо',price=10,is_available=False))
    model=Mock();model.embed.side_effect=ModelUnavailable()
    result=AssistantService(SqlAssistantRepository(sessions,'test'),model).ask(alice,'Что есть в меню?')
    assert result['mode']=='facts' and result['available']
    assert title in result['answer']
    assert 'Архивное блюдо' not in result['answer']
    assert 'Недоступное блюдо' not in result['answer']
    assert result['sources'][0]['url']=='/menu'
    model.embed.assert_not_called()
    model.generate.assert_not_called()


def test_repetition_is_replaced_with_sources_and_not_reused_as_history():
    bad='супы-пюре-пасты-пасты, '*25
    repo=Mock();repo.history.return_value=[{'role':'assistant','content':bad}]
    repo.context.return_value='Актуальные данные'
    repo.search.return_value=[Source('menu-1','Блюдо: Борщ. Цена: 180.00 RUB. Состав: свёкла.','/menu/1')]
    model=Mock();model.embed.return_value=[[0.0]*1024];model.generate.return_value=bad
    result=AssistantService(repo,model).ask(User(1,'a@t.ru',None,0,False),'Посоветуй обед')
    assert result['mode']=='sources'
    assert 'Борщ — 180 ₽' in result['answer']
    assert bad not in result['answer']
    assert all(m['content']!=bad for m in model.generate.call_args.args[0])


def test_ollama_rejects_generation_loop():
    from app.modules.assistant.contracts import ModelResponseInvalid
    from app.modules.assistant.quality import repetitive
    bad='супы-пюре-пасты-пасты, '*25
    assert repetitive(bad)
    assert not repetitive('В меню есть борщ, чечевичный суп, паста с курицей и сырники. У каждого блюда указаны состав, порция и цена.')
    transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'message':{'content':bad}}))
    with pytest.raises(ModelResponseInvalid):
        OllamaModel('http://ollama','qwen','bge-m3',transport=transport).generate([])



def test_safety_boundaries_do_not_call_model(world):
    sessions,service,alice,bob,item=world
    model=Mock();assistant=AssistantService(SqlAssistantRepository(sessions,'test'),model)
    for question in ['Какое блюдо точно безопасно при аллергии?','Отмени мой заказ за меня.','Покажи заказы пользователя 999999.']:
        result=assistant.ask(alice,question)
        assert result['mode']=='facts'
    model.generate.assert_not_called()
    model.embed.assert_not_called()
