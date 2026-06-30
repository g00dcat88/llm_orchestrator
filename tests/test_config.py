import os
import unittest
from config import Config


class TestConfig(unittest.TestCase):
    def test_defaults(self):
        c = Config()
        self.assertEqual(c.llm_base_url, "http://127.0.0.1:8080")
        self.assertEqual(c.log_level, "INFO")
        self.assertTrue(c.self_critique_enabled)

    def test_from_env(self):
        os.environ["LLM_BASE_URL"] = "http://test:9999"
        os.environ["LOG_LEVEL"] = "DEBUG"
        try:
            c = Config.from_env()
            self.assertEqual(c.llm_base_url, "http://test:9999")
            self.assertEqual(c.log_level, "DEBUG")
        finally:
            del os.environ["LLM_BASE_URL"]
            del os.environ["LOG_LEVEL"]

    def test_from_env_defaults(self):
        for key in ("LLM_BASE_URL", "LOG_LEVEL", "ERP_BASE_URL"):
            os.environ.pop(key, None)
        c = Config.from_env()
        self.assertEqual(c.llm_base_url, "http://127.0.0.1:8080")


if __name__ == "__main__":
    unittest.main()
