"""
Транспортный слой модуля меню (круг 4: Frameworks & Drivers).
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.domain.exceptions import DomainError
from app.http_errors import to_http_exception
from app.modules.menu.repository import SqlAlchemyMenuRepository
from app.modules.menu.service import MenuService
from app.schemas import MenuItemCreate, MenuItemUpdate

router = APIRouter()


@router.post("/items")
def create_menu_item(payload: MenuItemCreate, db: Session = Depends(get_db)):
    if payload.price <= 0:
        raise HTTPException(
            status_code=400,
            detail="Цена должна быть положительной",
        )

    if len(payload.name) < 2:
        raise HTTPException(
            status_code=400,
            detail="Название блюда слишком короткое",
        )

    service = MenuService(SqlAlchemyMenuRepository(db))

    try:
        item = service.create_item(name=payload.name, price=payload.price)
    except DomainError as e:
        raise to_http_exception(e)

    return {"status": "success", "item_id": item.id}


@router.patch("/items/{item_id}")
def update_menu_item(
    item_id: int,
    payload: MenuItemUpdate,
    db: Session = Depends(get_db),
):
    if payload.price is not None and payload.price <= 0:
        raise HTTPException(
            status_code=400,
            detail="Цена должна быть положительной",
        )

    service = MenuService(SqlAlchemyMenuRepository(db))

    try:
        item = service.update_item(
            item_id=item_id,
            name=payload.name,
            price=payload.price,
            is_available=payload.is_available,
        )
    except DomainError as e:
        raise to_http_exception(e)

    return {"status": "success", "item_id": item.id}
