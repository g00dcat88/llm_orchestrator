from collections import deque
from typing import Optional


class ConversationBuffer:
    def __init__(self, max_messages: int = 20, user_id: str = None):
        self.messages: deque[dict] = deque(maxlen=max_messages)
        self.user_profile: dict = {}
        self.user_id = user_id

    def add_user_message(self, content: str) -> None:
        self.messages.append({"role": "user", "content": content})

    def add_assistant_message(self, content: str) -> None:
        self.messages.append({"role": "assistant", "content": content})

    def get_context_string(self) -> str:
        if not self.messages:
            return ""
        lines = []
        for m in self.messages:
            prefix = "Пользователь" if m["role"] == "user" else "Ассистент"
            lines.append(f"{prefix}: {m['content']}")
        return "\n".join(lines)

    def get_messages_for_llm(self) -> list[dict]:
        return list(self.messages)

    def get_last_user_message(self) -> Optional[str]:
        for m in reversed(self.messages):
            if m["role"] == "user":
                return m["content"]
        return None

    def update_profile(self, key: str, value) -> None:
        self.user_profile[key] = value

    def get_profile_summary(self) -> str:
        if not self.user_profile:
            return ""
        parts = [f"{k}: {v}" for k, v in self.user_profile.items()]
        return "Профиль пользователя: " + ", ".join(parts)

    def clear(self) -> None:
        self.messages.clear()
        self.user_profile.clear()
