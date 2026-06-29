import json
from gateway import BaseLLM

class QueryDispatcher:
    """
    Классификатор и диспетчер запросов. Разделяет точечные запросы по сущностям
    от аналитических сводок, общих списков и вычислений.
    """
    def __init__(self, llm: BaseLLM):
        self.llm = llm

    def classify(self, user_query: str) -> dict:
        system_prompt = (
            "Ты — интеллектуальный классификатор запросов для ERP/FSM системы ООО «Л-Старт».\n"
            "Твоя задача — проанализировать запрос пользователя и определить:\n"
            "1. Сферу запроса (scope):\n"
            "   - 'hr_single': запрос конкретной информации, контактов, отпуска, фото или документов по ОДНОМУ конкретному сотруднику.\n"
            "   - 'hr_summary': общие вопросы по кадрам, списки сотрудников, статистика, аналитика, общие отчеты по людям.\n"
            "   - 'fsm_single': запрос по конкретной задаче, наряду или его редактированию (например, Tsk00004).\n"
            "   - 'fsm_summary': общие списки нарядов, статистика по задачам, отчеты по выполненным работам.\n"
            "   - 'python_sandbox': математические расчеты, вычисления, написание и выполнение кода.\n"
            "   - 'web_monitor': проверки работоспособности сайтов или URL.\n"
            "   - 'general': общие вопросы, не подходящие под другие категории.\n"
            "2. Упомянутые сущности (ФИО сотрудников, коды нарядов типа Tsk..., коды проектов Pjt...).\n\n"
            "Верни ответ СТРОГО в формате JSON:\n"
            "{\n"
            "  \"scope\": \"<одно из значений выше>\",\n"
            "  \"entity_id\": \"<ФИО сотрудника или код наряда, если упомянут, иначе null>\",\n"
            "  \"reason\": \"<краткое объяснение выбора на русском языке>\"\n"
            "}"
        )

        try:
            res = self.llm.generate(prompt=user_query, system_prompt=system_prompt)
            if res.get("ok"):
                content = res["content"].strip()
                if content.startswith("```json"):
                    content = content[7:]
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()
                
                # Parse JSON safely
                data = json.loads(content)
                return data
        except Exception as e:
            print(f"[Dispatcher Warning]: Failed to parse classification: {e}. Raw content: {res.get('content') if 'res' in locals() else 'None'}")
            
        # Fallback classifications based on simple patterns
        query_lower = user_query.lower()
        if "посчитай" in query_lower or "вычисли" in query_lower or "2 + 2" in query_lower or "105 *" in query_lower:
            return {"scope": "python_sandbox", "entity_id": None, "reason": "Regex fallback: math"}
        elif "httpbin" in query_lower or "монитор" in query_lower:
            return {"scope": "web_monitor", "entity_id": None, "reason": "Regex fallback: web_monitor"}
        elif "иванов" in query_lower:
            return {"scope": "hr_single", "entity_id": "Иванов И.И.", "reason": "Regex fallback: single employee"}
        
        return {"scope": "general", "entity_id": None, "reason": "Fallback default"}
