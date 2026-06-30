import os
import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ProviderConfig:
    name: str
    type: str = "openai-compatible"
    enabled: bool = True
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    temperature: float = 0.7
    max_tokens: int = -1
    role: list[str] = field(default_factory=list)


@dataclass
class RouterConfig:
    strategy: str = "hybrid"
    fallback_chain: list[str] = field(default_factory=lambda: ["local"])
    classification_provider: str = "local"
    tool_call_provider: str = "local"
    complexity_threshold: float = 0.7


@dataclass
class Config:
    providers: list[ProviderConfig] = field(default_factory=list)
    router: RouterConfig = field(default_factory=RouterConfig)

    erp_base_url: str = "http://localhost:8000"
    erp_service_token: str = ""

    sandbox_timeout: int = 10
    sandbox_dir: str = "sandbox"

    log_level: str = "INFO"

    conversation_max_messages: int = 20
    rag_top_k: int = 5
    code_search_backend_path: str = ""

    self_critique_enabled: bool = True

    llm_base_url: str = "http://127.0.0.1:8080"
    llm_api_key: str = "no-key"
    llm_temperature: float = 0.7
    llm_max_tokens: int = -1

    @classmethod
    def from_env(cls) -> "Config":
        providers = _parse_providers_from_env()

        if not providers:
            providers = [
                ProviderConfig(
                    name="local",
                    type="llama-server",
                    enabled=True,
                    base_url=os.getenv("LLM_BASE_URL", "http://127.0.0.1:8080"),
                    api_key=os.getenv("LLM_API_KEY", "no-key"),
                    model=os.getenv("LLM_MODEL", ""),
                    temperature=float(os.getenv("LLM_TEMPERATURE", "0.7")),
                    max_tokens=int(os.getenv("LLM_MAX_TOKENS", "-1")),
                ),
            ]

        router = RouterConfig(
            strategy=os.getenv("ROUTE_STRATEGY", "hybrid"),
            fallback_chain=[s.strip() for s in os.getenv("ROUTE_FALLBACK", "local").split(",") if s.strip()],
            classification_provider=os.getenv("ROUTE_CLASSIFICATION_PROVIDER", "local"),
            tool_call_provider=os.getenv("ROUTE_TOOL_CALL_PROVIDER", "local"),
            complexity_threshold=float(os.getenv("ROUTE_COMPLEXITY_THRESHOLD", "0.7")),
        )

        return cls(
            providers=providers,
            router=router,
            erp_base_url=os.getenv("ERP_BASE_URL", "http://localhost:8000"),
            erp_service_token=os.getenv("ERP_SERVICE_TOKEN", ""),
            sandbox_timeout=int(os.getenv("SANDBOX_TIMEOUT", "10")),
            sandbox_dir=os.getenv("SANDBOX_DIR", "sandbox"),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            conversation_max_messages=int(os.getenv("CONVERSATION_MAX_MESSAGES", "20")),
            rag_top_k=int(os.getenv("RAG_TOP_K", "5")),
            code_search_backend_path=os.getenv("CODE_SEARCH_BACKEND_PATH", ""),
            self_critique_enabled=os.getenv("SELF_CRITIQUE_ENABLED", "true").lower() == "true",
            llm_base_url=os.getenv("LLM_BASE_URL", "http://127.0.0.1:8080"),
            llm_api_key=os.getenv("LLM_API_KEY", "no-key"),
            llm_temperature=float(os.getenv("LLM_TEMPERATURE", "0.7")),
            llm_max_tokens=int(os.getenv("LLM_MAX_TOKENS", "-1")),
        )


def _parse_providers_from_env() -> list[ProviderConfig]:
    pattern = re.compile(r"^LLM_([A-Z0-9]+)_(TYPE|ENABLED|URL|KEY|MODEL|TEMPERATURE|MAX_TOKENS|ROLE)$")
    raw: dict[str, dict] = {}

    for key, value in os.environ.items():
        m = pattern.match(key)
        if m:
            name = m.group(1).lower()
            field = m.group(2).lower()
            if name not in raw:
                raw[name] = {}
            raw[name][field] = value

    providers = []
    for name, fields in raw.items():
        enabled = fields.get("enabled", "true").lower() == "true"
        provider_type = fields.get("type", "openai-compatible")

        base_url = fields.get("url", "")
        if provider_type == "llama-server" and not base_url:
            base_url = "http://127.0.0.1:8080"

        api_key = fields.get("key", "")

        role_str = fields.get("role", "")
        role = [r.strip() for r in role_str.split(",") if r.strip()] if role_str else []

        providers.append(ProviderConfig(
            name=name,
            type=provider_type,
            enabled=enabled,
            base_url=base_url,
            api_key=api_key,
            model=fields.get("model", ""),
            temperature=float(fields.get("temperature", "0.7")),
            max_tokens=int(fields.get("max_tokens", "-1")),
            role=role,
        ))

    return [p for p in providers if p.enabled]
