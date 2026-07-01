"""Self-learning module — records successful interactions and enriches knowledge."""
import json
import logging
from session_store import SessionStore

logger = logging.getLogger(__name__)


class SelfLearner:
    def __init__(self, store: SessionStore):
        self.store = store

    def record_interaction(self, user_id: str, prompt: str, response: str,
                           scope: str = None, tools_used: list = None,
                           success: bool = True):
        """Record a successful interaction as a learned pattern."""
        rating = 1.0 if success else 0.3
        self.store.save_pattern(
            user_id=user_id,
            pattern_type="qa_pair",
            input_prompt=prompt,
            output_response=response,
            scope=scope,
            tools_used=tools_used or [],
            success_rating=rating,
        )
        logger.info("Recorded pattern: user=%s scope=%s tools=%s", user_id, scope, tools_used)

    def get_relevant_examples(self, prompt: str, scope: str = None,
                              user_id: str = None, limit: int = 3) -> list[dict]:
        """Find relevant learned examples to inject into context."""
        patterns = self.store.get_patterns(scope=scope, limit=50)
        scored = []
        prompt_words = set(prompt.lower().split())
        for p in patterns:
            if user_id and p["user_id"] == user_id:
                continue  # skip own patterns to avoid echo
            pattern_words = set(p["input_prompt"].lower().split())
            overlap = len(prompt_words & pattern_words)
            if overlap >= 2 and p["success_rating"] >= 0.7:
                scored.append((overlap, p))
        scored.sort(key=lambda x: -x[0])
        return [p for _, p in scored[:limit]]

    def enrich_knowledge(self, user_id: str, tool_name: str,
                         tool_output: str, query: str):
        """Save useful tool results to the knowledge base."""
        if len(tool_output) > 100:
            content = f"[Из инструмента {tool_name} по запросу '{query}']\n{tool_output}"
            self.store.save_knowledge(content, source="tool_result", added_by=user_id)
            logger.info("Enriched knowledge from tool=%s user=%s", tool_name, user_id)

    def record_feedback(self, pattern_id: int, rating: float):
        """Update rating for a learned pattern based on user feedback."""
        self.store.update_pattern_rating(pattern_id, max(0.0, min(1.0, rating)))

    def format_examples(self, examples: list[dict]) -> str:
        """Format learned examples for context injection."""
        if not examples:
            return ""
        lines = ["Похожие успешные запросы:"]
        for i, ex in enumerate(examples, 1):
            lines.append(f"{i}. Вопрос: {ex['input_prompt'][:100]}")
            lines.append(f"   Ответ: {ex['output_response'][:150]}")
            if ex.get("tools_used"):
                lines.append(f"   Инструменты: {', '.join(ex['tools_used'])}")
        return "\n".join(lines)
