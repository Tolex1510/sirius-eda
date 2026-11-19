"""Explicit catalogue constraints. Embeddings rank candidates after these checks."""
import re

HOT_MEAL_CATEGORIES = ('Горячее', 'Супы', 'Паста и вок')
LUNCH_CATEGORIES = (*HOT_MEAL_CATEGORIES, 'Салаты')


def diet_for(question: str) -> str | None:
    if re.search(r'веган|полностью растительн|без продуктов животного', question, re.I):
        return 'vegan'
    if re.search(r'без мяс|вегетариан', question, re.I):
        return 'vegetarian'
    return None


def budget_for(query: str) -> int | None:
    match = re.search(r'до\s+(\d{2,4})(?:\s*(?:₽|руб|р\b))?', query, re.I)
    return int(match.group(1)) if match else None


def category_rule(query: str) -> tuple[tuple[str, ...], str] | None:
    if re.search(r'\bсуп(?:а|ы|ов|ом|чик|чики|е|у)?\b|борщ|бульон|\bуха\b', query, re.I):
        return ('Супы',), 'Супы'
    if re.search(r'кофе|кофейн|капучино|эспрессо|американо|напит|попить|питьё', query, re.I):
        return ('Напитки',), 'Напитки'
    if re.search(r'десерт|сладкое|к чаю', query, re.I):
        return ('Десерты',), 'Десерты'
    if re.search(r'завтрак', query, re.I):
        return ('Завтраки',), 'Завтраки'
    if re.search(r'перекус|сэндвич|бутерброд', query, re.I):
        return ('Перекусы',), 'Перекусы'
    if re.search(r'паст[аыуе]|лапш|вок|спагетти|удон|соба', query, re.I):
        return ('Паста и вок',), 'Паста и вок'
    if re.search(r'салат', query, re.I):
        return ('Салаты',), 'Салаты'
    hot = bool(re.search(r'горяч|тёпл|тепл', query, re.I))
    lunch = bool(re.search(r'обед|поесть|сытн', query, re.I))
    if hot:
        label = 'Горячий обед: горячее, супы и паста' if lunch else 'Горячие блюда, супы и паста'
        return HOT_MEAL_CATEGORIES, label
    if lunch:
        return LUNCH_CATEGORIES, 'Обед: горячее, супы, паста и салаты'
    if re.search(r'блюд', query, re.I):
        return ('Завтраки', 'Горячее', 'Супы', 'Паста и вок', 'Салаты', 'Перекусы'), 'Блюда без напитков и десертов'
    return None


def explanation(query: str, semantic: bool = True) -> dict:
    constraints = []
    category = category_rule(query)
    if category:
        constraints.append(category[1])
    diet = diet_for(query)
    if diet:
        constraints.append('Веганская рецептура' if diet == 'vegan' else 'Без мяса: вегетарианские рецептуры')
    budget = budget_for(query)
    if budget is not None:
        constraints.append(f'До {budget} ₽ за порцию')
    if re.search(r'кофе|кофейн|капучино|эспрессо|американо', query, re.I):
        if re.search(r'с\s+молок|молочн.*пен|капучино|латте', query, re.I):
            constraints.append('Кофе с молоком')
        elif re.search(r'без\s+(?:добавления\s+)?молок', query, re.I):
            constraints.append('Кофе без молока')
    return {'constraints': constraints, 'ranking': (
        'Сравниваем пожелание с названием, описанием и составом блюд. '
        'Сначала применяем указанные условия, затем показываем наиболее близкие варианты.'
        if semantic else 'Подбор по пожеланиям сейчас недоступен. Выполнен поиск по словам.'
    )}


def eligible(item, query: str, category=None) -> bool:
    coffee = re.search(r'кофе|кофейн|капучино|эспрессо|американо', query, re.I)
    ingredients = getattr(item, 'ingredients', None) or []
    if coffee and not any('кофе' in value.lower() for value in ingredients):
        return False
    if coffee:
        has_milk = any('молок' in value.lower() for value in ingredients)
        if re.search(r'без\s+(?:добавления\s+)?молок', query, re.I) and has_milk:
            return False
        if re.search(r'с\s+молок|молочн.*пен|капучино|латте', query, re.I) and not has_milk:
            return False
    rule = category_rule(query)
    if category and rule and category not in rule[0]:
        return False
    tags = item.dietary_tags or []
    diet = diet_for(query)
    if diet == 'vegan' and 'vegan' not in tags:
        return False
    if diet == 'vegetarian' and not {'vegan', 'vegetarian'}.intersection(tags):
        return False
    budget = budget_for(query)
    return budget is None or item.price <= budget
