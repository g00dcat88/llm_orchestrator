import unittest
from pathlib import Path
from rag import BM25SearchEngine


class TestBM25(unittest.TestCase):
    def setUp(self):
        self.engine = BM25SearchEngine()

    def test_empty_search(self):
        results = self.engine.search("anything")
        self.assertEqual(results, [])

    def test_add_and_search(self):
        self.engine.add_document("doc1.txt", "Python — язык программирования для анализа данных")
        self.engine.add_document("doc2.txt", "JavaScript используется для веб-разработки")
        self.engine.add_document("doc3.txt", "Python и机器学习 — популярное направление")

        results = self.engine.search("Python")
        self.assertGreater(len(results), 0)
        self.assertIn("Python", results[0]["text"])

    def test_relevance_ranking(self):
        self.engine.add_document("a.txt", "кот собака птица")
        self.engine.add_document("b.txt", "кот кот кот")
        results = self.engine.search("кот")
        self.assertEqual(results[0]["source"], "b.txt")

    def test_index_directory(self, tmp_path=None):
        if tmp_path is None:
            tmp_path = Path("test_kb")
            tmp_path.mkdir(exist_ok=True)
            try:
                (tmp_path / "test.txt").write_text("Параграф первый\n\nПараграф второй", encoding="utf-8")
                engine = BM25SearchEngine()
                count = engine.index_directory(tmp_path)
                self.assertGreater(count, 0)
                results = engine.search("параграф")
                self.assertGreater(len(results), 0)
            finally:
                import shutil
                shutil.rmtree(tmp_path, ignore_errors=True)
        else:
            pass

    def test_no_match(self):
        self.engine.add_document("a.txt", "абсолютно нерелевантный текст")
        results = self.engine.search("python java")
        self.assertEqual(len(results), 0)


if __name__ == "__main__":
    unittest.main()
