import logging
import time
from typing import Optional

from gateway import BaseLLM

logger = logging.getLogger(__name__)


def classify_complexity(prompt: str) -> float:
    score = 0.0
    if len(prompt) > 200:
        score += 0.3
    if len(prompt) > 500:
        score += 0.2
    if "```" in prompt:
        score += 0.3
    complex_words = ("объясни", "проанализируй", "напиши код", "сравни", "создай функцию",
                     "рефактор", "оптимизируй", "архитектур", "спроектируй")
    if any(w in prompt.lower() for w in complex_words):
        score += 0.3
    simple_words = ("посчитай", "что такое", "какой", "сколько", "найди")
    if any(w in prompt.lower() for w in simple_words):
        score -= 0.2
    return max(0.0, min(1.0, score))


class ProviderPool:
    def __init__(self):
        self.health_cache: dict[str, tuple[bool, float]] = {}
        self.health_ttl = 60.0

    def is_healthy(self, name: str, provider: BaseLLM) -> bool:
        now = time.time()
        if name in self.health_cache:
            healthy, checked_at = self.health_cache[name]
            if now - checked_at < self.health_ttl:
                return healthy

        healthy = False
        if hasattr(provider, "health_check"):
            try:
                healthy = provider.health_check()
            except Exception:
                healthy = False

        self.health_cache[name] = (healthy, now)
        return healthy

    def invalidate(self, name: str) -> None:
        self.health_cache.pop(name, None)


class RouterLLM(BaseLLM):
    def __init__(
        self,
        providers: dict[str, BaseLLM],
        strategy: str = "hybrid",
        fallback_chain: Optional[list[str]] = None,
        classification_provider: str = "local",
        tool_call_provider: str = "local",
        complexity_threshold: float = 0.7,
    ):
        self.providers = providers
        self.strategy = strategy
        self.fallback_chain = fallback_chain or list(providers.keys())
        self.classification_provider = classification_provider
        self.tool_call_provider = tool_call_provider
        self.complexity_threshold = complexity_threshold
        self.pool = ProviderPool()
        self._last_classification_scope: Optional[str] = None

    def _get_provider(self, name: str) -> Optional[BaseLLM]:
        return self.providers.get(name)

    def _select_provider(self, prompt: str, system_prompt: str = "", tools: list = None) -> str:
        is_classification = system_prompt and "классификатор" in system_prompt
        if is_classification and self.classification_provider in self.providers:
            return self.classification_provider

        is_tool_call = bool(tools)
        if is_tool_call and self.tool_call_provider in self.providers:
            return self.tool_call_provider

        if self.strategy == "local-first":
            for name in self.fallback_chain:
                if name in self.providers and self.pool.is_healthy(name, self.providers[name]):
                    return name

        if self.strategy == "api-first":
            for name in self.fallback_chain:
                if name == "local" or name == "mock":
                    continue
                if name in self.providers and self.pool.is_healthy(name, self.providers[name]):
                    return name
            if "local" in self.providers:
                return "local"

        complexity = classify_complexity(prompt)
        logger.debug("Complexity: %.2f (threshold: %.2f)", complexity, self.complexity_threshold)

        if complexity < self.complexity_threshold:
            for name in self.fallback_chain:
                if name in self.providers and self.pool.is_healthy(name, self.providers[name]):
                    return name
        else:
            for name in self.fallback_chain:
                if name in ("local", "mock"):
                    continue
                if name in self.providers and self.pool.is_healthy(name, self.providers[name]):
                    return name
            for name in self.fallback_chain:
                if name in self.providers and self.pool.is_healthy(name, self.providers[name]):
                    return name

        for name, provider in self.providers.items():
            if self.pool.is_healthy(name, provider):
                return name

        return list(self.providers.keys())[0] if self.providers else "mock"

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        tools: Optional[list] = None,
        messages: Optional[list[dict]] = None,
        **kwargs,
    ) -> dict:
        selected = self._select_provider(prompt, system_prompt, tools)
        logger.info("Router: selected provider '%s' for strategy='%s'", selected, self.strategy)

        errors = []
        tried = set()

        chain = [selected] + [n for n in self.fallback_chain if n != selected]

        for name in chain:
            if name in tried:
                continue
            tried.add(name)

            provider = self._get_provider(name)
            if not provider:
                continue

            if name != selected and not self.pool.is_healthy(name, provider):
                continue

            result = provider.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                tools=tools,
                messages=messages,
                **kwargs,
            )

            if result.get("ok"):
                result["provider"] = name
                return result

            error = result.get("error", "unknown")
            errors.append(f"{name}: {error}")
            logger.warning("Provider '%s' failed: %s", name, error)
            self.pool.invalidate(name)

        logger.error("All providers failed: %s", errors)
        return {"ok": False, "error": f"All providers failed: {'; '.join(errors)}"}

    def get_status(self) -> dict:
        status = {}
        for name, provider in self.providers.items():
            healthy = self.pool.is_healthy(name, provider)
            status[name] = {
                "healthy": healthy,
                "type": type(provider).__name__,
                "enabled": True,
            }
        return status

    def test_provider(self, name: str) -> dict:
        provider = self._get_provider(name)
        if not provider:
            return {"ok": False, "error": f"Provider '{name}' not found"}

        start = time.time()
        result = provider.generate(prompt="Hello", max_tokens=10)
        duration = time.time() - start

        return {
            "ok": result.get("ok", False),
            "provider": name,
            "duration_ms": round(duration * 1000, 1),
            "error": result.get("error"),
        }
