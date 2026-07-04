"""Client Registry — мульти-клиентская платформа для AI-агентов.

Каждый клиент (ERP, Telegram, CRM и т.д.) имеет свой набор инструментов,
навыков и контекст. Идентификация по X-Client-ID + X-Client-API-Key.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ClientConfig:
    client_id: str
    name: str
    api_key: str
    enabled: bool = True
    system_prompt: str = ""
    tools: list[dict] = field(default_factory=list)     # кастомные инструменты
    skills: dict = field(default_factory=dict)           # навыки клиента
    allowed_models: list[str] = field(default_factory=list)  # пусто = все
    rate_limit: int = 10   # запросов в минуту
    created_at: float = 0.0
    last_seen: float = 0.0
    request_count: int = 0
    metadata: dict = field(default_factory=dict)         # произвольные данные

    def to_dict(self) -> dict:
        return {
            "client_id": self.client_id,
            "name": self.name,
            "api_key": self.api_key,
            "enabled": self.enabled,
            "system_prompt": self.system_prompt,
            "tools": self.tools,
            "skills": self.skills,
            "allowed_models": self.allowed_models,
            "rate_limit": self.rate_limit,
            "created_at": self.created_at,
            "last_seen": self.last_seen,
            "request_count": self.request_count,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ClientConfig:
        return cls(
            client_id=data.get("client_id", ""),
            name=data.get("name", ""),
            api_key=data.get("api_key", ""),
            enabled=data.get("enabled", True),
            system_prompt=data.get("system_prompt", ""),
            tools=data.get("tools", []),
            skills=data.get("skills", {}),
            allowed_models=data.get("allowed_models", []),
            rate_limit=data.get("rate_limit", 10),
            created_at=data.get("created_at", 0.0),
            last_seen=data.get("last_seen", 0.0),
            request_count=data.get("request_count", 0),
            metadata=data.get("metadata", {}),
        )


class ClientRegistry:
    """Реестр клиентов. Хранит конфиги в clients/{id}.json"""

    def __init__(self, clients_dir: Path) -> None:
        self.clients_dir = clients_dir
        self.clients_dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, ClientConfig] = {}
        self._load_all()

    def _load_all(self) -> None:
        for f in self.clients_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                client = ClientConfig.from_dict(data)
                if client.client_id:
                    self._cache[client.client_id] = client
            except Exception:
                pass

    def get(self, client_id: str) -> ClientConfig | None:
        return self._cache.get(client_id)

    def get_by_api_key(self, api_key: str) -> ClientConfig | None:
        for client in self._cache.values():
            if client.api_key == api_key and client.enabled:
                return client
        return None

    def list_all(self) -> list[ClientConfig]:
        return list(self._cache.values())

    def create(self, client: ClientConfig) -> ClientConfig:
        client.created_at = time.time()
        self._cache[client.client_id] = client
        self._save(client)
        return client

    def update(self, client_id: str, updates: dict) -> ClientConfig | None:
        client = self._cache.get(client_id)
        if not client:
            return None
        for key, val in updates.items():
            if hasattr(client, key) and key not in ("client_id", "created_at"):
                setattr(client, key, val)
        self._save(client)
        return client

    def delete(self, client_id: str) -> bool:
        if client_id not in self._cache:
            return False
        del self._cache[client_id]
        path = self.clients_dir / f"{client_id}.json"
        if path.exists():
            path.unlink()
        return True

    def record_request(self, client_id: str) -> None:
        client = self._cache.get(client_id)
        if client:
            client.last_seen = time.time()
            client.request_count += 1
            self._save(client)

    def add_tool(self, client_id: str, tool: dict) -> bool:
        client = self._cache.get(client_id)
        if not client:
            return False
        # Проверяем дубликат
        existing_names = {t.get("name") for t in client.tools}
        if tool.get("name") in existing_names:
            return False
        client.tools.append(tool)
        self._save(client)
        return True

    def remove_tool(self, client_id: str, tool_name: str) -> bool:
        client = self._cache.get(client_id)
        if not client:
            return False
        before = len(client.tools)
        client.tools = [t for t in client.tools if t.get("name") != tool_name]
        if len(client.tools) < before:
            self._save(client)
            return True
        return False

    def _save(self, client: ClientConfig) -> None:
        path = self.clients_dir / f"{client.client_id}.json"
        path.write_text(
            json.dumps(client.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


# ── Default ERP client ─────────────────────────────────────────────

ERP_CLIENT_CONFIG = ClientConfig(
    client_id="erp",
    name="ERP L-Start",
    api_key=os.environ.get("ERP_API_KEY", "erp_secret_key_2026"),
    system_prompt="""Ты — ИИ-ассистент ERP-системы L-Start.
Помогаешь сотрудникам компании решать рабочие задачи:
- Работа с проектами (карточки, комментарии, наряды)
- Управление командировками и графиками
- Поиск информации в базе знаний
- Формирование отчётов

Правила:
- После записи в ERP — перечитать и проверить
- При неуверенности — сказать об этом
- Отвечать кратко и по существу""",
    tools=[],  # будут зарегистрированы из ERPIntegrationTools
    rate_limit=20,
)


def ensure_default_clients(registry: ClientRegistry) -> None:
    """Создать клиентов по умолчанию если их нет."""
    if not registry.get("erp"):
        registry.create(ERP_CLIENT_CONFIG)
