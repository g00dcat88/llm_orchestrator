import json
import urllib.request
from pathlib import Path
from gateway import LlamaServerLLM, BaseLLM
from prompt import PromptTemplate
from chain import LLMChain
from tools import Tool, ToolRegistry, PythonSandbox, WebMonitorTool

# --- Вспомогательный Mock-провайдер для автономной работы ---
class MockLLM(BaseLLM):
    """
    Mock-модель, которая имитирует ответы LLM, если локальный llama-server выключен.
    Это позволяет продемонстрировать логику работы оркестратора без запущенного сервера.
    """
    def generate(self, prompt: str, system_prompt: str = None, tools: list = None, **kwargs) -> dict:
        prompt_lower = prompt.lower()
        
        # 1. Ответы для последовательной цепочки (Chain)
        if "выбери тему" in prompt_lower:
            return {
                "ok": True,
                "content": "Нейросети в медицине: диагностика заболеваний на ранних стадиях.",
                "tool_calls": []
            }
        elif "составь подробный план" in prompt_lower:
            return {
                "ok": True,
                "content": "1. Введение: текущее состояние ИИ в медицине.\n2. Применение сверточных нейросетей для анализа МРТ.\n3. Перспективы внедрения в клиниках.\n4. Проблемы конфиденциальности данных.",
                "tool_calls": []
            }
            
        # 2. Имитация вызова инструмента (Function Calling)
        elif "посчитай" in prompt_lower or "вычисли" in prompt_lower or "2 + 2" in prompt_lower:
            if tools:
                return {
                    "ok": True,
                    "content": "",
                    "tool_calls": [{
                        "id": "call_mock_1",
                        "type": "function",
                        "function": {
                            "name": "execute_python",
                            "arguments": json.dumps({"code": "print(105 * 2 + 10)"})
                        }
                    }]
                }
        elif "монитор" in prompt_lower or "проверь состояние" in prompt_lower or "httpbin.org" in prompt_lower:
            if tools:
                return {
                    "ok": True,
                    "content": "",
                    "tool_calls": [{
                        "id": "call_mock_2",
                        "type": "function",
                        "function": {
                            "name": "monitor_web_resource",
                            "arguments": json.dumps({"url": "https://httpbin.org/status/200"})
                        }
                    }]
                }
        
        # 3. Финальный ответ после выполнения инструмента
        elif "выполнил задачу и вернул следующий результат" in prompt_lower:
            if "monitor_web_resource" in prompt_lower or "проверки" in prompt_lower or "статус" in prompt_lower:
                return {
                    "ok": True,
                    "content": "Я проверил веб-ресурс с помощью инструмента monitor_web_resource. Ресурс вернул статус 200 (Успешно), подтверждающий его корректную работу. Запись о проверке успешно занесена в лог.",
                    "tool_calls": []
                }
            # Извлекаем результат выполнения
            res_content = "220"
            for line in prompt.split('\n'):
                if line.strip() and not line.startswith("Инструмент") and not line.startswith("Пожалуйста"):
                    res_content = line.strip()
            return {
                "ok": True,
                "content": f"Результат вычислений равен {res_content}.",
                "tool_calls": []
            }
            
        return {
            "ok": True,
            "content": "Это тестовый ответ от MockLLM. Для полноценной генерации запустите llama-server.",
            "tool_calls": []
        }

# --- Проверка активности сервера ---
def is_server_online(url: str) -> bool:
    try:
        with urllib.request.urlopen(url + "/health", timeout=1.5) as r:
            return r.status < 500
    except:
        return False

# --- Логика Агентного цикла рассуждения (ReAct Loop) ---
def run_agentic_loop(llm: BaseLLM, registry: ToolRegistry, user_prompt: str, max_retries: int = 3, system_prompt: str = None, log_callback = None):
    def log(msg):
        if log_callback:
            log_callback(msg)
        print(msg)
        
    log("==========================================")
    log(f"[Агент] Получен запрос: {user_prompt}")
    log("==========================================")
    
    if not system_prompt:
        system_prompt = "Ты полезный ассистент, который может выполнять код на Python для решения математических задач."
    
    # 1. Первый запрос к модели
    res = llm.generate(prompt=user_prompt, system_prompt=system_prompt, tools=registry.get_schemas())
    if not res["ok"]:
        log(f"[Ошибка LLM]: {res['error']}")
        return res

    retries = 0
    # Цикл выполнения инструментов, если модель решила их вызвать
    while res.get("tool_calls") and retries < max_retries:
        for tool_call in res["tool_calls"]:
            fn_name = tool_call["function"]["name"]
            try:
                fn_args = json.loads(tool_call["function"]["arguments"])
            except Exception as e:
                fn_args = {"code": tool_call["function"]["arguments"]} # Fallback при невалидном JSON
                
            log(f"\n[Агент] [Инструмент] Решил вызвать инструмент '{fn_name}' со следующими параметрами:")
            log(f"---> {json.dumps(fn_args, indent=2, ensure_ascii=False)}")
            
            # Выполняем инструмент через реестр
            tool_output = registry.call(fn_name, fn_args)
            log(f"[Инструмент '{fn_name}'] [Вывод]:\n{tool_output}")
            
            # 2. Возвращаем результат выполнения инструмента обратно в LLM
            feedback_prompt = (
                f"Инструмент '{fn_name}' выполнил задачу и вернул следующий результат:\n"
                f"{tool_output}\n"
                f"Пожалуйста, сформируй итоговый ответ для пользователя на основе этого результата."
            )
            res = llm.generate(prompt=feedback_prompt, system_prompt=system_prompt, tools=registry.get_schemas())
            if not res["ok"]:
                log(f"[Ошибка LLM при обработке обратной связи]: {res['error']}")
                return res
                
        retries += 1

    log(f"\n[Агент] Итоговый ответ:\n{res['content']}")
    log("==========================================\n")
    return res



def main():
    # Определение путей песочницы
    current_dir = Path(__file__).resolve().parent
    sandbox_dir = current_dir / "sandbox"
    
    print(f"Настройка песочницы выполнения кода в папке:\n-> {sandbox_dir}\n")
    sandbox = PythonSandbox(sandbox_dir)
    
    # Инициализация реестра инструментов и регистрация песочницы Python
    registry = ToolRegistry()
    
    execute_python_tool = Tool(
        name="execute_python",
        description="Выполняет код на Python в изолированной папке песочницы и возвращает stdout/stderr. Используйте для вычислений или обработки данных.",
        parameters={
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Исходный код программы на Python для выполнения."
                }
            },
            "required": ["code"]
        },
        func=sandbox.execute_code
    )
    
    registry.register(execute_python_tool)
    
    # Инициализация WebMonitorTool
    monitor_log_path = sandbox_dir / "monitoring_log.json"
    web_monitor = WebMonitorTool(monitor_log_path)
    
    web_monitor_tool = Tool(
        name="monitor_web_resource",
        description="Проверяет состояние указанного веб-ресурса (URL), получает preview-данные и записывает проверку в журнал логов.",
        parameters={
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Полный URL-адрес веб-ресурса для проверки (например: https://httpbin.org/status/200)."
                }
            },
            "required": ["url"]
        },
        func=web_monitor.monitor
    )
    
    registry.register(web_monitor_tool)
    
    # Инициализация LLM Gateway
    server_url = "http://127.0.0.1:8080" # Порт по умолчанию для llama-server
    if is_server_online(server_url):
        print("[+] Локальный llama-server обнаружен и находится в сети. Запуск в реальном режиме.")
        llm = LlamaServerLLM(base_url=server_url)
    else:
        print("[-] Локальный llama-server не найден на 8080. Запуск в режиме симуляции (MockLLM).")
        llm = MockLLM()

    # --- ДЕМОНСТРАЦИЯ 1: Последовательная цепочка промптов (LLMChain) ---
    print("\n=== ДЕМОНСТРАЦИЯ 1: Последовательная цепочка промптов (LLMChain) ===")
    
    template_topic = PromptTemplate(
        template="Выбери интересную и актуальную тему для исследования в области {domain}.",
        required_variables=["domain"]
    )
    
    template_plan = PromptTemplate(
        template="Составь подробный план статьи на тему: '{selected_topic}'.",
        required_variables=["selected_topic"]
    )
    
    chain = LLMChain(llm)
    chain.add_step(
        name="Выбор темы",
        template=template_topic,
        output_key="selected_topic"
    )
    chain.add_step(
        name="Создание плана статьи",
        template=template_plan,
        output_key="article_plan"
    )
    
    # Запуск цепочки
    try:
        chain_result = chain.run({"domain": "медицинских технологий"})
        print(f"\n[Результат цепочки] Выбранная тема: {chain_result['selected_topic']}")
        print(f"[Результат цепочки] План статьи:\n{chain_result['article_plan']}")
    except Exception as e:
        print(f"[Ошибка выполнения цепочки]: {e}")

    # --- ДЕМОНСТРАЦИЯ 2: Агентный цикл рассуждения и вызов кода в песочнице ---
    print("\n=== ДЕМОНСТРАЦИЯ 2: Агент с вызовом кода в песочнице ===")
    run_agentic_loop(
        llm=llm,
        registry=registry,
        user_prompt="Пожалуйста, вычисли результат следующего математического выражения на Python: 105 * 2 + 10"
    )

    # --- ДЕМОНСТРАЦИЯ 3: Агент с мониторингом веб-ресурса ---
    print("\n=== ДЕМОНСТРАЦИЯ 3: Агент с мониторингом веб-ресурса ===")
    run_agentic_loop(
        llm=llm,
        registry=registry,
        user_prompt="Пожалуйста, проверь состояние веб-ресурса https://httpbin.org/status/200 и убедись, что он работает."
    )


if __name__ == "__main__":
    main()
