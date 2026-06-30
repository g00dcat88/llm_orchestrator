import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

CHARS_PER_TOKEN_RU = 3.5
CHARS_PER_TOKEN_EN = 4.5


def estimate_tokens(text: str) -> int:
    ru_chars = len(re.findall(r"[а-яА-ЯёЁ]", text))
    en_chars = len(re.findall(r"[a-zA-Z]", text))
    other_chars = len(text) - ru_chars - en_chars
    return int(ru_chars / CHARS_PER_TOKEN_RU + en_chars / CHARS_PER_TOKEN_EN + other_chars / 4)


class TokenBudget:
    def __init__(self, max_context: int = 4096, reserve_output: int = 1024):
        self.max_context = max_context
        self.reserve_output = reserve_output
        self.available = max_context - reserve_output

    def can_fit(self, text: str) -> bool:
        return estimate_tokens(text) <= self.available

    def remaining(self, text: str = "") -> int:
        used = estimate_tokens(text)
        return max(0, self.available - used)

    def truncate_to_fit(self, text: str, prefix: str = "", suffix: str = "") -> str:
        prefix_tokens = estimate_tokens(prefix)
        suffix_tokens = estimate_tokens(suffix)
        budget = self.available - prefix_tokens - suffix_tokens

        if budget <= 0:
            return prefix + suffix

        current_tokens = estimate_tokens(text)
        if current_tokens <= budget:
            return prefix + text + suffix

        chars_needed = int(budget * CHARS_PER_TOKEN_RU)
        if len(text) <= chars_needed:
            return prefix + text + suffix

        truncated = text[:chars_needed] + "..."
        return prefix + truncated + suffix


class TokenManager:
    def __init__(self, max_context: int = 4096, reserve_output: int = 1024):
        self.max_context = max_context
        self.reserve_output = reserve_output

    def create_budget(self) -> TokenBudget:
        return TokenBudget(self.max_context, self.reserve_output)

    def prepare_messages(
        self,
        messages: list[dict],
        system_prompt: Optional[str] = None,
        max_tokens: int = 0,
    ) -> list[dict]:
        budget = TokenBudget(self.max_context, max_tokens or self.reserve_output)

        result: list[dict] = []
        system_tokens = 0

        if system_prompt:
            system_tokens = estimate_tokens(system_prompt)
            budget.available -= system_tokens
            result.append({"role": "system", "content": system_prompt})

        for msg in reversed(messages):
            msg_tokens = estimate_tokens(msg.get("content", ""))
            if budget.remaining() >= msg_tokens:
                result.insert(len(result) - (0 if system_prompt else 0), msg)
                budget.available -= msg_tokens
            else:
                break

        if not result or result[0].get("role") != "system":
            if system_prompt:
                result.insert(0, {"role": "system", "content": system_prompt})

        return result

    def summarize_if_needed(self, text: str, max_tokens: int = 500) -> str:
        current = estimate_tokens(text)
        if current <= max_tokens:
            return text

        ratio = max_tokens / current
        target_chars = int(len(text) * ratio * 0.9)
        return text[:target_chars] + "\n\n[... суммаризовано ...]"
