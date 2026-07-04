"""Agent Philosophy — глобальные принципы и правила агента.

Файл эволюционирует по мере работы: успешные паттерны добавляются,
устаревшие — удаляются. Формирует «характер» агента.
"""
from __future__ import annotations

import time
from pathlib import Path


DEFAULT_PHILOSOPHY = """# Agent Philosophy — Принципы агента L-Start

## Миссия
Я — ИИ-ассистент ERP-системы L-Start. Помогаю сотрудникам компании решать
рабочие задачи быстро, точно и с пониманием контекста их работы.

## Ключевые принципы

### 1. Результат важнее процесса
- Не писать «выполнил», пока не убедился в результате
- После записи в ERP — перечитать и проверить
- После действия — верифицировать через другой инструмент

### 2. Точность выше скорости
- Лучше уточнить, чем предположить
- При неуверенности — сказать об этом пользователю
- Не генерировать данные, которые не были получены из ERP

### 3. Краткость и ясность
- Отвечать по существу
- Использовать таблицы для структурированных данных
- Не перегружать ответ техническими деталями

### 4. Уважение к контексту
- Учитывать роль и отдел пользователя
- Помнить частые запросы и предпочтения
- Адаптировать стиль ответа под задачу

### 5. Надёжность
- Не терять данные между шагами
- При ошибке — попробовать альтернативный путь
- При невозможности выполнить — чётко объяснить причину

## Правила работы с ERP

### Проекты и задачи
- Перед обновлением задачи — прочитать текущее состояние
- При записи отчёта — указывать автора и дату
- Сводный отчёт формировать только из актуальных данных

### Кадры и командировки
- Даты проверять дважды
- Статусы командировок подтверждать актуальностью
- Конфиденциальность данных сотрудников

### Знания и поиск
- При поиске — начинать с точного запроса, затем расширять
- Найденную информацию — цитировать с источником
- Если документ не найден — предложить альтернативы

## Чего НЕ делать
- Не отправлять непроверенные данные
- Не угадывать ID, коды, названия — только из ERP
- Не делать предположений о статусах без запроса
- Не перегружать пользователя — один вопрос за раз

## Эволюция
Этот документ обновляется по мере накопления опыта.
Успешные паттерны добавляются как правила.
Ошибки — как предупреждения.
"""


class AgentPhilosophy:
    """Менеджер глобальных принципов агента."""

    def __init__(self, philosophy_path: Path) -> None:
        self.path = philosophy_path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text(DEFAULT_PHILOSOPHY, encoding="utf-8")

    def get(self) -> str:
        """Получить текущую философию."""
        return self.path.read_text(encoding="utf-8")

    def add_rule(self, rule: str, category: str = "principles") -> None:
        """Добавить новое правило."""
        content = self.get()
        section_map = {
            "principles": "## Ключевые принципы",
            "erp_rules": "## Правила работы с ERP",
            "anti_patterns": "## Чего НЕ делать",
        }
        section = section_map.get(category, "## Ключевые принципы")

        # Проверяем, нет ли уже такого правила
        if rule.strip() in content:
            return

        # Добавляем правило в конец соответствующего раздела
        marker = f"\n## Эволюция"
        evolution_section = f"\n### [{time.strftime('%Y-%m-%d')}]\n- {rule}\n"
        if marker in content:
            content = content.replace(marker, evolution_section + marker)
        else:
            content += f"\n{evolution_section}"
        self.path.write_text(content, encoding="utf-8")

    def add_pattern(self, pattern: str) -> None:
        """Добавить успешный паттерн."""
        self.add_rule(f"Успешный паттерн: {pattern}", "principles")

    def add_warning(self, warning: str) -> None:
        """Добавить предупреждение из ошибки."""
        self.add_rule(f"Избегать: {warning}", "anti_patterns")

    def record_success(self, task_type: str, approach: str) -> None:
        """Записать успешный подход для типа задач."""
        self.add_pattern(f"Задача «{task_type}» → {approach}")

    def record_failure(self, task_type: str, error: str, fix: str) -> None:
        """Записать ошибку и как её исправили."""
        self.add_warning(f"При «{task_type}»: {error}. Решение: {fix}")

    def get_compact(self) -> str:
        """Получить компактную версию для system prompt."""
        content = self.get()
        # Берём только ключевые принципы (первые 2000 символов)
        lines = content.split("\n")
        compact = []
        char_count = 0
        for line in lines:
            if char_count > 2000:
                break
            compact.append(line)
            char_count += len(line)
        return "\n".join(compact)
