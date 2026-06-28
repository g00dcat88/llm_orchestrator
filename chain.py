from gateway import BaseLLM
from prompt import PromptTemplate

class LLMChain:
    """
    Цепочка последовательного выполнения задач с передачей контекста между шагами.
    """
    def __init__(self, llm: BaseLLM):
        self.llm = llm
        self.steps = []

    def add_step(self, name: str, template: PromptTemplate, output_key: str, system_prompt: str = None):
        """
        Добавление шага в цепочку.
        """
        self.steps.append({
            "name": name,
            "template": template,
            "output_key": output_key,
            "system_prompt": system_prompt
        })

    def run(self, inputs: dict, **kwargs) -> dict:
        """
        Последовательный запуск всех шагов цепочки с накоплением состояния.
        """
        state = inputs.copy()
        
        for step in self.steps:
            print(f"-> Выполнение шага: {step['name']}...")
            
            # Форматируем шаблон с текущими переменными состояния
            prompt_str = step["template"].render(**state)
            
            # Генерируем ответ модели
            res = self.llm.generate(
                prompt=prompt_str, 
                system_prompt=step["system_prompt"],
                **kwargs
            )
            
            if not res["ok"]:
                raise RuntimeError(f"Ошибка на шаге '{step['name']}': {res['error']}")
                
            # Записываем результат шага в состояние цепочки
            state[step["output_key"]] = res["content"].strip()
            
        return state
