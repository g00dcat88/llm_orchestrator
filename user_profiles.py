"""User Profile Manager — личность и контекст каждого пользователя.

При первом обращении система опрашивает пользователя о его роли, задачах
и правилах. Информация оптимизируется по мере использования и становится
первоначальным контекстом для всех будущих сессий.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class UserProfile:
    user_id: str
    display_name: str = ""
    role: str = ""            # "инженер", "директор", "бухгалтер" и т.д.
    department: str = ""      # "ПРС", "Проекты", "Кадры" и т.д.
    rules: list[str] = field(default_factory=list)   # правила, которыми пользуется
    preferences: dict = field(default_factory=dict)   # прочие предпочтения
    patterns: list[str] = field(default_factory=list) # извлечённые паттерны из запросов
    created_at: float = 0.0
    last_seen: float = 0.0
    query_count: int = 0
    onboarded: bool = False   # прошёл ли первичный опрос


class UserProfileManager:
    """Менеджер профилей пользователей. Хранит данные в user_profiles/{id}.md"""

    ONBOARDING_PROMPT = """Ты — ИИ-ассистент ERP-системы L-Start. Пользователь обратился к тебе впервые.
Попроси его рассказать о себе:
1. Как его зовут?
2. Какая у него должность/роль?
3. В каком отделе работает?
4. Какие задачи он чаще всего решает через ERP?
5. Какие правила или регламенты он использует в работе?
6. Есть ли особые предпочтения в формате ответов (коротко/подробно, с таблицами, со ссылками)?

Задай эти вопросы дружелюбно, по-русски. Не все сразу — начни с имени и роли."""

    def __init__(self, profiles_dir: Path) -> None:
        self.profiles_dir = profiles_dir
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, UserProfile] = {}

    def _profile_path(self, user_id: str) -> Path:
        safe_id = re.sub(r'[^\w\-]', '_', user_id)
        return self.profiles_dir / f"{safe_id}.md"

    def get_or_create(self, user_id: str) -> UserProfile:
        if user_id in self._cache:
            return self._cache[user_id]
        path = self._profile_path(user_id)
        if path.exists():
            profile = self._parse_md(path.read_text(encoding="utf-8"), user_id)
        else:
            profile = UserProfile(user_id=user_id, created_at=time.time())
        profile.last_seen = time.time()
        profile.query_count += 1
        self._cache[user_id] = profile
        return profile

    def save(self, profile: UserProfile) -> None:
        path = self._profile_path(profile.user_id)
        md = self._to_md(profile)
        path.write_text(md, encoding="utf-8")
        self._cache[profile.user_id] = profile

    def is_onboarded(self, user_id: str) -> bool:
        profile = self.get_or_create(user_id)
        return profile.onboarded

    def get_system_context(self, user_id: str) -> str:
        """Возвращает контекст пользователя для подстановки в system prompt."""
        profile = self.get_or_create(user_id)
        if not profile.onboarded:
            return self.ONBOARDING_PROMPT

        parts = [f"## Пользователь: {profile.display_name or profile.user_id}"]
        if profile.role:
            parts.append(f"- Должность: {profile.role}")
        if profile.department:
            parts.append(f"- Отдел: {profile.department}")
        if profile.rules:
            parts.append("- Правила:")
            for r in profile.rules:
                parts.append(f"  - {r}")
        if profile.preferences:
            parts.append("- Предпочтения:")
            for k, v in profile.preferences.items():
                parts.append(f"  - {k}: {v}")
        if profile.patterns:
            parts.append("- Частые паттерны запросов:")
            for p in profile.patterns[-5:]:  # последние 5
                parts.append(f"  - {p}")
        return "\n".join(parts)

    def record_interaction(self, user_id: str, prompt: str, result: str) -> None:
        """Записать взаимодействие и извлечь паттерны."""
        profile = self.get_or_create(user_id)
        # Извлекаем краткий паттерн из запроса
        pattern = self._extract_pattern(prompt)
        if pattern and pattern not in profile.patterns:
            profile.patterns.append(pattern)
            # Ограничиваем историю паттернов
            if len(profile.patterns) > 20:
                profile.patterns = profile.patterns[-20:]
        self.save(profile)

    def complete_onboarding(self, user_id: str, info: dict) -> None:
        """Завершить онбординг с данными, извлечёнными из ответа модели."""
        profile = self.get_or_create(user_id)
        profile.onboarded = True
        profile.display_name = info.get("name", profile.display_name)
        profile.role = info.get("role", profile.role)
        profile.department = info.get("department", profile.department)
        if "rules" in info:
            profile.rules = info["rules"]
        if "preferences" in info:
            profile.preferences.update(info["preferences"])
        self.save(profile)

    def _extract_pattern(self, prompt: str) -> str:
        """Извлечь краткий паттерн из запроса пользователя."""
        prompt_lower = prompt.lower().strip()
        # Простые эвристики
        if any(w in prompt_lower for w in ["проект", "карточка", "заказ"]):
            return "Работа с проектами"
        if any(w in prompt_lower for w in ["наряд", "задача", "выполнение"]):
            return "Управление задачами"
        if any(w in prompt_lower for w in ["командировка", "график", "отпуск"]):
            return "Кадры/HR"
        if any(w in prompt_lower for w in ["найти", "поиск", "некст"]):
            return "Поиск информации"
        if any(w in prompt_lower for w in ["отчёт", "сводка", "итог"]):
            return "Формирование отчётов"
        if any(w in prompt_lower for w in ["посчитай", "вычисли", "формула"]):
            return "Вычисления"
        return ""

    def _to_md(self, profile: UserProfile) -> str:
        lines = [
            f"# UserProfile: {profile.user_id}",
            "",
            f"**Имя:** {profile.display_name}",
            f"**Роль:** {profile.role}",
            f"**Отдел:** {profile.department}",
            f"**Онбординг:** {'Да' if profile.onboarded else 'Нет'}",
            f"**Создан:** {profile.created_at}",
            f"**Последний визит:** {profile.last_seen}",
            f"**Запросов:** {profile.query_count}",
            "",
        ]
        if profile.rules:
            lines.append("## Правила")
            for r in profile.rules:
                lines.append(f"- {r}")
            lines.append("")
        if profile.preferences:
            lines.append("## Предпочтения")
            for k, v in profile.preferences.items():
                lines.append(f"- **{k}:** {v}")
            lines.append("")
        if profile.patterns:
            lines.append("## Паттерны запросов")
            for p in profile.patterns:
                lines.append(f"- {p}")
            lines.append("")
        return "\n".join(lines)

    def _parse_md(self, content: str, user_id: str) -> UserProfile:
        profile = UserProfile(user_id=user_id)
        lines = content.split("\n")
        current_section = None
        for line in lines:
            line = line.strip()
            if line.startswith("**Имя:**"):
                profile.display_name = line.split(":", 1)[1].strip()
            elif line.startswith("**Роль:**"):
                profile.role = line.split(":", 1)[1].strip()
            elif line.startswith("**Отдел:**"):
                profile.department = line.split(":", 1)[1].strip()
            elif line.startswith("**Онбординг:**"):
                profile.onboarded = line.split(":", 1)[1].strip() == "Да"
            elif line.startswith("**Создан:**"):
                try:
                    profile.created_at = float(line.split(":", 1)[1].strip())
                except ValueError:
                    pass
            elif line.startswith("**Последний визит:**"):
                try:
                    profile.last_seen = float(line.split(":", 1)[1].strip())
                except ValueError:
                    pass
            elif line.startswith("**Запросов:**"):
                try:
                    profile.query_count = int(line.split(":", 1)[1].strip())
                except ValueError:
                    pass
            elif line == "## Правила":
                current_section = "rules"
            elif line == "## Предпочтения":
                current_section = "preferences"
            elif line == "## Паттерны запросов":
                current_section = "patterns"
            elif line.startswith("- ") and current_section:
                item = line[2:].strip()
                if current_section == "rules":
                    profile.rules.append(item)
                elif current_section == "patterns":
                    profile.patterns.append(item)
                elif current_section == "preferences" and ":" in item:
                    k, v = item.split(":", 1)
                    profile.preferences[k.strip()] = v.strip()
        return profile
