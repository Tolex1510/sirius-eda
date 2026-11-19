from tests.conftest import add_menu_item


def test_public_dish_detail_and_missing_status(client, storage):
    item = add_menu_item(storage, price=190.5, is_available=False)
    response = client.get(f'/menu/items/{item.id}')
    assert response.status_code == 200
    assert response.json() == {'id': item.id, 'name': item.name, 'price': 190.5,
                               'is_available': False, 'category_id': None, 'image_url': None, 'description': '', 'ingredients': [], 'dietary_tags': [], 'portion_value': None, 'portion_unit': None}
    assert client.get('/menu/items/999999').status_code == 404
    assert client.get('/menu/items/not-a-number').status_code == 422


def test_catalog_metadata_and_archival(client, storage):
    item = add_menu_item(storage)
    item.description = "Суп из чечевицы"
    item.ingredients = ["чечевица", "томат"]
    item.dietary_tags = ["vegan"]
    item.portion_value, item.portion_unit = 350, "g"
    assert client.get(f"/menu/items/{item.id}").json()["ingredients"] == item.ingredients
    item.is_archived = True
    item.is_available = False
    assert client.get("/menu/items").json() == []
    assert client.get(f"/menu/items/{item.id}").status_code == 200
