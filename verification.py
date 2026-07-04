"""Verification Engine — watchdog-паттерн для проверки результатов tool calls.

После каждого действия агента система автоматически проверяет, что действие
выполнено корректно. Если проверка не прошла — повторяет или эскалирует.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import Enum


class VerifyResult(Enum):
    PASS = "pass"
    FAIL = "fail"
    UNCERTAIN = "uncertain"
    SKIP = "skip"


@dataclass
class VerificationReport:
    tool_name: str
    result: VerifyResult
    confidence: float          # 0.0 - 1.0
    message: str = ""
    details: dict = field(default_factory=dict)
    retry_suggested: bool = False
    verified_at: float = 0.0

    def __post_init__(self):
        if not self.verified_at:
            self.verified_at = time.time()


# Правила верификации для каждого типа инструмента
VERIFICATION_RULES = {
    "append_task_details": {
        "description": "Проверка записи в наряд",
        "verify_tool": "get_task_comments",
        "verify_param": "work_order_id",
        "check_field": None,  # проверяем наличие новой записи
        "confidence_threshold": 0.8,
    },
    "update_task_summary": {
        "description": "Проверка обновления сводки задачи",
        "verify_tool": "get_task_comments",
        "verify_param": "work_order_id",
        "check_field": None,
        "confidence_threshold": 0.8,
    },
    "consolidate_to_project": {
        "description": "Проверка записи в проект",
        "verify_tool": "get_project_card",
        "verify_param": "project_id",
        "check_field": "comments",
        "confidence_threshold": 0.7,
    },
    "get_project_card": {
        "description": "Проверка получения карточки",
        "verify_tool": None,  # инструмент чтения — верификация не нужна
        "confidence_threshold": 0.9,
    },
    "get_trip_details": {
        "description": "Проверка получения данных командировки",
        "verify_tool": None,
        "confidence_threshold": 0.9,
    },
    "list_upcoming_trips": {
        "description": "Проверка списка командировок",
        "verify_tool": None,
        "confidence_threshold": 0.9,
    },
    "search_knowledge_base": {
        "description": "Проверка поиска в базе знаний",
        "verify_tool": None,
        "confidence_threshold": 0.85,
    },
    "execute_python": {
        "description": "Проверка выполнения Python-кода",
        "verify_tool": None,
        "confidence_threshold": 0.7,
    },
    "monitor_web_resource": {
        "description": "Проверка веб-мониторинга",
        "verify_tool": None,
        "confidence_threshold": 0.8,
    },
}


class VerificationEngine:
    """Движок верификации результатов tool calls."""

    def __init__(self) -> None:
        self.reports: list[VerificationReport] = []
        self.max_retries = 2

    def should_verify(self, tool_name: str) -> bool:
        """Нужна ли верификация для данного инструмента."""
        rule = VERIFICATION_RULES.get(tool_name)
        if not rule:
            return True  # по умолчанию — верифицируем всё новое
        return rule.get("verify_tool") is not None

    def get_verify_tool(self, tool_name: str) -> str | None:
        """Какой инструмент использовать для верификации."""
        rule = VERIFICATION_RULES.get(tool_name)
        if rule:
            return rule.get("verify_tool")
        return None

    def get_verify_params(self, tool_name: str, original_params: dict) -> dict:
        """Параметры для инструмента верификации."""
        rule = VERIFICATION_RULES.get(tool_name, {})
        verify_param = rule.get("verify_param")
        if verify_param and verify_param in original_params:
            return {verify_param: original_params[verify_param]}
        return {}

    def evaluate_result(
        self,
        tool_name: str,
        tool_params: dict,
        tool_result: dict,
        verify_result: dict | None = None,
    ) -> VerificationReport:
        """Оценить результат tool call и, при необходимости, верификации."""
        rule = VERIFICATION_RULES.get(tool_name, {})
        threshold = rule.get("confidence_threshold", 0.7)

        # Если инструмент чтения — доверяем результату
        if not rule.get("verify_tool"):
            confidence = 0.9 if tool_result.get("ok") else 0.3
            return VerificationReport(
                tool_name=tool_name,
                result=VerifyResult.PASS if confidence >= threshold else VerifyResult.FAIL,
                confidence=confidence,
                message="Инструмент чтения — верификация не требуется",
            )

        # Если нет результата верификации — оцениваем по tool_result
        if verify_result is None:
            if tool_result.get("ok"):
                return VerificationReport(
                    tool_name=tool_name,
                    result=VerifyResult.PASS,
                    confidence=0.7,
                    message="ОК, но верификация не выполнена",
                )
            else:
                return VerificationReport(
                    tool_name=tool_name,
                    result=VerifyResult.FAIL,
                    confidence=0.3,
                    message=f"Ошибка: {tool_result.get('error', 'неизвестно')}",
                    retry_suggested=True,
                )

        # Анализ результата верификации
        confidence = self._calculate_confidence(tool_name, tool_params, tool_result, verify_result)

        if confidence >= threshold:
            result = VerifyResult.PASS
            msg = "Верификация пройдена"
        elif confidence >= threshold * 0.5:
            result = VerifyResult.UNCERTAIN
            msg = "Верификация неуверенная — возможна ошибка"
        else:
            result = VerifyResult.FAIL
            msg = "Верификация не пройдена"

        return VerificationReport(
            tool_name=tool_name,
            result=result,
            confidence=confidence,
            message=msg,
            retry_suggested=result != VerifyResult.PASS,
            details={"threshold": threshold, "verify_tool_result": verify_result},
        )

    def _calculate_confidence(
        self,
        tool_name: str,
        params: dict,
        result: dict,
        verify_result: dict,
    ) -> float:
        """Рассчитать confidence на основе результата и верификации."""
        base_confidence = 0.5

        # Если основной инструмент вернул OK
        if result.get("ok"):
            base_confidence += 0.2

        # Если верификация показала наличие данных
        if verify_result.get("ok"):
            base_confidence += 0.15

        # Проверка контента (для append/update)
        rule = VERIFICATION_RULES.get(tool_name, {})
        if rule.get("check_field") and verify_result:
            field_val = verify_result.get(rule["check_field"])
            if field_val:
                base_confidence += 0.1

        # Штраф за пустой результат
        if not result.get("content") and not result.get("ok"):
            base_confidence -= 0.2

        return max(0.0, min(1.0, base_confidence))

    def should_retry(self, report: VerificationReport, attempt: int) -> bool:
        """Стоит ли повторить действие."""
        return report.retry_suggested and attempt < self.max_retries

    def record(self, report: VerificationReport) -> None:
        """Записать отчёт о верификации."""
        self.reports.append(report)
        # Ограничиваем историю
        if len(self.reports) > 100:
            self.reports = self.reports[-100:]

    def get_stats(self) -> dict:
        """Статистика верификаций."""
        if not self.reports:
            return {"total": 0, "pass": 0, "fail": 0, "uncertain": 0, "avg_confidence": 0}
        total = len(self.reports)
        passed = sum(1 for r in self.reports if r.result == VerifyResult.PASS)
        failed = sum(1 for r in self.reports if r.result == VerifyResult.FAIL)
        uncertain = sum(1 for r in self.reports if r.result == VerifyResult.UNCERTAIN)
        avg_conf = sum(r.confidence for r in self.reports) / total
        return {
            "total": total,
            "pass": passed,
            "fail": failed,
            "uncertain": uncertain,
            "avg_confidence": round(avg_conf, 2),
        }
