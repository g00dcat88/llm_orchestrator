class PromptTemplate:
    def __init__(self, template: str, required_variables: list[str] | None = None):
        self.template = template
        self.required_variables = required_variables or []

    def render(self, **kwargs) -> str:
        missing = [var for var in self.required_variables if var not in kwargs]
        if missing:
            raise ValueError(f"Missing variables: {', '.join(missing)}")
        return self.template.format(**kwargs)
