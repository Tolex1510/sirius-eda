"""
Транспортный слой модуля меню (круг 4: Frameworks & Drivers).
"""
from fastapi import APIRouter, Depends, HTTPException

from app.core.dependencies import require_role
from app.dependencies import get_menu_repository
from app.domain.entities import Role, User
from app.domain.exceptions import DomainError
from app.http_errors import to_http_exception
from app.modules.menu.repository import MenuRepository
from app.modules.menu.service import MenuService
from app.schemas import (
    CategoryCreate,
    CategoryMenuResponse,
    CategoryResponse,
    MenuItemCreate,
    MenuItemResponse,
    MenuItemUpdate,
)

router = APIRouter()


def get_menu_service(repository: MenuRepository = Depends(get_menu_repository)) -> MenuService:
    """Сборка слоёв: конкретный репозиторий внедряется в сервис через конструктор."""
    return MenuService(repository)


menu_editor = require_role(Role.ADMIN, Role.COOK)


# response_model включает сериализацию через pydantic-core. Без него FastAPI
# обходит 300 блюд в jsonable_encoder на чистом Python, и это дороже чтения из кеша.
@router.get("/items", response_model=list[MenuItemResponse])
def list_menu_items(service: MenuService = Depends(get_menu_service)):
    return service.list_items()


@router.get("/categories", response_model=list[CategoryResponse])
def list_categories(service: MenuService = Depends(get_menu_service)):
    return service.list_categories()


@router.get("/categories/{category_id}", response_model=CategoryMenuResponse)
def get_category_menu(category_id: int, service: MenuService = Depends(get_menu_service)):
    try:
        return service.get_category_menu(category_id)
    except DomainError as e:
        raise to_http_exception(e)


@router.post("/categories")
def create_category(
    payload: CategoryCreate,
    _: User = Depends(menu_editor),
    service: MenuService = Depends(get_menu_service),
):
    try:
        category = service.create_category(payload.name)
    except DomainError as e:
        raise to_http_exception(e)

    return {"status": "success", "category_id": category.id}


@router.post("/items")
def create_menu_item(
    payload: MenuItemCreate,
    _: User = Depends(menu_editor),
    service: MenuService = Depends(get_menu_service),
):
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

    try:
        item = service.create_item(name=payload.name, price=payload.price, category_id=payload.category_id)
    except DomainError as e:
        raise to_http_exception(e)

    return {"status": "success", "item_id": item.id}


@router.patch("/items/{item_id}")
def update_menu_item(
    item_id: int,
    payload: MenuItemUpdate,
    _: User = Depends(menu_editor),
    service: MenuService = Depends(get_menu_service),
):
    if payload.price is not None and payload.price <= 0:
        raise HTTPException(
            status_code=400,
            detail="Цена должна быть положительной",
        )

    try:
        item = service.update_item(
            item_id=item_id,
            name=payload.name,
            price=payload.price,
            is_available=payload.is_available,
            category_id=payload.category_id,
        )
    except DomainError as e:
        raise to_http_exception(e)

    return {"status": "success", "item_id": item.id}
