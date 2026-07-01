import json
import logging
import sys
import time
import urllib.request
from pathlib import Path

from config import Config
from conversation import ConversationBuffer
from gateway import BaseLLM, create_llm_from_config
from prompt import PromptTemplate
from chain import LLMChain
from dispatcher import QueryDispatcher
from rag import BM25SearchEngine
from skills import SkillsManager
from tools import (
    Tool, ToolRegistry, PythonSandbox, WebMonitorTool, ERPIntegrationTools,
    CodeSearchTool, EntitySchemaTool, ApiDocsTool, ListEntitiesTool, EntityRelationsTool,
)
from cache import ResponseCache
from rate_limiter import DualRateLimiter
from metrics import MetricsCollector, TimingContext
from tracing import SpanContext, new_trace_id, reset_trace, format_trace
from guardrails import OutputGuardrails, InputGuardrails
from token_manager import TokenManager

logger = logging.getLogger("hermes")


def run_agentic_loop(
    llm: BaseLLM,
    registry: ToolRegistry,
    user_prompt: str,
    dispatcher: QueryDispatcher,
    conversation: ConversationBuffer,
    rag_engine: BM25SearchEngine,
    config: Config,
    cache: ResponseCache = None,
    rate_limiter: DualRateLimiter = None,
    metrics: MetricsCollector = None,
    input_guard: InputGuardrails = None,
    output_guard: OutputGuardrails = None,
    token_mgr: TokenManager = None,
    session_id: str = "default",
    use_cache: bool = True,
    self_learner=None,
    skill_id: str = None,
    skills_manager=None,
) -> dict:
    trace_id = new_trace_id()
    reset_trace()
    start_time = time.time()

    if input_guard:
        check = input_guard.check(user_prompt)
        if not check.passed:
            return {"ok": False, "error": "Input blocked", "violations": check.violations}

    if use_cache and cache:
        cached = cache.get(user_prompt)
        if cached:
            logger.info("Cache hit")
            if metrics:
                metrics.record_counter("cache_hit")
            cached["cached"] = True
            return cached

    if rate_limiter and not rate_limiter.allow_llm(session_id):
        if metrics:
            metrics.record_counter("rate_limited")
        return {"ok": False, "error": "Rate limit exceeded"}

    conversation.add_user_message(user_prompt)

    with SpanContext("classify", trace_id=trace_id):
        classification = dispatcher.classify(user_prompt)
    scope = classification.get("scope", "general")
    entity_id = classification.get("entity_id")
    scope_prompt = dispatcher.get_response_prompt(scope)
    logger.info("Scope: %s | Entity: %s", scope, entity_id)

    context_parts: list[str] = []
    with SpanContext("rag_search"):
        rag_results = rag_engine.search(user_prompt, top_k=config.rag_top_k)
        if rag_results:
            context_parts.append("База знаний:\n" + "\n\n".join(r["text"] for r in rag_results))

    conv_ctx = conversation.get_context_string()
    if conv_ctx:
        context_parts.append(f"История диалога:\n{conv_ctx}")

    profile = conversation.get_profile_summary()
    if profile:
        context_parts.append(profile)

    # Add learned examples from similar past interactions
    if self_learner:
        user_id = getattr(conversation, 'user_id', None)
        examples = self_learner.get_relevant_examples(user_prompt, scope=scope, user_id=user_id)
        if examples:
            context_parts.append(self_learner.format_examples(examples))

    full_context = "\n\n".join(context_parts)
    tools_schemas = registry.get_schemas_for_scope(scope)

    # Skill_id from ERP frontend takes priority over dispatcher scope prompt
    if skill_id and skills_manager:
        skills = skills_manager.list_skills()
        if skill_id in skills:
            system_prompt = skills[skill_id]["system_prompt"]
        else:
            system_prompt = scope_prompt
    else:
        system_prompt = scope_prompt

    prompt_with_context = user_prompt
    if full_context:
        prompt_with_context = f"Контекст:\n{full_context}\n\nВопрос: {user_prompt}"

    if token_mgr:
        budget = token_mgr.create_budget()
        if not budget.can_fit(prompt_with_context):
            prompt_with_context = budget.truncate_to_fit(prompt_with_context, prefix="Контекст:\n", suffix=f"\n\nВопрос: {user_prompt}")

    with SpanContext("llm_generate"):
        res = llm.generate(prompt=prompt_with_context, system_prompt=system_prompt, tools=tools_schemas)
    if not res["ok"]:
        logger.error("LLM error: %s", res["error"])
        return res

    retries = 0
    all_tools_used = []
    while res.get("tool_calls") and retries < 3:
        for tc in res["tool_calls"]:
            fn_name = tc["function"]["name"]
            all_tools_used.append(fn_name)
            try:
                fn_args = json.loads(tc["function"]["arguments"])
            except Exception:
                fn_args = {}
            logger.info("Tool: %s", fn_name)
            if fn_name in ("append_task_details", "consolidate_to_project"):
                logger.warning("SAFE GATE: %s", fn_name)
            with SpanContext(f"tool:{fn_name}"):
                tool_output = registry.call(fn_name, fn_args)
            feedback = f"Инструмент '{fn_name}' вернул:\n{tool_output}\nСформируй ответ."
            res = llm.generate(prompt=feedback, system_prompt=system_prompt, tools=tools_schemas)
            if not res["ok"]:
                return res
        retries += 1

    answer = res.get("content", "")

    if config.self_critique_enabled and answer:
        with SpanContext("self_critique"):
            critique = llm.generate(
                prompt=f"Проверь:\nВопрос: {user_prompt}\nОтвет: {answer}\nВерни только ответ.",
                system_prompt="Ты редактор.",
            )
            if critique.get("ok") and critique.get("content"):
                answer = critique["content"]

    if output_guard:
        oc = output_guard.check(answer)
        answer = oc.filtered_text

    conversation.add_assistant_message(answer)

    duration = time.time() - start_time
    if metrics:
        metrics.record_timing("full_pipeline", duration, scope=scope)
        metrics.record_counter("requests")
        metrics.record_counter(f"scope:{scope}")

    logger.info("Done in %.1fs", duration * 1000)
    logger.info("Trace:\n%s", format_trace())

    result = {"ok": True, "content": answer, "trace_id": trace_id, "scope": scope,
              "duration_ms": round(duration * 1000, 1), "tool_calls": all_tools_used}

    if use_cache and cache:
        cache.set(user_prompt, result)

    # Record interaction for self-learning
    if self_learner:
        user_id = getattr(conversation, 'user_id', None)
        if user_id:
            self_learner.record_interaction(
                user_id=user_id,
                prompt=user_prompt,
                response=answer,
                scope=scope,
                tools_used=all_tools_used,
                success=True,
            )

    return result


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def build_registry(config: Config, project_dir: Path) -> ToolRegistry:
    registry = ToolRegistry()
    sandbox_dir = project_dir / config.sandbox_dir
    sandbox = PythonSandbox(sandbox_dir, timeout=config.sandbox_timeout)

    registry.register(Tool(
        name="execute_python",
        description="Выполняет Python-код в песочнице.",
        parameters={"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]},
        func=sandbox.execute_code, category="python_sandbox",
    ))

    monitor_log = sandbox_dir / "monitoring_log.json"
    web_monitor = WebMonitorTool(monitor_log)
    registry.register(Tool(
        name="monitor_web_resource",
        description="Проверяет доступность URL.",
        parameters={"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
        func=web_monitor.monitor, category="web_monitor",
    ))

    erp = ERPIntegrationTools(base_url=config.erp_base_url, service_token=config.erp_service_token)
    for name, desc, params, func, cat in [
        ("get_project_card", "Карточка проекта по коду.", {"project_code": {"type": "string"}}, erp.get_project_card, "fsm_single"),
        ("get_trip_details", "Детали командировки по ID.", {"schedule_id": {"type": "integer"}}, erp.get_trip_details, "hr_single"),
        ("list_upcoming_trips", "Список командировок.", {}, erp.list_upcoming_trips, "hr_summary"),
        ("append_task_details", "Запись в лог наряда.", {"work_order_id": {"type": "integer"}, "text": {"type": "string"}, "author_name": {"type": "string"}}, erp.append_task_details, "fsm_single"),
        ("consolidate_to_project", "Отчёт в карточку проекта.", {"project_id": {"type": "integer"}, "summary_text": {"type": "string"}}, erp.consolidate_to_project, "fsm_single"),
        ("get_task_comments", "Комментарии по задаче.", {"work_order_id": {"type": "integer"}}, erp.get_task_comments, "fsm_single"),
        ("update_task_summary", "Обновить отчёт задачи.", {"work_order_id": {"type": "integer"}, "summary_text": {"type": "string"}}, erp.update_task_summary, "fsm_single"),
        ("search_knowledge_base", "Поиск в базе знаний.", {"query": {"type": "string"}}, erp.search_knowledge_base, "general"),
    ]:
        required = [k for k, v in params.items() if k in ("project_code", "schedule_id", "work_order_id", "project_id", "query", "text", "author_name", "summary_text")]
        registry.register(Tool(name=name, description=desc, parameters={"type": "object", "properties": params, "required": required}, func=func, category=cat))

    knowledge_dir = project_dir / "knowledge_base"
    code_search = CodeSearchTool(config.code_search_backend_path)
    registry.register(Tool(
        name="search_code", description="Поиск по исходникам проекта.",
        parameters={"type": "object", "properties": {"query": {"type": "string"}, "file_pattern": {"type": "string"}}, "required": ["query"]},
        func=code_search.search, category="code_search",
    ))

    entity_schema = EntitySchemaTool(knowledge_dir)
    registry.register(Tool(
        name="get_entity_schema", description="Схема таблицы БД.",
        parameters={"type": "object", "properties": {"table_name": {"type": "string"}}, "required": ["table_name"]},
        func=entity_schema.get_schema, category="entity_schema",
    ))

    api_docs = ApiDocsTool(knowledge_dir)
    registry.register(Tool(
        name="get_api_docs", description="Документация API-эндпоинта.",
        parameters={"type": "object", "properties": {"endpoint_pattern": {"type": "string"}}, "required": ["endpoint_pattern"]},
        func=api_docs.get_docs, category="entity_schema",
    ))

    list_entities = ListEntitiesTool(knowledge_dir)
    registry.register(Tool(
        name="list_entities", description="Список таблиц или API-эндпоинтов.",
        parameters={"type": "object", "properties": {"entity_type": {"type": "string"}}},
        func=lambda entity_type="tables": list_entities.list_tables() if entity_type == "tables" else list_entities.list_api_endpoints(),
        category="entity_schema",
    ))

    relations = EntityRelationsTool(knowledge_dir)
    registry.register(Tool(
        name="get_entity_relations", description="Связи таблицы.",
        parameters={"type": "object", "properties": {"table_name": {"type": "string"}}, "required": ["table_name"]},
        func=relations.get_relations, category="entity_schema",
    ))

    return registry


def main() -> None:
    config = Config.from_env()
    setup_logging(config.log_level)
    project_dir = Path(__file__).resolve().parent

    logger.info("=== HERMES LLM Orchestrator ===")

    cache = ResponseCache(str(project_dir / "cache.db"))
    rate_limiter = DualRateLimiter(llm_rate=5, llm_burst=10)
    metrics = MetricsCollector(str(project_dir / "metrics.db"))
    input_guard = InputGuardrails()
    output_guard = OutputGuardrails()
    token_mgr = TokenManager(max_context=4096)

    rag_engine = BM25SearchEngine()
    knowledge_dir = project_dir / "knowledge_base"
    if knowledge_dir.exists():
        indexed = rag_engine.index_directory(knowledge_dir)
        logger.info("RAG: %d chunks indexed", indexed)

    conversation = ConversationBuffer(max_messages=config.conversation_max_messages)
    registry = build_registry(config, project_dir)
    logger.info("Registered %d tools", len(registry.tools))

    llm = create_llm_from_config(config)
    dispatcher = QueryDispatcher(llm)

    loop_kwargs = dict(
        dispatcher=dispatcher, conversation=conversation, rag_engine=rag_engine, config=config,
        cache=cache, rate_limiter=rate_limiter, metrics=metrics,
        input_guard=input_guard, output_guard=output_guard, token_mgr=token_mgr,
    )

    print("\n=== Demo 1: Prompt Chain ===")
    chain = LLMChain(llm)
    chain.add_step("Topic", PromptTemplate("Выбери тему в {domain}.", ["domain"]), "topic")
    chain.add_step("Plan", PromptTemplate("План статьи: '{topic}'.", ["topic"]), "plan")
    try:
        r = chain.run({"domain": "AI"})
        print(f"Тема: {r['topic']}\nПлан:\n{r['plan']}")
    except Exception as e:
        print(f"Error: {e}")

    print("\n=== Demo 2: Compute ===")
    run_agentic_loop(llm=llm, registry=registry, user_prompt="Посчитай 105 * 2 + 10", **loop_kwargs)

    print("\n=== Demo 3: Monitoring ===")
    run_agentic_loop(llm=llm, registry=registry, user_prompt="Проверь httpbin.org/status/200", **loop_kwargs)

    print("\n=== Demo 4: Knowledge Base ===")
    run_agentic_loop(llm=llm, registry=registry, user_prompt="Какая структура БД?", **loop_kwargs)

    print("\n=== Demo 5: Session Context ===")
    run_agentic_loop(llm=llm, registry=registry, user_prompt="А какие таблицы?", **loop_kwargs)

    print("\n=== Metrics ===")
    print(metrics.export_json())
    print("\n=== Done ===")


if __name__ == "__main__":
    main()
