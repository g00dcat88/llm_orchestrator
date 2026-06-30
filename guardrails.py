import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

PII_PATTERNS = {
    "email": re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"),
    "phone": re.compile(r"(\+7|8)[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}"),
    "snils": re.compile(r"\d{3}[\s\-]?\d{3}[\s\-]?\d{3}\s?\d{2}"),
    "inn": re.compile(r"\d{10}(\d{2})?"),
    "credit_card": re.compile(r"\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}"),
}

PROFANITY_LIST = [
    "хуй", "пизд", "бляд", "ебат", "сука", "нахуй", "пидор", "говно",
]


class GuardrailResult:
    def __init__(self, passed: bool, filtered_text: str, violations: list[str]):
        self.passed = passed
        self.filtered_text = filtered_text
        self.violations = violations

    def __bool__(self):
        return self.passed


class OutputGuardrails:
    def __init__(
        self,
        filter_pii: bool = True,
        filter_profanity: bool = True,
        max_length: int = 10000,
        block_on_violation: bool = False,
    ):
        self.filter_pii = filter_pii
        self.filter_profanity = filter_profanity
        self.max_length = max_length
        self.block_on_violation = block_on_violation

    def check(self, text: str) -> GuardrailResult:
        violations: list[str] = []
        filtered = text

        if self.filter_pii:
            for pii_type, pattern in PII_PATTERNS.items():
                matches = pattern.findall(filtered)
                if matches:
                    violations.append(f"PII:{pii_type}({len(matches)})")
                    filtered = pattern.sub(f"[{pii_type.upper()}]", filtered)

        if self.filter_profanity:
            text_lower = filtered.lower()
            for word in PROFANITY_LIST:
                if word in text_lower:
                    violations.append(f"profanity:{word}")
                    pattern = re.compile(re.escape(word), re.IGNORECASE)
                    filtered = pattern.sub("[filtered]", filtered)

        if len(filtered) > self.max_length:
            violations.append(f"length:{len(filtered)}>{self.max_length}")
            filtered = filtered[: self.max_length] + "..."

        passed = True
        if violations and self.block_on_violation:
            passed = False

        if violations:
            logger.info("Guardrails: %d violations in output", len(violations))

        return GuardrailResult(passed=passed, filtered_text=filtered, violations=violations)


class InputGuardrails:
    def __init__(self, max_length: int = 5000, blocked_patterns: Optional[list[str]] = None):
        self.max_length = max_length
        self.blocked_patterns = [re.compile(p, re.IGNORECASE) for p in (blocked_patterns or [])]

    def check(self, text: str) -> GuardrailResult:
        violations: list[str] = []

        if len(text) > self.max_length:
            violations.append(f"input_too_long:{len(text)}>{self.max_length}")

        for pattern in self.blocked_patterns:
            if pattern.search(text):
                violations.append(f"blocked_pattern:{pattern.pattern}")

        passed = len(violations) == 0
        return GuardrailResult(passed=passed, filtered_text=text, violations=violations)
