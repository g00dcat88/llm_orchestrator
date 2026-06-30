import json
import logging
import os
import sys
import time
import uuid
from pathlib import Path
from typing import AsyncGenerator, Optional

logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import Config, ProviderConfig
from conversation import ConversationBuffer
from gateway import BaseLLM, LlamaServerLLM, create_llm_from_config
from dispatcher import QueryDispatcher
from rag import BM25SearchEngine
from tools import ToolRegistry
from cache import ResponseCache
from rate_limiter import DualRateLimiter
from retry import retry
from metrics import MetricsCollector
from tracing import SpanContext, new_trace_id, reset_trace
from guardrails import OutputGuardrails, InputGuardrails
from token_manager import TokenManager

try:
    from fastapi import FastAPI, Request, HTTPException, Depends
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse, StreamingResponse
    from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
    import uvicorn
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False

from api.auth import validate_api_key, get_key_name, load_api_keys


class OrchestratorApp:
    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config.from_env()
        self.project_dir = Path(__file__).resolve().parent.parent

        self.cache = ResponseCache(
            db_path=str(self.project_dir / "cache.db"),
            ttl_seconds=3600,
        )
        self.rate_limiter = DualRateLimiter(llm_rate=5, llm_burst=10)
        self.metrics = MetricsCollector(db_path=str(self.project_dir / "metrics.db"))
        self.output_guardrails = OutputGuardrails()
        self.input_guardrails = InputGuardrails()
        self.token_manager = TokenManager(max_context=4096)
        self.conversations: dict[str, ConversationBuffer] = {}

        self.rag_engine = BM25SearchEngine()
        knowledge_dir = self.project_dir / "knowledge_base"
        if knowledge_dir.exists():
            indexed = self.rag_engine.index_directory(knowledge_dir)
            logger.info("RAG: indexed %d chunks", indexed)

        from main import build_registry
        self.registry = build_registry(self.config, self.project_dir)

        self.llm: BaseLLM = self._init_llm()
        self.dispatcher = QueryDispatcher(self.llm)

    def _init_llm(self) -> BaseLLM:
        return create_llm_from_config(self.config)

    def get_conversation(self, session_id: str) -> ConversationBuffer:
        if session_id not in self.conversations:
            self.conversations[session_id] = ConversationBuffer(
                max_messages=self.config.conversation_max_messages
            )
        return self.conversations[session_id]

    def process_query(
        self,
        query: str,
        session_id: str = "default",
        use_cache: bool = True,
    ) -> dict:
        trace_id = new_trace_id()
        reset_trace()

        start_time = time.time()

        input_check = self.input_guardrails.check(query)
        if not input_check.passed:
            return {"ok": False, "error": "Input blocked by guardrails", "violations": input_check.violations}

        if use_cache:
            cached = self.cache.get(query)
            if cached:
                self.metrics.record_counter("cache_hit")
                cached["cached"] = True
                return cached

        if not self.rate_limiter.allow_llm(session_id):
            self.metrics.record_counter("rate_limited")
            return {"ok": False, "error": "Rate limit exceeded. Please wait."}

        with SpanContext("full_pipeline", trace_id=trace_id) as span:
            conversation = self.get_conversation(session_id)
            conversation.add_user_message(query)

            with SpanContext("classify"):
                classification = self.dispatcher.classify(query)

            scope = classification.get("scope", "general")
            entity_id = classification.get("entity_id")
            scope_prompt = self.dispatcher.get_response_prompt(scope)

            context_parts: list[str] = []

            with SpanContext("rag_search"):
                rag_results = self.rag_engine.search(query, top_k=self.config.rag_top_k)
                if rag_results:
                    rag_text = "\n\n".join(r["text"] for r in rag_results)
                    context_parts.append(f"База знаний:\n{rag_text}")

            conv_context = conversation.get_context_string()
            if conv_context:
                context_parts.append(f"История диалога:\n{conv_context}")

            full_context = "\n\n".join(context_parts)

            tools_schemas = self.registry.get_schemas_for_scope(scope)

            prompt_with_context = query
            if full_context:
                prompt_with_context = f"Контекст:\n{full_context}\n\nВопрос: {query}"

            with SpanContext("llm_generate"):
                res = self.llm.generate(
                    prompt=prompt_with_context,
                    system_prompt=scope_prompt,
                    tools=tools_schemas,
                )

            retries = 0
            while res.get("tool_calls") and retries < 3:
                for tool_call in res["tool_calls"]:
                    fn_name = tool_call["function"]["name"]
                    try:
                        fn_args = json.loads(tool_call["function"]["arguments"])
                    except Exception:
                        fn_args = {}

                    with SpanContext(f"tool:{fn_name}"):
                        tool_output = self.registry.call(fn_name, fn_args)

                    feedback = (
                        f"Инструмент '{fn_name}' вернул:\n{tool_output}\n"
                        f"Сформируй итоговый ответ."
                    )
                    res = self.llm.generate(
                        prompt=feedback,
                        system_prompt=scope_prompt,
                        tools=tools_schemas,
                    )
                retries += 1

            answer = res.get("content", "")

            if self.config.self_critique_enabled and answer:
                with SpanContext("self_critique"):
                    critique = self.llm.generate(
                        prompt=f"Проверь ответ:\nВопрос: {query}\nОтвет: {answer}\nВерни только ответ.",
                        system_prompt="Ты редактор.",
                    )
                    if critique.get("ok") and critique.get("content"):
                        answer = critique["content"]

            output_check = self.output_guardrails.check(answer)
            answer = output_check.filtered_text

            conversation.add_assistant_message(answer)

        duration = time.time() - start_time
        self.metrics.record_counter("requests")
        self.metrics.record_timing("full_pipeline", duration, scope=scope)
        self.metrics.record_counter(f"scope:{scope}")

        result = {
            "ok": True,
            "content": answer,
            "session_id": session_id,
            "trace_id": trace_id,
            "scope": scope,
            "entity_id": entity_id,
            "duration_ms": round(duration * 1000, 1),
            "cached": False,
        }

        if use_cache:
            self.cache.set(query, result)

        return result

    def get_metrics(self) -> dict:
        return {
            "cache": self.cache.stats(),
            "metrics": self.metrics.get_summary(minutes=60),
        }


def create_app(orchestrator: Optional[OrchestratorApp] = None) -> "FastAPI":
    if not HAS_FASTAPI:
        raise ImportError("FastAPI not installed. Run: pip install fastapi uvicorn")

    app = FastAPI(title="Hermes LLM Orchestrator", version="1.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    state = {"orchestrator": orchestrator}

    @app.on_event("startup")
    async def startup():
        if state["orchestrator"] is None:
            state["orchestrator"] = OrchestratorApp()
        load_api_keys()
        logger.info("Hermes API started")

    def get_orchestrator():
        return state["orchestrator"]

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "hermes"}

    @app.post("/chat")
    async def chat(request: Request):
        body = await request.json()
        query = body.get("query", "").strip()
        session_id = body.get("session_id", "default")
        use_cache = body.get("use_cache", True)

        if not query:
            raise HTTPException(400, "query is required")

        orch = get_orchestrator()
        result = orch.process_query(query, session_id, use_cache)
        return result

    @app.post("/chat/stream")
    async def chat_stream(request: Request):
        body = await request.json()
        query = body.get("query", "").strip()
        session_id = body.get("session_id", "default")

        if not query:
            raise HTTPException(400, "query is required")

        async def generate():
            orch = get_orchestrator()
            classification = orch.dispatcher.classify(query)
            scope = classification.get("scope", "general")

            yield f"data: {json.dumps({'type': 'classification', 'scope': scope})}\n\n"

            rag_results = orch.rag_engine.search(query, top_k=3)
            if rag_results:
                yield f"data: {json.dumps({'type': 'rag', 'count': len(rag_results)})}\n\n"

            yield f"data: {json.dumps({'type': 'generating'})}\n\n"

            result = orch.process_query(query, session_id)
            yield f"data: {json.dumps({'type': 'complete', 'content': result.get('content', '')})}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(generate(), media_type="text/event-stream")

    @app.get("/metrics")
    async def metrics():
        orch = get_orchestrator()
        return orch.get_metrics()

    @app.get("/cache/stats")
    async def cache_stats():
        orch = get_orchestrator()
        return orch.cache.stats()

    @app.delete("/cache")
    async def cache_clear():
        orch = get_orchestrator()
        count = orch.cache.clear()
        return {"cleared": count}

    @app.get("/trace/{trace_id}")
    async def trace(trace_id: str):
        return {"trace_id": trace_id, "message": "Trace data available in metrics"}

    @app.get("/providers")
    async def list_providers():
        orch = get_orchestrator()
        providers = []
        for p in orch.config.providers:
            providers.append({
                "name": p.name,
                "type": p.type,
                "enabled": p.enabled,
                "base_url": p.base_url,
                "model": p.model,
                "temperature": p.temperature,
                "max_tokens": p.max_tokens,
                "role": p.role,
                "has_key": bool(p.api_key),
            })
        return {"providers": providers}

    @app.get("/providers/{name}")
    async def get_provider(name: str):
        orch = get_orchestrator()
        for p in orch.config.providers:
            if p.name == name:
                return {
                    "name": p.name,
                    "type": p.type,
                    "enabled": p.enabled,
                    "base_url": p.base_url,
                    "model": p.model,
                    "temperature": p.temperature,
                    "max_tokens": p.max_tokens,
                    "role": p.role,
                    "has_key": bool(p.api_key),
                }
        raise HTTPException(404, f"Provider '{name}' not found")

    @app.post("/providers/{name}/test")
    async def test_provider(name: str):
        orch = get_orchestrator()
        if hasattr(orch.llm, "test_provider"):
            result = orch.llm.test_provider(name)
        else:
            result = {"ok": False, "error": "Router not active"}
        return result

    @app.post("/providers/{name}/toggle")
    async def toggle_provider(name: str):
        orch = get_orchestrator()
        for p in orch.config.providers:
            if p.name == name:
                p.enabled = not p.enabled
                orch.llm = create_llm_from_config(orch.config)
                orch.dispatcher = QueryDispatcher(orch.llm)
                return {"name": name, "enabled": p.enabled}
        raise HTTPException(404, f"Provider '{name}' not found")

    @app.post("/providers/{name}/update")
    async def update_provider(name: str, request: Request):
        orch = get_orchestrator()
        body = await request.json()
        for p in orch.config.providers:
            if p.name == name:
                if "api_key" in body:
                    p.api_key = body["api_key"]
                if "base_url" in body:
                    p.base_url = body["base_url"]
                if "model" in body:
                    p.model = body["model"]
                if "temperature" in body:
                    p.temperature = float(body["temperature"])
                if "max_tokens" in body:
                    p.max_tokens = int(body["max_tokens"])
                if "enabled" in body:
                    p.enabled = body["enabled"]
                orch.llm = create_llm_from_config(orch.config)
                orch.dispatcher = QueryDispatcher(orch.llm)
                return {
                    "ok": True,
                    "name": name,
                    "has_key": bool(p.api_key),
                    "base_url": p.base_url,
                    "model": p.model,
                }
        raise HTTPException(404, f"Provider '{name}' not found")

    @app.get("/router/status")
    async def router_status():
        orch = get_orchestrator()
        status = {
            "strategy": orch.config.router.strategy,
            "fallback_chain": orch.config.router.fallback_chain,
            "classification_provider": orch.config.router.classification_provider,
            "tool_call_provider": orch.config.router.tool_call_provider,
            "complexity_threshold": orch.config.router.complexity_threshold,
            "llm_type": type(orch.llm).__name__,
        }
        if hasattr(orch.llm, "get_status"):
            status["providers"] = orch.llm.get_status()
        return status

    @app.post("/router/strategy")
    async def set_router_strategy(request: Request):
        body = await request.json()
        strategy = body.get("strategy", "hybrid")
        if strategy not in ("hybrid", "local-first", "api-first"):
            raise HTTPException(400, "Invalid strategy")
        orch = get_orchestrator()
        orch.config.router.strategy = strategy
        orch.llm = create_llm_from_config(orch.config)
        orch.dispatcher = QueryDispatcher(orch.llm)
        return {"strategy": strategy}

    return app


def run_server(host: str = "0.0.0.0", port: int = 8888):
    if not HAS_FASTAPI:
        print("FastAPI not installed. Run: pip install fastapi uvicorn")
        return
    app = create_app()
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_server()
