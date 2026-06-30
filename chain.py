import logging
from typing import Optional
from gateway import BaseLLM
from prompt import PromptTemplate

logger = logging.getLogger(__name__)


class LLMChain:
    def __init__(self, llm: BaseLLM):
        self.llm = llm
        self.steps: list[dict] = []

    def add_step(
        self,
        name: str,
        template: PromptTemplate,
        output_key: str,
        system_prompt: Optional[str] = None,
    ) -> None:
        self.steps.append({
            "name": name,
            "template": template,
            "output_key": output_key,
            "system_prompt": system_prompt,
        })

    def run(self, inputs: dict, **kwargs) -> dict:
        state = inputs.copy()

        for step in self.steps:
            logger.info("Цепочка — шаг: %s", step["name"])
            prompt_str = step["template"].render(**state)

            res = self.llm.generate(
                prompt=prompt_str,
                system_prompt=step["system_prompt"],
                **kwargs,
            )

            if not res["ok"]:
                raise RuntimeError(f"Ошибка на шаге '{step['name']}': {res['error']}")

            content = res["content"]
            if isinstance(content, dict):
                content = str(content)
            state[step["output_key"]] = content.strip()

        return state
