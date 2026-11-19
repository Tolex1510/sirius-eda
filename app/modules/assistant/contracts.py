from abc import ABC, abstractmethod
from dataclasses import dataclass
from app.domain.entities import User


class ModelUnavailable(Exception):
    pass


class ModelResponseInvalid(Exception):
    pass


@dataclass(frozen=True)
class Source:
    id: str
    text: str
    url: str


class LanguageModel(ABC):
    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]: ...
    @abstractmethod
    def generate(self, messages: list[dict]) -> str: ...


class AssistantRepository(ABC):
    @abstractmethod
    def search(self, embedding: list[float], query: str = "") -> list[Source]: ...
    def order_summary(self, actor: User, order_id: int | None = None) -> str | None:
        return None

    def menu_summary(self, query: str = "") -> str | None:
        return None

    def named_items(self, query: str) -> list[Source] | None:
        return None

    @abstractmethod
    def context(self, actor: User) -> str: ...
    @abstractmethod
    def history(self, actor: User, conversation_id: str) -> list[dict]: ...
    @abstractmethod
    def save(self, actor: User, conversation_id: str, question: str, answer: str, sources: list[Source]) -> None: ...
