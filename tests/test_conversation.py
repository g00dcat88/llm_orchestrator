import unittest
from conversation import ConversationBuffer


class TestConversationBuffer(unittest.TestCase):
    def test_add_and_get(self):
        buf = ConversationBuffer(max_messages=5)
        buf.add_user_message("Привет")
        buf.add_assistant_message("Здравствуйте")
        self.assertEqual(len(buf.messages), 2)

    def test_max_messages(self):
        buf = ConversationBuffer(max_messages=3)
        for i in range(5):
            buf.add_user_message(f"msg {i}")
        self.assertEqual(len(buf.messages), 3)
        self.assertEqual(buf.messages[0]["content"], "msg 2")

    def test_context_string(self):
        buf = ConversationBuffer()
        buf.add_user_message("Вопрос")
        buf.add_assistant_message("Ответ")
        ctx = buf.get_context_string()
        self.assertIn("Пользователь: Вопрос", ctx)
        self.assertIn("Ассистент: Ответ", ctx)

    def test_last_user_message(self):
        buf = ConversationBuffer()
        buf.add_user_message("первый")
        buf.add_assistant_message("ответ")
        buf.add_user_message("второй")
        self.assertEqual(buf.get_last_user_message(), "второй")

    def test_profile(self):
        buf = ConversationBuffer()
        buf.update_profile("role", "HR")
        self.assertEqual(buf.user_profile["role"], "HR")
        self.assertIn("HR", buf.get_profile_summary())

    def test_clear(self):
        buf = ConversationBuffer()
        buf.add_user_message("test")
        buf.update_profile("k", "v")
        buf.clear()
        self.assertEqual(len(buf.messages), 0)
        self.assertEqual(len(buf.user_profile), 0)

    def test_empty_context(self):
        buf = ConversationBuffer()
        self.assertEqual(buf.get_context_string(), "")


if __name__ == "__main__":
    unittest.main()
