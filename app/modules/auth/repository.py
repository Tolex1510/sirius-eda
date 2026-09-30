"""
Инфраструктурный слой модуля аутентификации (круг 3: Interface Adapters).
Хранит выданные refresh-токены, чтобы их можно было отозвать.
"""
from abc import ABC, abstractmethod
from dataclasses import replace
from datetime import datetime

from sqlalchemy.orm import Session

from app.domain.entities import RefreshTokenRecord
from app.memory_storage import InMemoryStorage
from app.models import ExternalAccount as ExternalAccountModel
from app.models import RefreshToken as RefreshTokenModel


class AuthRepository(ABC):
    """Контракт хранилища, от которого зависит AuthService."""

    @abstractmethod
    def save_refresh_token(self, user_id: int, token_hash: str, expires_at: datetime) -> None: ...

    @abstractmethod
    def get_refresh_token(self, token_hash: str) -> RefreshTokenRecord | None: ...

    @abstractmethod
    def revoke_refresh_token(self, token_id: int) -> bool:
        """Отзывает токен. False, если он уже был отозван: значит, его пытаются использовать повторно."""

    @abstractmethod
    def revoke_all_refresh_tokens(self, user_id: int) -> None: ...

    @abstractmethod
    def get_user_id_by_external(self, provider: str, subject: str) -> int | None: ...

    @abstractmethod
    def link_external(self, user_id: int, provider: str, subject: str, email: str | None) -> None: ...


class SqlAlchemyAuthRepository(AuthRepository):
    def __init__(self, db: Session):
        self.db = db

    def save_refresh_token(self, user_id: int, token_hash: str, expires_at: datetime) -> None:
        self.db.add(RefreshTokenModel(user_id=user_id, token_hash=token_hash, expires_at=expires_at))
        self.db.commit()

    def get_refresh_token(self, token_hash: str) -> RefreshTokenRecord | None:
        row = self.db.query(RefreshTokenModel).filter(RefreshTokenModel.token_hash == token_hash).first()
        if not row:
            return None
        return RefreshTokenRecord(
            id=row.id,
            user_id=row.user_id,
            token_hash=row.token_hash,
            expires_at=row.expires_at,
            is_revoked=row.is_revoked,
        )

    def revoke_refresh_token(self, token_id: int) -> bool:
        # Условный UPDATE атомарен: из двух параллельных refresh с одним токеном пройдёт только один.
        updated = (
            self.db.query(RefreshTokenModel)
            .filter(RefreshTokenModel.id == token_id, RefreshTokenModel.is_revoked.is_(False))
            .update({"is_revoked": True})
        )
        self.db.commit()
        return updated == 1

    def revoke_all_refresh_tokens(self, user_id: int) -> None:
        self.db.query(RefreshTokenModel).filter(RefreshTokenModel.user_id == user_id).update({"is_revoked": True})
        self.db.commit()

    def get_user_id_by_external(self, provider: str, subject: str) -> int | None:
        row = (
            self.db.query(ExternalAccountModel.user_id)
            .filter(ExternalAccountModel.provider == provider, ExternalAccountModel.subject == subject)
            .first()
        )
        return row[0] if row else None

    def link_external(self, user_id: int, provider: str, subject: str, email: str | None) -> None:
        self.db.add(ExternalAccountModel(user_id=user_id, provider=provider, subject=subject, email=email))
        self.db.commit()


class InMemoryAuthRepository(AuthRepository):
    """Хранит данные в памяти процесса. Используется в тестах и без СУБД."""

    def __init__(self, storage: InMemoryStorage):
        self.storage = storage

    def save_refresh_token(self, user_id: int, token_hash: str, expires_at: datetime) -> None:
        token_id = self.storage.next_id("refresh_tokens")
        self.storage.refresh_tokens[token_id] = RefreshTokenRecord(
            id=token_id,
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            is_revoked=False,
        )

    def get_refresh_token(self, token_hash: str) -> RefreshTokenRecord | None:
        for record in self.storage.refresh_tokens.values():
            if record.token_hash == token_hash:
                return replace(record)
        return None

    def revoke_refresh_token(self, token_id: int) -> bool:
        record = self.storage.refresh_tokens[token_id]
        if record.is_revoked:
            return False
        record.is_revoked = True
        return True

    def revoke_all_refresh_tokens(self, user_id: int) -> None:
        for record in self.storage.refresh_tokens.values():
            if record.user_id == user_id:
                record.is_revoked = True

    def get_user_id_by_external(self, provider: str, subject: str) -> int | None:
        return self.storage.external_accounts.get((provider, subject))

    def link_external(self, user_id: int, provider: str, subject: str, email: str | None) -> None:
        self.storage.external_accounts[(provider, subject)] = user_id
