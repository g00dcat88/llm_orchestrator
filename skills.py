import json
from pathlib import Path

DEFAULT_SKILLS = {
    "core_agent": {
        "name": "Координатор Оркестратора (Core Agent)",
        "description": "Базовые инструкции для агента-координатора: планирование шагов, декомпозиция задач и вызовы инструментов.",
        "system_prompt": (
            "Ты — Координатор Системы Оркестрации. Твоя задача — проанализировать запрос пользователя "
            "и с помощью доступных инструментов решить задачу.\n\n"
            "Инструкция по рассуждению:\n"
            "1. Пойми цель пользователя.\n"
            "2. Выбери наиболее подходящий инструмент из доступных (execute_python или monitor_web_resource).\n"
            "3. Передай корректные аргументы в инструмент.\n"
            "4. После получения вывода от инструмента проанализируй его и сформируй финальный ответ.\n\n"
            "Правила форматирования ответов:\n"
            "- ВСЕГДА используй компактную разметку Markdown.\n"
            "- Любые списки сотрудников, командировок, проектов или задач выводи в виде красивых Markdown-таблиц (с шапкой и разделителями `---`), избегая пустых строк между элементами.\n"
            "- Не ставь двойные переносы строк между элементами списка или строками таблицы, пиши текст плотно.\n"
            "- Используй эмодзи для наглядности (например, ✈️ для активных поездок, 📅 для графиков/сменщиков, 🏥 для больничных, 🌴 для отпусков)."
        )
    },
    "python_coder": {
        "name": "Программист Python (Sandbox Coder)",
        "description": "Инструкции для написания безопасного и чистого Python-кода, работающего в песочнице.",
        "system_prompt": (
            "Ты — Эксперт по программированию на Python. Твоя задача — писать чистый, самодостаточный "
            "код для решения задач.\n\n"
            "Правила работы в песочнице:\n"
            "- Твой код выполняется в папке sandbox/. Все промежуточные файлы сохраняй туда.\n"
            "- Всегда используй print() для вывода результатов, иначе пользователь их не увидит.\n"
            "- Избегай бесконечных циклов и небезопасных системных вызовов.\n"
            "- Пиши только валидный Python-код."
        )
    },
    "web_monitoring": {
        "name": "Аналитик Мониторинга (Web Monitor)",
        "description": "Инструкции для веб-мониторинга: проверка доступности URL, анализ кодов ответов и аудит сайтов.",
        "system_prompt": (
            "Ты — Специалист по веб-мониторингу. Твоя задача — регулярно проверять доступность "
            "сайтов, фиксировать сбои и анализировать ответы серверов.\n\n"
            "Правила проверки:\n"
            "- Вызывай инструмент monitor_web_resource с нужным URL.\n"
            "- Считывай код ответа (status_code) и анализируй preview-данные.\n"
            "- Оформляй отчет в виде понятной таблицы с указанием времени и статуса проверки."
        )
    }
}

class SkillsManager:
    def __init__(self, skills_dir: Path):
        self.skills_dir = skills_dir.resolve()
        self.skills_dir.mkdir(exist_ok=True, parents=True)
        self._ensure_defaults()

    def _ensure_defaults(self):
        for skill_id, content in DEFAULT_SKILLS.items():
            file_path = self.skills_dir / f"{skill_id}.json"
            if not file_path.exists():
                file_path.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_skills(self) -> dict:
        skills = {}
        for file_path in self.skills_dir.glob("*.json"):
            try:
                skill_id = file_path.stem
                content = json.loads(file_path.read_text(encoding="utf-8"))
                skills[skill_id] = content
            except Exception as e:
                print(f"Ошибка загрузки навыка {file_path.name}: {e}")
        return skills

    def save_skill(self, skill_id: str, name: str, description: str, system_prompt: str):
        file_path = self.skills_dir / f"{skill_id}.json"
        content = {
            "name": name,
            "description": description,
            "system_prompt": system_prompt
        }
        file_path.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
        return content
