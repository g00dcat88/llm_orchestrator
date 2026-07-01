import json
import logging
from gateway import BaseLLM
from response_prompts import CLASSIFICATION_PROMPT, RESPONSE_PROMPTS

logger = logging.getLogger(__name__)


class QueryDispatcher:
    def __init__(self, llm: BaseLLM):
        self.llm = llm

    def classify(self, user_query: str) -> dict:
        try:
            res = self.llm.generate(prompt=user_query, system_prompt=CLASSIFICATION_PROMPT)
            if res.get("ok"):
                content = res["content"].strip()
                if content.startswith("```json"):
                    content = content[7:]
                if content.endswith("```"):
                    content = content[:-3]
                data = json.loads(content.strip())
                logger.info("Классификация: scope=%s, entity=%s", data.get("scope"), data.get("entity_id"))
                return data
        except Exception as e:
            logger.warning("Ошибка парсинга классификации: %s", e)

        return self._fallback_classify(user_query)

    def _fallback_classify(self, query: str) -> dict:
        q = query.lower()
        if any(w in q for w in ("конструктор", "шаблон", "создай задачу", "составить наряд")):
            return {"scope": "task_constructor", "entity_id": None, "reason": "fallback: task_constructor"}
        if any(w in q for w in ("посчитай", "вычисли", "python")):
            return {"scope": "python_sandbox", "entity_id": None, "reason": "fallback: python_sandbox"}
        if any(w in q for w in ("httpbin", "монитор", "проверь сайт")):
            return {"scope": "web_monitor", "entity_id": None, "reason": "fallback: web_monitor"}
        if any(w in q for w in ("схем", "таблиц", "модел", "столбц")):
            return {"scope": "entity_schema", "entity_id": None, "reason": "fallback: entity_schema"}
        if any(w in q for w in ("исходник", "функци", "класс", "метод")):
            return {"scope": "code_search", "entity_id": None, "reason": "fallback: code_search"}
        if any(w in q for w in ("чат", "переписк", "тезис", "отчёт", "структурируй", "собери отчёт")):
            return {"scope": "chat_secretary", "entity_id": None, "reason": "fallback: chat_secretary"}
        if any(w in q for w in ("иванов", "петров", "сотрудник", "командировк", "отпуск")):
            return {"scope": "hr_single", "entity_id": None, "reason": "fallback: hr_single"}
        return {"scope": "general", "entity_id": None, "reason": "fallback: general"}

    def get_response_prompt(self, scope: str) -> str:
        return RESPONSE_PROMPTS.get(scope, RESPONSE_PROMPTS["general"])
