"""File Tools — инструменты для работы с файлами и vision-анализом.

Поддерживает:
- Чтение текстовых файлов (код, TXT, MD, JSON, CSV)
- Анализ изображений через vision (base64 → llama-server с mmproj)
- Список файлов и метаданные
"""
from __future__ import annotations

import base64
import json
import mimetypes
import os
import urllib.request
import urllib.error
from pathlib import Path


# Поддерживаемые расширения для текстового чтения
TEXT_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css", ".scss",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf",
    ".md", ".txt", ".rst", ".csv", ".tsv",
    ".sh", ".bash", ".bat", ".cmd", ".ps1",
    ".sql", ".xml", ".svg",
    ".c", ".cpp", ".h", ".hpp", ".cs", ".java", ".go", ".rs",
    ".rb", ".php", ".swift", ".kt",
    ".env", ".gitignore", ".dockerignore",
    ".log", ".diff", ".patch",
}

# Расширения изображений для vision
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff"}

# Максимальный размер текстового файла (100 KB)
MAX_TEXT_SIZE = 100 * 1024

# Максимальный размер изображения для base64 (20 MB)
MAX_IMAGE_SIZE = 20 * 1024 * 1024


class FileTools:
    """Инструменты для работы с файлами."""

    def __init__(self, uploads_dir: Path, server_url: str = "http://127.0.0.1:8080") -> None:
        self.uploads_dir = uploads_dir
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.server_url = server_url.rstrip("/")

    def read_file(self, path: str) -> str:
        """Прочитать текстовый файл."""
        file_path = self._resolve(path)
        if not file_path:
            return "Ошибка: файл не найден"
        if not file_path.exists():
            return f"Ошибка: файл не существует: {path}"
        if not file_path.is_file():
            return f"Ошибка: это не файл: {path}"

        ext = file_path.suffix.lower()
        if ext not in TEXT_EXTENSIONS:
            return f"Ошибка: неподдерживаемый тип файла '{ext}'. Поддерживаются: {', '.join(sorted(TEXT_EXTENSIONS))}"

        size = file_path.stat().st_size
        if size > MAX_TEXT_SIZE:
            return f"Ошибка: файл слишком большой ({size // 1024} KB). Лимит: {MAX_TEXT_SIZE // 1024} KB"

        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
            return f"[Файл: {file_path.name}]\n{content}"
        except Exception as e:
            return f"Ошибка чтения: {e}"

    def analyze_image(self, path: str, question: str = "Опиши что изображено на этой картинке.") -> str:
        """Проанализировать изображение через vision-модель (mmproj)."""
        file_path = self._resolve(path)
        if not file_path:
            return "Ошибка: файл не найден"
        if not file_path.exists():
            return f"Ошибка: файл не существует: {path}"

        ext = file_path.suffix.lower()
        if ext not in IMAGE_EXTENSIONS:
            return f"Ошибка: файл не является изображением ({ext}). Поддерживаются: {', '.join(sorted(IMAGE_EXTENSIONS))}"

        size = file_path.stat().st_size
        if size > MAX_IMAGE_SIZE:
            return f"Ошибка: изображение слишком большое ({size // (1024*1024)} MB). Лимит: {MAX_IMAGE_SIZE // (1024*1024)} MB"

        # Кодируем в base64
        try:
            with open(file_path, "rb") as f:
                image_data = base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            return f"Ошибка чтения файла: {e}"

        # Определяем MIME тип
        mime_type = mimetypes.guess_type(str(file_path))[0] or "image/png"

        # Отправляем в llama-server через OpenAI-совместимый API
        payload = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": question},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{image_data}"
                            }
                        }
                    ]
                }
            ],
            "max_tokens": 1000,
            "stream": False,
        }

        try:
            req = urllib.request.Request(
                f"{self.server_url}/v1/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                content = result["choices"][0]["message"]["content"].strip()
                return f"[Анализ изображения: {file_path.name}]\n{content}"
        except urllib.error.URLError as e:
            return f"Ошибка подключения к серверу: {e}. Убедитесь, что llama-server запущен с mmproj."
        except Exception as e:
            return f"Ошибка vision-анализа: {e}"

    def list_files(self, directory: str = "") -> str:
        """Список файлов в директории."""
        if directory:
            dir_path = self._resolve(directory)
        else:
            dir_path = self.uploads_dir

        if not dir_path or not dir_path.exists():
            return "Ошибка: директория не найдена"
        if not dir_path.is_dir():
            return "Ошибка: это не директория"

        files = []
        for item in sorted(dir_path.iterdir()):
            if item.name.startswith("."):
                continue
            size = item.stat().st_size
            if item.is_dir():
                files.append(f"  [DIR]  {item.name}/")
            else:
                ext = item.suffix.lower()
                size_str = f"{size // 1024} KB" if size > 1024 else f"{size} B"
                files.append(f"  {ext:6s} {item.name:40s} {size_str}")

        if not files:
            return "Директория пуста"
        return f"[Файлы в {dir_path.name}/]\n" + "\n".join(files)

    def get_file_info(self, path: str) -> str:
        """Метаданные файла."""
        file_path = self._resolve(path)
        if not file_path or not file_path.exists():
            return f"Ошибка: файл не найден: {path}"

        stat = file_path.stat()
        ext = file_path.suffix.lower()
        is_image = ext in IMAGE_EXTENSIONS
        is_text = ext in TEXT_EXTENSIONS

        info = [
            f"Имя: {file_path.name}",
            f"Размер: {stat.st_size} bytes ({stat.st_size // 1024} KB)",
            f"Расширение: {ext}",
            f"Тип: {'изображение' if is_image else 'текст' if is_text else 'другой'}",
            f"Путь: {file_path}",
        ]
        if is_image:
            info.append("Vision: доступен (через mmproj)")
        if is_text:
            info.append("Чтение: доступно")
        return "\n".join(info)

    def save_upload(self, filename: str, data: bytes) -> str:
        """Сохранить загруженный файл."""
        safe_name = filename.replace("/", "_").replace("\\", "_").replace("..", "_")
        target = self.uploads_dir / safe_name
        target.write_bytes(data)
        return str(target)

    def _resolve(self, path: str) -> Path | None:
        """Разрешить путь относительно uploads_dir."""
        p = Path(path)
        if p.is_absolute():
            return p
        # Пробуем относительно uploads_dir
        candidate = self.uploads_dir / path
        if candidate.exists():
            return candidate
        # Пробуем как есть
        return p
