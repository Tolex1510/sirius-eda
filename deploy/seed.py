"""Идемпотентное стартовое меню. Учётные записи только по явному DEMO_PASSWORD."""
import os
from app.database import SessionLocal
from app.models import Category, MenuItem, Role, User
from app.core.security import hash_password

MENU = {
    'Завтраки': [('Сырники со сметаной', 190), ('Овсяная каша', 120)],
    'Салаты': [('Овощной салат', 150), ('Цезарь с курицей', 260)],
    'Супы': [('Борщ', 180), ('Куриный суп', 160)],
    'Горячее': [('Курица с рисом', 290), ('Паста с томатами', 240), ('Гречка с грибами', 210)],
    'Десерты': [('Творожная запеканка', 160)],
    'Напитки': [('Морс', 80), ('Кофе', 110)],
}


def main():
    with SessionLocal() as check:
        empty = check.query(MenuItem).count() == 0
    if empty:
        from deploy.import_menu import main as import_menu
        import_menu()
    with SessionLocal.begin() as db:
        # Не меняем наполненное меню сданных лабораторных.
        if db.query(MenuItem).count() == 0:
            for name, items in MENU.items():
                category = db.query(Category).filter_by(name=name).first()
                if not category:
                    category = Category(name=name)
                    db.add(category)
                    db.flush()
                for title, price in items:
                    db.add(MenuItem(name=title, price=price, category_id=category.id, is_available=True))
        password = os.getenv('DEMO_PASSWORD')
        if password:
            if len(password) < 8:
                raise ValueError('DEMO_PASSWORD должен содержать минимум 8 символов')
            for role, email in [('student', 'student@demo.sirius.ru'), ('courier', 'courier@demo.sirius.ru'),
                                ('cook', 'cook@demo.sirius.ru'), ('admin', 'admin@demo.sirius.ru')]:
                if not db.query(User).filter_by(email=email).first():
                    db.add(User(email=email, balance=0, is_blocked=False, password_hash=hash_password(password),
                                role_id=db.query(Role.id).filter_by(name=role).scalar()))
    print('Стартовые данные готовы')


if __name__ == '__main__':
    main()
