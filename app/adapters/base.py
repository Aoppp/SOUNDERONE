from abc import ABC, abstractmethod
from typing import Any

from app.models import AgentReply, IncomingMessage, Platform


class PlatformAdapter(ABC):
    platform: Platform

    @abstractmethod
    def parse(self, payload: dict[str, Any]) -> IncomingMessage: ...

    @abstractmethod
    def serialize(self, reply: AgentReply) -> dict[str, Any]: ...
