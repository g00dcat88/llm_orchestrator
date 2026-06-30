import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_SKILLS = {
    "core_agent": {
        "name": "Координатор Оркестратора",
        "description": "Базовые инструкции для агента-координатора.",
        "system_prompt": (
            "Ты — Координатор Системы Оркестрации. Решай задачи с помощью доступных инструментов.\n"
            "1. Пойми цель.\n2. Выбери инструмент.\n3. Передай аргументы.\n4. Сформируй ответ.\n\n"
            "Формат: компактный Markdown. Списки — таблицы. Эмодзи для наглядности."
        ),
    },
    "python_coder": {
        "name": "Программист Python",
        "description": "Инструкции для Python-кода в песочнице.",
        "system_prompt": (
            "Ты — Python-программист. Пиши чистый самодостаточный код.\n"
            "Правила: sandbox/, print() для вывода, без бесконечных циклов."
        ),
    },
    "web_monitoring": {
        "name": "Аналитик Мониторинга",
        "description": "Проверка доступности URL.",
        "system_prompt": (
            "Ты — специалист по веб-мониторингу. Проверяй URL, анализируй ответы, фиксируй сбои."
        ),
    },
    "hr_assistant": {
        "name": "HR-Ассистент",
        "description": "Кадры, командировки, отпуска.",
        "system_prompt": (
            "Ты — HR-ассистент Л-Старт. Помогай с кадрами, командировками, отпусками.\n"
            "Инструменты: list_upcoming_trips, get_trip_details, search_knowledge_base.\n"
            "Эмодзи: ✈️ командировка, 📅 график, 🏥 больничный, 🌴 отпуск."
        ),
    },
    "projects_assistant": {
        "name": "Ассистент по Проектам",
        "description": "Наряды, проекты, отчёты.",
        "system_prompt": (
            "Ты — ассистент по нарядам и проектам Л-Старт.\n"
            "Инструменты: get_project_card, append_task_details, consolidate_to_project.\n"
            "Для записей — предупреждай о безопасном изменении данных."
        ),
    },
    "task_constructor_assistant": {
        "name": "Конструктор Задач",
        "description": "Создание задач через наводящие вопросы.",
        "system_prompt": (
            "Ты — конструктор задач Л-Старт. Задавай вопросы, собирай ТЗ, формируй JSON для формы."
        ),
    },
}


class SkillsManager:
    def __init__(self, skills_dir: Path):
        self.skills_dir = skills_dir.resolve()
        self.skills_dir.mkdir(exist_ok=True, parents=True)
        self._ensure_defaults()

    def _ensure_defaults(self) -> None:
        for skill_id, content in DEFAULT_SKILLS.items():
            fp = self.skills_dir / f"{skill_id}.json"
            if not fp.exists():
                fp.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_skills(self) -> dict[str, dict]:
        skills: dict[str, dict] = {}
        for fp in self.skills_dir.glob("*.json"):
            try:
                skills[fp.stem] = json.loads(fp.read_text(encoding="utf-8"))
            except Exception as e:
                logger.error("Ошибка загрузки навыка %s: %s", fp.name, e)
        return skills

    def get_skill(self, skill_id: str) -> dict | None:
        fp = self.skills_dir / f"{skill_id}.json"
        if fp.exists():
            try:
                return json.loads(fp.read_text(encoding="utf-8"))
            except Exception:
                return None
        return None

    def save_skill(self, skill_id: str, name: str, description: str, system_prompt: str) -> dict:
        content = {"name": name, "description": description, "system_prompt": system_prompt}
        fp = self.skills_dir / f"{skill_id}.json"
        fp.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
        return content
