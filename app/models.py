"""
Определение ORM-моделей предметной области «Сириус.Еда».
"""
from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
from app.domain import entities


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False)
    phone = Column(String, nullable=True)
    balance = Column(Float, default=0.0)
    is_blocked = Column(Boolean, default=False)

    def to_entity(self) -> entities.User:
        return entities.User(
            id=self.id,
            email=self.email,
            phone=self.phone,
            balance=self.balance,
            is_blocked=self.is_blocked,
        )


class MenuItem(Base):
    __tablename__ = "menu_items"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    is_available = Column(Boolean, default=True)

    def to_entity(self) -> entities.MenuItem:
        return entities.MenuItem(
            id=self.id,
            name=self.name,
            price=self.price,
            is_available=self.is_available,
        )


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    item_id = Column(Integer, ForeignKey("menu_items.id"))
    quantity = Column(Integer, nullable=False)
    status = Column(String, default="processing")

    user = relationship("User")
    item = relationship("MenuItem")

    def to_entity(self) -> entities.Order:
        return entities.Order(
            id=self.id,
            user_id=self.user_id,
            item_id=self.item_id,
            quantity=self.quantity,
            status=self.status,
        )


class Delivery(Base):
    __tablename__ = "deliveries"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"))
    courier_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    status = Column(String, default="pending")

    order = relationship("Order")
    courier = relationship("User")

    def to_entity(self) -> entities.Delivery:
        return entities.Delivery(
            id=self.id,
            order_id=self.order_id,
            courier_id=self.courier_id,
            status=self.status,
        )
