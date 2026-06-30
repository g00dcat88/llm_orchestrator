import json
import logging
import urllib.error
import urllib.request
from typing import Optional

from gateway import BaseLLM

logger = logging.getLogger(__name__)


class OpenAICompatibleLLM(BaseLLM):
    def __init__(
        self,
        base_url: str,
        api_key: str = "",
        model: str = "",
        temperature: float = 0.7,
        max_tokens: int = -1,
        **kwargs,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        tools: Optional[list] = None,
        messages: Optional[list[dict]] = None,
        **kwargs,
    ) -> dict:
        url = f"{self.base_url}/v1/chat/completions"

        if messages:
            msg_list = list(messages)
        else:
            msg_list = []
            if system_prompt:
                msg_list.append({"role": "system", "content": system_prompt})
            msg_list.append({"role": "user", "content": prompt})

        if system_prompt and not any(m.get("role") == "system" for m in msg_list):
            msg_list.insert(0, {"role": "system", "content": system_prompt})

        payload = {
            "messages": msg_list,
            "temperature": kwargs.get("temperature", self.temperature),
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
        }

        if self.model:
            payload["model"] = self.model

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                message = result["choices"][0]["message"]
                return {
                    "ok": True,
                    "content": message.get("content") or "",
                    "tool_calls": message.get("tool_calls") or [],
                    "raw": result,
                }
        except urllib.error.URLError as e:
            logger.error("[%s] Connection error: %s", self.__class__.__name__, e)
            return {"ok": False, "error": f"Connection error: {e}"}
        except Exception as e:
            logger.error("[%s] Error: %s", self.__class__.__name__, e)
            return {"ok": False, "error": str(e)}

    def health_check(self) -> bool:
        try:
            url = f"{self.base_url}/v1/models"
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status < 400
        except Exception:
            return False


class LlamaServerLLM(OpenAICompatibleLLM):
    def __init__(self, base_url: str = "http://127.0.0.1:8080", api_key: str = "no-key", **kwargs):
        super().__init__(base_url=base_url, api_key=api_key, **kwargs)

    def health_check(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self.base_url}/health", timeout=1.5) as r:
                return r.status < 500
        except Exception:
            return False


class AnthropicLLM(BaseLLM):
    def __init__(
        self,
        api_key: str = "",
        model: str = "claude-sonnet-4-20250514",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ):
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        tools: Optional[list] = None,
        messages: Optional[list[dict]] = None,
        **kwargs,
    ) -> dict:
        url = "https://api.anthropic.com/v1/messages"

        if messages:
            msg_list = []
            for m in messages:
                if m.get("role") == "system":
                    continue
                msg_list.append({"role": m.get("role", "user"), "content": m.get("content", "")})
        else:
            msg_list = [{"role": "user", "content": prompt}]

        payload = {
            "model": self.model,
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            "messages": msg_list,
        }

        if system_prompt:
            payload["system"] = system_prompt

        if kwargs.get("temperature") is not None:
            payload["temperature"] = kwargs["temperature"]
        elif self.temperature is not None:
            payload["temperature"] = self.temperature

        if tools:
            anthropic_tools = []
            for t in tools:
                if t.get("type") == "function":
                    fn = t["function"]
                    anthropic_tools.append({
                        "name": fn["name"],
                        "description": fn.get("description", ""),
                        "input_schema": fn.get("parameters", {}),
                    })
            if anthropic_tools:
                payload["tools"] = anthropic_tools

        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode("utf-8"))

                content = ""
                tool_calls = []
                for block in result.get("content", []):
                    if block.get("type") == "text":
                        content += block.get("text", "")
                    elif block.get("type") == "tool_use":
                        tool_calls.append({
                            "id": block["id"],
                            "type": "function",
                            "function": {
                                "name": block["name"],
                                "arguments": json.dumps(block.get("input", {})),
                            },
                        })

                return {
                    "ok": True,
                    "content": content,
                    "tool_calls": tool_calls,
                    "raw": result,
                }
        except urllib.error.URLError as e:
            logger.error("[Anthropic] Connection error: %s", e)
            return {"ok": False, "error": f"Connection error: {e}"}
        except Exception as e:
            logger.error("[Anthropic] Error: %s", e)
            return {"ok": False, "error": str(e)}

    def health_check(self) -> bool:
        try:
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                data=json.dumps({
                    "model": self.model,
                    "max_tokens": 10,
                    "messages": [{"role": "user", "content": "hi"}],
                }).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status < 400
        except Exception:
            return False


class MockLLM(BaseLLM):
    def generate(self, prompt: str, system_prompt: str = None, tools: list = None, messages: list = None, **kwargs) -> dict:
        pl = prompt.lower()
        if system_prompt and "классификатор" in system_prompt:
            if any(w in pl for w in ("посчитай", "вычисли", "2 + 2")):
                return {"ok": True, "content": '{"scope":"python_sandbox","entity_id":null,"reason":"вычисление"}', "tool_calls": []}
            if any(w in pl for w in ("httpbin", "мониторинг", "проверь")):
                return {"ok": True, "content": '{"scope":"web_monitor","entity_id":null,"reason":"мониторинг"}', "tool_calls": []}
            if any(w in pl for w in ("иванов", "командировк")):
                return {"ok": True, "content": '{"scope":"hr_single","entity_id":null,"reason":"кадры"}', "tool_calls": []}
            if any(w in pl for w in ("схем", "таблиц")):
                return {"ok": True, "content": '{"scope":"entity_schema","entity_id":null,"reason":"схема данных"}', "tool_calls": []}
            if any(w in pl for w in ("исходник", "функци", "класс")):
                return {"ok": True, "content": '{"scope":"code_search","entity_id":null,"reason":"поиск кода"}', "tool_calls": []}
            return {"ok": True, "content": '{"scope":"general","entity_id":null,"reason":"общий"}', "tool_calls": []}
        if "выбери тему" in pl:
            return {"ok": True, "content": "Нейросети в медицине.", "tool_calls": []}
        if "составь подробный план" in pl:
            return {"ok": True, "content": "1. Введение\n2. Методы\n3. Результаты\n4. Выводы", "tool_calls": []}
        if any(w in pl for w in ("посчитай", "вычисли")):
            if tools:
                return {"ok": True, "content": "", "tool_calls": [{"id": "m1", "type": "function", "function": {"name": "execute_python", "arguments": json.dumps({"code": "print(105 * 2 + 10)"})}}]}
        if any(w in pl for w in ("монитор", "проверь")):
            if tools:
                return {"ok": True, "content": "", "tool_calls": [{"id": "m2", "type": "function", "function": {"name": "monitor_web_resource", "arguments": json.dumps({"url": "https://httpbin.org/status/200"})}}]}
        return {"ok": True, "content": "MockLLM: запустите LLM для полноценной работы.", "tool_calls": []}


PROVIDER_TYPES = {
    "openai-compatible": OpenAICompatibleLLM,
    "anthropic": AnthropicLLM,
    "llama-server": LlamaServerLLM,
    "mock": MockLLM,
}


def create_provider(config: dict) -> BaseLLM:
    provider_type = config.get("type", "openai-compatible")
    cls = PROVIDER_TYPES.get(provider_type)
    if not cls:
        raise ValueError(f"Unknown provider type: {provider_type}")
    filtered = {k: v for k, v in config.items() if k != "type"}
    return cls(**filtered)
