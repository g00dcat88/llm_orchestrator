import unittest
from gateway import BaseLLM
from dispatcher import QueryDispatcher


class MockLLM(BaseLLM):
    def __init__(self, response=None):
        self.response = response or {}

    def generate(self, prompt, system_prompt=None, tools=None, **kwargs):
        if self.response:
            return {"ok": True, "content": str(self.response), "tool_calls": []}
        return {"ok": True, "content": '{"scope":"general","entity_id":null,"reason":"test"}', "tool_calls": []}


class TestQueryDispatcher(unittest.TestCase):
    def test_classify(self):
        llm = MockLLM()
        dispatcher = QueryDispatcher(llm)
        result = dispatcher.classify("test query")
        self.assertIn("scope", result)

    def test_fallback_task_constructor(self):
        llm = MockLLM()
        llm.response = "invalid json {{{"
        dispatcher = QueryDispatcher(llm)
        result = dispatcher.classify("создай задачу")
        self.assertEqual(result["scope"], "task_constructor")

    def test_fallback_python(self):
        llm = MockLLM()
        llm.response = "invalid"
        dispatcher = QueryDispatcher(llm)
        result = dispatcher.classify("посчитай сумму")
        self.assertEqual(result["scope"], "python_sandbox")

    def test_fallback_entity_schema(self):
        llm = MockLLM()
        llm.response = "invalid"
        dispatcher = QueryDispatcher(llm)
        result = dispatcher.classify("покажи схему таблицы")
        self.assertEqual(result["scope"], "entity_schema")

    def test_fallback_general(self):
        llm = MockLLM()
        llm.response = "invalid"
        dispatcher = QueryDispatcher(llm)
        result = dispatcher.classify("какая погода?")
        self.assertEqual(result["scope"], "general")

    def test_get_response_prompt(self):
        dispatcher = QueryDispatcher(MockLLM())
        prompt = dispatcher.get_response_prompt("hr_single")
        self.assertIn("HR", prompt)
        prompt = dispatcher.get_response_prompt("unknown_scope")
        self.assertIn("ассистент", prompt.lower())


if __name__ == "__main__":
    unittest.main()
