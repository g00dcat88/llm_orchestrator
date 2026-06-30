import json
import logging
import urllib.error
import urllib.request
from typing import Optional

logger = logging.getLogger(__name__)


class BaseLLM:
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        tools: Optional[list] = None,
        messages: Optional[list[dict]] = None,
        **kwargs,
    ) -> dict:
        raise NotImplementedError

    def health_check(self) -> bool:
        return True


def create_llm_from_config(config) -> BaseLLM:
    from providers import create_provider, MockLLM
    from router import RouterLLM

    enabled = [p for p in config.providers if p.enabled]

    if not enabled:
        logger.warning("No providers enabled, using MockLLM")
        return MockLLM()

    if len(enabled) == 1:
        p = enabled[0]
        provider = create_provider({
            "type": p.type,
            "base_url": p.base_url,
            "api_key": p.api_key,
            "model": p.model,
            "temperature": p.temperature,
            "max_tokens": p.max_tokens,
        })
        logger.info("Single provider: %s (%s)", p.name, p.type)
        return provider

    providers_dict = {}
    for p in enabled:
        providers_dict[p.name] = create_provider({
            "type": p.type,
            "base_url": p.base_url,
            "api_key": p.api_key,
            "model": p.model,
            "temperature": p.temperature,
            "max_tokens": p.max_tokens,
        })

    router_cfg = config.router
    router = RouterLLM(
        providers=providers_dict,
        strategy=router_cfg.strategy,
        fallback_chain=router_cfg.fallback_chain,
        classification_provider=router_cfg.classification_provider,
        tool_call_provider=router_cfg.tool_call_provider,
        complexity_threshold=router_cfg.complexity_threshold,
    )

    logger.info(
        "Router: strategy=%s, providers=%s, fallback=%s",
        router_cfg.strategy,
        list(providers_dict.keys()),
        router_cfg.fallback_chain,
    )
    return router
