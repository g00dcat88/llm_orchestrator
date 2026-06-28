import json
import urllib.request
import urllib.error

class BaseLLM:
    def generate(self, prompt: str, system_prompt: str = None, tools: list = None, **kwargs) -> dict:
        """
        Отправка запроса к языковой модели.
        """
        raise NotImplementedError

class LlamaServerLLM(BaseLLM):
    """
    Интерфейс к локальной модели через API (совместимый с OpenAI API, например llama-server или vLLM).
    """
    def __init__(self, base_url: str = "http://127.0.0.1:8080", api_key: str = "no-key"):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key

    def generate(self, prompt: str, system_prompt: str = None, tools: list = None, **kwargs) -> dict:
        url = f"{self.base_url}/v1/chat/completions"
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_tokens", -1)
        }
        
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                choice = result["choices"][0]
                message = choice["message"]
                
                return {
                    "ok": True,
                    "content": message.get("content") or "",
                    "tool_calls": message.get("tool_calls") or [],
                    "raw": result
                }
        except urllib.error.URLError as e:
            return {"ok": False, "error": f"Ошибка соединения: {e}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}
