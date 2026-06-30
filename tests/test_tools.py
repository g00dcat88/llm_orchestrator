import unittest
from pathlib import Path
from tools import Tool, ToolRegistry, PythonSandbox, CodeSearchTool, EntitySchemaTool, ApiDocsTool, ListEntitiesTool, EntityRelationsTool


class TestTool(unittest.TestCase):
    def test_execute(self):
        t = Tool("adder", "adds", {"type": "object", "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}}}, func=lambda a, b: a + b)
        self.assertEqual(t.execute(a=2, b=3), "5")

    def test_execute_error(self):
        t = Tool("fail", "fails", {}, func=lambda: 1 / 0)
        result = t.execute()
        self.assertIn("Ошибка", result)

    def test_to_schema(self):
        t = Tool("test", "desc", {"type": "object", "properties": {}}, func=lambda: "")
        schema = t.to_schema()
        self.assertEqual(schema["type"], "function")
        self.assertEqual(schema["function"]["name"], "test")


class TestToolRegistry(unittest.TestCase):
    def test_register_and_call(self):
        reg = ToolRegistry()
        t = Tool("inc", "increment", {"type": "object", "properties": {"x": {"type": "integer"}}}, func=lambda x: x + 1)
        reg.register(t)
        self.assertEqual(reg.call("inc", {"x": 5}), "6")

    def test_unknown_tool(self):
        reg = ToolRegistry()
        self.assertIn("не найден", reg.call("nope", {}))

    def test_scope_filter(self):
        reg = ToolRegistry()
        reg.register(Tool("a", "", {}, func=lambda: "", category="hr_single"))
        reg.register(Tool("b", "", {}, func=lambda: "", category="general"))
        schemas = reg.get_schemas_for_scope("hr_single")
        names = [s["function"]["name"] for s in schemas]
        self.assertIn("a", names)
        self.assertIn("b", names)

    def test_scope_excludes(self):
        reg = ToolRegistry()
        reg.register(Tool("a", "", {}, func=lambda: "", category="fsm_single"))
        schemas = reg.get_schemas_for_scope("hr_single")
        names = [s["function"]["name"] for s in schemas]
        self.assertNotIn("a", names)


class TestPythonSandbox(unittest.TestCase):
    def test_basic_execution(self):
        sandbox = PythonSandbox(Path("test_sandbox"), timeout=5)
        result = sandbox.execute_code("print(2 + 2)")
        self.assertEqual(result, "4")
        import shutil
        shutil.rmtree("test_sandbox", ignore_errors=True)

    def test_syntax_error(self):
        sandbox = PythonSandbox(Path("test_sandbox2"), timeout=5)
        result = sandbox.execute_code("def broken(")
        self.assertIn("Ошибка", result)
        import shutil
        shutil.rmtree("test_sandbox2", ignore_errors=True)


class TestEntityTools(unittest.TestCase):
    def setUp(self):
        self.kb = Path("test_kb_tools")
        self.kb.mkdir(exist_ok=True)
        sep = "\n" + "=" * 40 + "\n"
        (self.kb / "database_schema.txt").write_text(
            sep.join([
                "=== SCHEMA ===\n\nТаблица: users\n  - id: INTEGER NOT NULL (PRIMARY KEY)\n  - name: TEXT NOT NULL\n  - project_id: INTEGER -> Ссылка на projects(id)",
                "\n\nТаблица: projects\n  - id: INTEGER NOT NULL (PRIMARY KEY)\n  - code: TEXT NOT NULL",
                "",
            ]),
            encoding="utf-8",
        )
        (self.kb / "api_routes.txt").write_text(
            "Маршрут: /api/v1/users\nМетоды: GET\nОписание: Список пользователей\n"
            "-" * 30 + "\n\nМаршрут: /api/v1/projects\nМетоды: GET, POST\nОписание: Проекты\n",
            encoding="utf-8",
        )

    def tearDown(self):
        import shutil
        shutil.rmtree(self.kb, ignore_errors=True)

    def test_entity_schema(self):
        tool = EntitySchemaTool(self.kb)
        result = tool.get_schema("users")
        self.assertIn("Таблица: users", result)
        self.assertIn("project_id", result)

    def test_entity_schema_not_found(self):
        tool = EntitySchemaTool(self.kb)
        result = tool.get_schema("nonexistent")
        self.assertIn("не найдена", result)

    def test_api_docs(self):
        tool = ApiDocsTool(self.kb)
        result = tool.get_docs("users")
        self.assertIn("/api/v1/users", result)

    def test_list_tables(self):
        tool = ListEntitiesTool(self.kb)
        result = tool.list_tables()
        self.assertIn("users", result)
        self.assertIn("projects", result)

    def test_list_endpoints(self):
        tool = ListEntitiesTool(self.kb)
        result = tool.list_api_endpoints()
        self.assertIn("/api/v1/users", result)

    def test_relations(self):
        tool = EntityRelationsTool(self.kb)
        result = tool.get_relations("users")
        self.assertIn("projects", result)

    def test_relations_none(self):
        tool = EntityRelationsTool(self.kb)
        result = tool.get_relations("projects")
        self.assertIn("нет внешних ключей", result)


if __name__ == "__main__":
    unittest.main()
