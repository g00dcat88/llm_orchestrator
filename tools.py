import ast
import json
import logging
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class Tool:
    def __init__(
        self,
        name: str,
        description: str,
        parameters: dict,
        func: Callable,
        category: str = "general",
    ):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.func = func
        self.category = category

    def to_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def execute(self, **kwargs) -> str:
        try:
            return str(self.func(**kwargs))
        except Exception as e:
            logger.error("Ошибка инструмента %s: %s", self.name, e)
            return f"Ошибка выполнения инструмента {self.name}: {e}"


class PythonSandbox:
    def __init__(self, sandbox_dir: Path, timeout: int = 10):
        self.sandbox_dir = sandbox_dir.resolve()
        self.sandbox_dir.mkdir(exist_ok=True, parents=True)
        self.timeout = timeout

    def _install_missing_imports(self, code: str) -> None:
        try:
            tree = ast.parse(code)
        except Exception:
            return

        imported_modules: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported_modules.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imported_modules.add(node.module.split(".")[0])

        package_mapping = {
            "bs4": "beautifulsoup4",
            "yaml": "pyyaml",
            "sklearn": "scikit-learn",
            "dateutil": "python-dateutil",
            "PIL": "pillow",
        }

        for module in imported_modules:
            try:
                __import__(module)
            except ImportError:
                pip_name = package_mapping.get(module, module)
                logger.info("Автоустановка библиотеки: %s", pip_name)
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", pip_name],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

    def execute_code(self, code: str) -> str:
        self._install_missing_imports(code)
        script_path = (self.sandbox_dir / "temp_script.py").resolve()

        if not str(script_path).startswith(str(self.sandbox_dir)):
            return "Ошибка безопасности: попытка выхода за пределы песочницы!"

        try:
            script_path.write_text(code, encoding="utf-8")
        except Exception as e:
            return f"Ошибка записи кода: {e}"

        try:
            res = subprocess.run(
                [sys.executable, "temp_script.py"],
                cwd=str(self.sandbox_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=self.timeout,
            )
            if script_path.exists():
                script_path.unlink()

            if res.returncode == 0:
                return res.stdout.strip() if res.stdout.strip() else "Скрипт выполнен (вывода нет)."
            return f"Ошибка (код {res.returncode}):\n{res.stderr}"

        except subprocess.TimeoutExpired:
            if script_path.exists():
                script_path.unlink()
            return f"Ошибка: тайм-аут {self.timeout} сек."
        except Exception as e:
            if script_path.exists():
                script_path.unlink()
            return f"Критическая ошибка: {e}"


class ToolRegistry:
    def __init__(self) -> None:
        self.tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self.tools[tool.name] = tool
        logger.debug("Зарегистрирован инструмент: %s (category=%s)", tool.name, tool.category)

    def get_schemas(self) -> list[dict]:
        return [tool.to_schema() for tool in self.tools.values()]

    def get_schemas_for_scope(self, scope: str) -> list[dict]:
        return [
            tool.to_schema()
            for tool in self.tools.values()
            if tool.category == scope or tool.category == "general"
        ]

    def call(self, name: str, arguments: dict) -> str:
        if name not in self.tools:
            return f"Ошибка: инструмент '{name}' не найден."
        return self.tools[name].execute(**arguments)


class WebMonitorTool:
    def __init__(self, log_path: Path):
        self.log_path = log_path
        if not self.log_path.exists():
            self.log_path.parent.mkdir(exist_ok=True, parents=True)
            self.log_path.write_text("[]", encoding="utf-8")

    def monitor(self, url: str) -> str:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        status_code = -1
        message = ""
        success = False
        data_preview = ""
        content_len = 0

        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "LLMOrchestrator-Monitor/1.0"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                status_code = resp.status
                content = resp.read()
                content_len = len(content)
                success = True
                message = "OK"
                try:
                    text = content.decode("utf-8")
                    data_preview = text[:300] + ("..." if len(text) > 300 else "")
                except Exception:
                    data_preview = f"[binary, {content_len} bytes]"
        except urllib.error.HTTPError as e:
            status_code = e.code
            message = f"HTTP {e.code}: {e.reason}"
            data_preview = str(e.code)
        except urllib.error.URLError as e:
            message = f"URL Error: {e.reason}"
            data_preview = "Connection failed"
        except Exception as e:
            message = str(e)
            data_preview = "Internal error"

        record = {
            "timestamp": timestamp,
            "url": url,
            "success": success,
            "status_code": status_code,
            "message": message,
            "data_length": content_len,
        }

        try:
            logs: list = []
            if self.log_path.exists():
                try:
                    logs = json.loads(self.log_path.read_text(encoding="utf-8"))
                except Exception:
                    logs = []
            logs.append(record)
            self.log_path.write_text(
                json.dumps(logs, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception as e:
            logger.error("Ошибка сохранения лога: %s", e)

        return (
            f"[URL]: {url}\n"
            f"[Время]: {timestamp}\n"
            f"[Статус]: {status_code} ({message})\n"
            f"[Данные]: {data_preview}\n"
            f"[Лог]: сохранён в {self.log_path.name}"
        )


class ERPIntegrationTools:
    def __init__(self, base_url: str = "http://localhost:8000", service_token: str = ""):
        self.base_url = base_url.rstrip("/")
        self.service_token = service_token

    def _make_request(
        self,
        url: str,
        data: Optional[bytes] = None,
        headers: Optional[dict] = None,
        method: Optional[str] = None,
    ) -> urllib.request.Request:
        req_headers: dict[str, str] = {}
        if headers:
            req_headers.update(headers)
        if self.service_token:
            req_headers["X-ERP-Service-Token"] = self.service_token
        return urllib.request.Request(url, data=data, headers=req_headers, method=method)

    def _get_json(self, url: str) -> dict | list:
        req = self._make_request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def get_project_card(self, project_code: str) -> str:
        url = f"{self.base_url}/api/v1/hr/projects?search={urllib.parse.quote(project_code)}"
        try:
            data = self._get_json(url)
            if not data:
                return f"Проект {project_code} не найден."
            p = data[0]
            return (
                f"Проект:\n"
                f"- ID: {p.get('id')}\n"
                f"- Код: {p.get('code')}\n"
                f"- Год: {p.get('year')}\n"
                f"- Направление: {p.get('direction_display') or p.get('direction')}\n"
                f"- Заказчик: {p.get('customer') or '—'}\n"
                f"- Договор: {p.get('contract_info') or '—'}\n"
                f"- Статус: {p.get('status_display') or p.get('status') or '—'}\n"
                f"- Оборудование: {p.get('equipment_list') or '—'}\n"
                f"- История:\n{p.get('comments') or '—'}"
            )
        except Exception as e:
            return f"Ошибка получения проекта: {e}"

    def get_trip_details(self, schedule_id: int) -> str:
        url = f"{self.base_url}/api/v1/hr/employee-schedules/{schedule_id}"
        try:
            s = self._get_json(url)
            return (
                f"Командировка:\n"
                f"- ID: {s.get('id')}\n"
                f"- Сотрудник: {s.get('employee_name')}\n"
                f"- Проект: {s.get('project_code')}\n"
                f"- Период: {s.get('start_date', '')[:10]} — {s.get('end_date', '')[:10]}\n"
                f"- Цель: {s.get('notes') or '—'}"
            )
        except Exception as e:
            return f"Ошибка: {e}"

    def append_task_details(self, work_order_id: int, text: str, author_name: str) -> str:
        try:
            wo = self._get_json(f"{self.base_url}/api/v1/hr/work-orders/{work_order_id}")
            current_log = wo.get("history_log") or ""
            date_str = time.strftime("%d.%m.%Y %H:%M")
            new_entry = f"\n\n[{date_str}] {author_name} (Гермес):\n{text}"
            updated_log = current_log.strip() + new_entry

            payload = json.dumps({"history_log": updated_log}).encode("utf-8")
            req = self._make_request(
                f"{self.base_url}/api/v1/hr/work-orders/{work_order_id}",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="PUT",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                json.loads(resp.read().decode("utf-8"))
            return f"Наряд #{work_order_id} дополнен отчётом от {author_name}."
        except Exception as e:
            return f"Ошибка дополнения наряда: {e}"

    def consolidate_to_project(self, project_id: int, summary_text: str) -> str:
        try:
            payload = json.dumps({"comments": summary_text}).encode("utf-8")
            req = self._make_request(
                f"{self.base_url}/api/v1/hr/projects/{project_id}",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="PUT",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                json.loads(resp.read().decode("utf-8"))
            return f"Отчёт сохранён в проекте #{project_id}."
        except Exception as e:
            return f"Ошибка: {e}"

    def get_task_comments(self, work_order_id: int) -> str:
        url = f"{self.base_url}/api/v1/hr/work-orders/{work_order_id}/comments"
        try:
            comments = self._get_json(url)
            if not comments:
                return f"Чат по задаче #{work_order_id} пуст."
            lines = [f"История задачи #{work_order_id}:"]
            for c in comments:
                sys_flag = " [СИСТ.]" if c.get("is_system") else ""
                lines.append(
                    f"- {c.get('sender_name')}{sys_flag} [{c.get('created_at')}]: {c.get('text')}"
                )
            return "\n".join(lines)
        except Exception as e:
            return f"Ошибка: {e}"

    def update_task_summary(self, work_order_id: int, summary_text: str) -> str:
        try:
            payload = json.dumps({"history_log": summary_text}).encode("utf-8")
            req = self._make_request(
                f"{self.base_url}/api/v1/hr/work-orders/{work_order_id}",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="PUT",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                json.loads(resp.read().decode("utf-8"))
            return f"Отчёт по задаче #{work_order_id} обновлён."
        except Exception as e:
            return f"Ошибка: {e}"

    def list_upcoming_trips(self) -> str:
        url = f"{self.base_url}/api/v1/hr/employee-schedules"
        try:
            schedules = self._get_json(url)
            if not schedules:
                return "Нет запланированных командировок."
            lines = ["Командировки:"]
            for s in schedules:
                dtype = s.get("type_display") or s.get("type", "")
                lines.append(
                    f"- ID:{s.get('id')} | {s.get('employee_name')} | "
                    f"Проект: {s.get('project_code')} | "
                    f"{s.get('start_date', '')[:10]}–{s.get('end_date', '')[:10]} | "
                    f"{dtype} | {s.get('notes') or '—'}"
                )
            return "\n".join(lines)
        except Exception as e:
            return f"Ошибка: {e}"

    def search_knowledge_base(self, query: str) -> str:
        current_dir = Path(__file__).resolve().parent
        knowledge_dir = current_dir / "knowledge_base"
        if not knowledge_dir.exists():
            return "База знаний не найдена."

        keywords = [k.lower().strip() for k in query.split() if len(k.strip()) > 2]
        if not keywords:
            return "Запрос слишком короткий."

        results: list[dict] = []
        for fp in knowledge_dir.glob("**/*"):
            if fp.is_file() and fp.suffix in [".txt", ".md"]:
                try:
                    text = fp.read_text(encoding="utf-8")
                    for para in text.split("\n\n"):
                        para = para.strip()
                        if not para:
                            continue
                        score = sum(1 for kw in keywords if kw in para.lower())
                        if score > 0:
                            results.append({"file": fp.name, "text": para, "score": score})
                except Exception:
                    pass

        if not results:
            return "Ничего не найдено в базе знаний."

        results.sort(key=lambda x: x["score"], reverse=True)
        top = results[:3]
        out = [f"Результаты поиска по '{query}':"]
        for r in top:
            out.append(f"--- {r['file']} (score={r['score']}) ---\n{r['text']}\n")
        return "\n".join(out)


class CodeSearchTool:
    def __init__(self, backend_path: str):
        self.backend_path = Path(backend_path) if backend_path else None

    def search(self, query: str, file_pattern: str = "*.py") -> str:
        if not self.backend_path or not self.backend_path.exists():
            return "Путь к исходному коду не настроен."

        try:
            result = subprocess.run(
                ["rg", "-l", "--glob", file_pattern, "-i", query, str(self.backend_path)],
                capture_output=True,
                text=True,
                timeout=10,
            )
            files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
            if not files:
                return f"По запросу '{query}' ничего не найдено в коде."

            output = [f"Найдено в {len(files)} файлах:"]
            for fp in files[:5]:
                try:
                    content = Path(fp).read_text(encoding="utf-8")
                    lines = content.split("\n")
                    matches = []
                    query_lower = query.lower()
                    for i, line in enumerate(lines):
                        if query_lower in line.lower():
                            matches.append(f"  L{i+1}: {line.strip()}")
                            if len(matches) >= 3:
                                break
                    output.append(f"\n{fp}:")
                    output.extend(matches)
                except Exception:
                    output.append(f"\n{fp}: [не удалось прочитать]")

            return "\n".join(output)
        except FileNotFoundError:
            return self._fallback_search(query, file_pattern)
        except Exception as e:
            return f"Ошибка поиска: {e}"

    def _fallback_search(self, query: str, file_pattern: str) -> str:
        if not self.backend_path:
            return "Backend path not configured."
        results: list[str] = []
        query_lower = query.lower()
        for fp in self.backend_path.glob(f"**/{file_pattern}"):
            try:
                text = fp.read_text(encoding="utf-8")
                if query_lower in text.lower():
                    results.append(str(fp))
            except Exception:
                pass
        if not results:
            return f"Ничего не найдено по '{query}'."
        output = [f"Найдено в {len(results)} файлах:"]
        for r in results[:5]:
            output.append(f"  {r}")
        return "\n".join(output)


class EntitySchemaTool:
    def __init__(self, knowledge_dir: Path):
        self.knowledge_dir = knowledge_dir

    def get_schema(self, table_name: str) -> str:
        schema_file = self.knowledge_dir / "database_schema.txt"
        if not schema_file.exists():
            return "Файл схемы БД не найден. Запустите generate_project_maps.py."

        text = schema_file.read_text(encoding="utf-8")
        blocks = text.split("=" * 40)
        for block in blocks:
            if f"Таблица: {table_name}" in block:
                return block.strip()
        return f"Таблица '{table_name}' не найдена в схеме."


class ApiDocsTool:
    def __init__(self, knowledge_dir: Path):
        self.knowledge_dir = knowledge_dir

    def get_docs(self, endpoint_pattern: str) -> str:
        api_file = self.knowledge_dir / "api_routes.txt"
        if not api_file.exists():
            return "Файл API-маршрутов не найден. Запустите generate_project_maps.py."

        text = api_file.read_text(encoding="utf-8")
        blocks = text.split("-" * 30)
        matches = []
        for block in blocks:
            if endpoint_pattern.lower() in block.lower():
                matches.append(block.strip())

        if not matches:
            return f"Эндпоинт '{endpoint_pattern}' не найден."
        return "\n\n".join(matches[:3])


class ListEntitiesTool:
    def __init__(self, knowledge_dir: Path):
        self.knowledge_dir = knowledge_dir

    def list_tables(self) -> str:
        schema_file = self.knowledge_dir / "database_schema.txt"
        if not schema_file.exists():
            return "Файл схемы БД не найден."

        text = schema_file.read_text(encoding="utf-8")
        tables = []
        for line in text.split("\n"):
            if line.startswith("Таблица: "):
                tables.append(line.replace("Таблица: ", "").strip())

        if not tables:
            return "Таблицы не найдены."
        return "Таблицы БД:\n" + "\n".join(f"  - {t}" for t in tables)

    def list_api_endpoints(self) -> str:
        api_file = self.knowledge_dir / "api_routes.txt"
        if not api_file.exists():
            return "Файл API не найден."

        text = api_file.read_text(encoding="utf-8")
        endpoints = []
        for line in text.split("\n"):
            if line.startswith("Маршрут: "):
                endpoints.append(line.replace("Маршрут: ", "").strip())

        if not endpoints:
            return "Эндпоинты не найдены."
        return "API-эндпоинты:\n" + "\n".join(f"  - {e}" for e in endpoints)


class EntityRelationsTool:
    def __init__(self, knowledge_dir: Path):
        self.knowledge_dir = knowledge_dir

    def get_relations(self, table_name: str) -> str:
        schema_file = self.knowledge_dir / "database_schema.txt"
        if not schema_file.exists():
            return "Файл схемы БД не найден."

        text = schema_file.read_text(encoding="utf-8")
        blocks = text.split("=" * 40)
        for block in blocks:
            if f"Таблица: {table_name}" in block:
                relations = []
                for line in block.split("\n"):
                    if "Ссылка на" in line:
                        relations.append(line.strip())
                if not relations:
                    return f"У таблицы '{table_name}' нет внешних ключей."
                return f"Связи таблицы '{table_name}':\n" + "\n".join(
                    f"  - {r}" for r in relations
                )
        return f"Таблица '{table_name}' не найдена."
