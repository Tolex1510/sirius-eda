"""
Транспортный слой кухни (круг 4: Frameworks & Drivers).
Очередь заполняет consumer события OrderPaid, повар её только читает.
"""
from fastapi import APIRouter, Depends

from app.core.dependencies import require_role
from app.dependencies import get_kitchen_repository
from app.domain.entities import Role, User
from app.modules.kitchen.repository import KitchenRepository
from app.modules.kitchen.service import KitchenService

router = APIRouter()


@router.get("/tickets")
def kitchen_queue(
    _: User = Depends(require_role(Role.COOK, Role.ADMIN)),
    repository: KitchenRepository = Depends(get_kitchen_repository),
):
    return KitchenService(repository).queue()
