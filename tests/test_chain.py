import unittest
from gateway import BaseLLM
from prompt import PromptTemplate
from chain import LLMChain


class MockLLM(BaseLLM):
    def __init__(self, responses=None):
        self.responses = responses or []
        self.call_count = 0

    def generate(self, prompt, system_prompt=None, tools=None, **kwargs):
        if self.call_count < len(self.responses):
            r = self.responses[self.call_count]
            self.call_count += 1
            return {"ok": True, "content": r, "tool_calls": []}
        return {"ok": True, "content": "default", "tool_calls": []}


class TestLLMChain(unittest.TestCase):
    def test_single_step(self):
        llm = MockLLM(["result"])
        chain = LLMChain(llm)
        chain.add_step("step1", PromptTemplate("do {x}", ["x"]), "out")
        result = chain.run({"x": "something"})
        self.assertEqual(result["out"], "result")

    def test_multi_step(self):
        llm = MockLLM(["topic1", "plan1"])
        chain = LLMChain(llm)
        chain.add_step("s1", PromptTemplate("pick {domain}", ["domain"]), "topic")
        chain.add_step("s2", PromptTemplate("plan for {topic}", ["topic"]), "plan")
        result = chain.run({"domain": "AI"})
        self.assertEqual(result["topic"], "topic1")
        self.assertEqual(result["plan"], "plan1")

    def test_step_error(self):
        llm = MockLLM()
        llm.responses = ["not_used"]
        original_generate = llm.generate
        def failing_generate(prompt, system_prompt=None, tools=None, **kwargs):
            return {"ok": False, "error": "fail", "tool_calls": []}
        llm.generate = failing_generate
        chain = LLMChain(llm)
        chain.add_step("fail", PromptTemplate("x"), "out")
        with self.assertRaises(RuntimeError):
            chain.run({})


if __name__ == "__main__":
    unittest.main()
