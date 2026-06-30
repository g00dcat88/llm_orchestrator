import unittest
from prompt import PromptTemplate


class TestPromptTemplate(unittest.TestCase):
    def test_render(self):
        t = PromptTemplate("Привет, {name}!", ["name"])
        self.assertEqual(t.render(name="Мир"), "Привет, Мир!")

    def test_missing_variable(self):
        t = PromptTemplate("{a} и {b}", ["a", "b"])
        with self.assertRaises(ValueError):
            t.render(a="1")

    def test_no_required(self):
        t = PromptTemplate("Статичный текст")
        self.assertEqual(t.render(), "Статичный текст")

    def test_multiple_vars(self):
        t = PromptTemplate("{x} + {y} = {z}", ["x", "y", "z"])
        result = t.render(x="1", y="2", z="3")
        self.assertEqual(result, "1 + 2 = 3")


if __name__ == "__main__":
    unittest.main()
