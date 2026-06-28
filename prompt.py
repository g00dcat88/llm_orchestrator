class PromptTemplate:
    """
    Управление шаблонами промптов с подстановкой переменных.
    """
    def __init__(self, template: str, required_variables: list[str] = None):
        self.template = template
        self.required_variables = required_variables or []

    def render(self, **kwargs) -> str:
        # Проверяем обязательные переменные
        missing = [var for var in self.required_variables if var not in kwargs]
        if missing:
            raise ValueError(f"Отсутствуют обязательные переменные шаблона: {', '.join(missing)}")
        
        # Подставляем переменные
        return self.template.format(**kwargs)
