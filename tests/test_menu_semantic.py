from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from app.modules.menu.filters import eligible

@pytest.mark.parametrize('query,tags,price,expected',[
    ('сытное без мяса',['vegan'],200,True),
    ('без мяса',[],200,False),
    ('веганское',['vegetarian'],150,False),
    ('вегетарианское до 200 рублей',['vegetarian'],250,False),
    ('веганский обед до 250',['vegan'],250,True),
])
def test_explicit_constraints(query,tags,price,expected):
    assert eligible(SimpleNamespace(dietary_tags=tags,price=price),query) is expected


def test_search_endpoint_returns_current_menu_cards(client,storage,monkeypatch):
    from tests.conftest import add_menu_item
    import app.modules.menu.semantic as semantic
    item=add_menu_item(storage)
    item.image_url='/menu-images/test.webp'
    monkeypatch.setattr(semantic,'search_menu',lambda q:{'items':[item],'mode':'semantic'})
    r=client.get('/menu/search',params={'q':'сытный обед'})
    assert r.status_code==200
    assert r.json()['mode']=='semantic'
    assert r.json()['items'][0]['image_url']==item.image_url
    assert 'is_archived' not in r.json()['items'][0]
    assert client.get('/menu/search',params={'q':'x'}).status_code==422


@pytest.mark.parametrize('query,category,expected',[
    ('тёплый суп без мяса','Напитки',False),
    ('тёплый суп без мяса','Супы',True),
    ('веганский обед до 250','Напитки',False),
    ('веганский обед до 250','Горячее',True),
])
def test_semantic_food_types_are_constraints(query,category,expected):
    assert eligible(SimpleNamespace(dietary_tags=['vegan'],price=200),query,category) is expected


def test_semantic_outage_falls_back_to_current_lexical_menu(monkeypatch):
    import app.modules.menu.semantic as semantic
    from app.modules.assistant.contracts import ModelUnavailable
    model=Mock();model.embed.side_effect=ModelUnavailable()
    monkeypatch.setattr(semantic,'assistant_service',lambda:SimpleNamespace(model=model))
    cache=Mock();cache.get.return_value=None
    monkeypatch.setattr(semantic,'Redis',SimpleNamespace(from_url=lambda *args,**kwargs:cache))
    fallback=Mock(return_value={'items':[],'mode':'keyword'})
    monkeypatch.setattr(semantic,'lexical_fallback',fallback)
    assert semantic.search_menu('суп без мяса')['mode']=='keyword'
    fallback.assert_called_once_with('суп без мяса',8)



def test_coffee_with_milk_foam_excludes_black_coffee():
    black=SimpleNamespace(ingredients=['кофе','вода'],dietary_tags=['vegan'],price=95)
    milk=SimpleNamespace(ingredients=['кофе','молоко'],dietary_tags=['vegetarian'],price=145)
    assert not eligible(black,'кофейный напиток с молочной пеной','Напитки')
    assert eligible(milk,'кофейный напиток с молочной пеной','Напитки')
    assert eligible(black,'кофе без молока','Напитки')
    assert not eligible(milk,'кофе без молока','Напитки')


@pytest.mark.parametrize('category,expected',[
    ('Горячее',True),('Супы',True),('Паста и вок',True),
    ('Завтраки',False),('Перекусы',False),('Салаты',False),('Напитки',False),('Десерты',False),
])
def test_hot_lunch_excludes_breakfast_and_snacks(category,expected):
    assert eligible(SimpleNamespace(ingredients=[],dietary_tags=[],price=200),'горячий обед',category) is expected


def test_semantic_explanation_reports_actual_constraints():
    from app.modules.menu.filters import explanation
    result=explanation('горячий обед без мяса до 250 рублей')
    assert result['constraints']==['Горячий обед: горячее, супы и паста','Без мяса: вегетарианские рецептуры','До 250 ₽ за порцию']
