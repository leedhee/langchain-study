from app.agents.tools import _build_symptom_search_queries
from app.agents.tools import _extract_disease_hint


def test_regex_extracts_gastritis_as_disease_hint():
    assert _extract_disease_hint("속이 쓰린데 위염 증상일 수 있어?") == "위염"


def test_regex_extracts_longer_disease_name_first():
    assert _extract_disease_hint("역류성식도염 증상일까?") == "역류성식도염"


def test_disease_name_is_prioritized_for_symptom_question():
    queries = _build_symptom_search_queries("속쓰림과 복통이 있는데 위염 증상일 수 있어?")

    assert queries == ["위염", "위염 속쓰림 복통"]


def test_symptom_only_question_uses_symptom_terms():
    queries = _build_symptom_search_queries("속쓰림, 복통")

    assert queries == ["속쓰림 복통"]
