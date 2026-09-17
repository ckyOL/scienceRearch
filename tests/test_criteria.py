"""判据求值的行为测试：三态语义与 errors 的分类必须能被外部观察到。"""

from __future__ import annotations

from scirearch.criteria import (
    DECIDED_BY_HUMAN,
    DECIDED_BY_MACHINE,
    REASON_FREE_TEXT,
    REASON_MISSING_METRIC,
    REASON_NON_NUMERIC,
    STATE_PENDING,
    STATE_SATISFIED,
    STATE_UNDECIDABLE,
    STATE_VIOLATED,
    evaluate,
    evaluate_one,
    normalize,
    parse,
)


def _state(criterion: str, metrics: dict[str, object] | None) -> str:
    return evaluate_one(criterion, metrics).state


def test_comparisons_cover_all_operators() -> None:
    metrics = {"x": 3.0}
    assert _state("x > 2", metrics) == STATE_SATISFIED
    assert _state("x >= 3", metrics) == STATE_SATISFIED
    assert _state("x < 2", metrics) == STATE_VIOLATED
    assert _state("x <= 2", metrics) == STATE_VIOLATED
    assert _state("x == 3", metrics) == STATE_SATISFIED
    assert _state("x != 3", metrics) == STATE_VIOLATED


def test_nested_paths_and_whitespace_variants_resolve() -> None:
    metrics = {"results": {"std": 0.0031}}
    assert _state("results.std < 0.01", metrics) == STATE_SATISFIED
    assert _state("  results.std<0.01  ", metrics) == STATE_SATISFIED
    assert _state("results.std >= 1e-2", metrics) == STATE_VIOLATED


def test_missing_metric_is_machine_undecidable_not_violated() -> None:
    outcome = evaluate_one("std < 0.01", {"other": 1})
    assert outcome.state == STATE_UNDECIDABLE
    assert outcome.reason == REASON_MISSING_METRIC
    assert outcome.decided_by == DECIDED_BY_MACHINE


def test_non_numeric_metric_is_undecidable() -> None:
    # 布尔值不是数值：True 排序上与 1 相等，但不应被当作可裁决的度量。
    outcome = evaluate_one("flag > 0", {"flag": True})
    assert outcome.state == STATE_UNDECIDABLE
    assert outcome.reason == REASON_NON_NUMERIC


def test_free_text_criteria_are_human_decided() -> None:
    outcome = evaluate_one("无 NaN", {"std": 0.1})
    assert outcome.state == STATE_UNDECIDABLE
    assert outcome.decided_by == DECIDED_BY_HUMAN
    assert outcome.reason == REASON_FREE_TEXT
    assert parse("无 NaN") is None


def test_pending_when_no_metrics_yet() -> None:
    outcomes = evaluate(["std < 0.01", "无 NaN"], None)
    assert [o.state for o in outcomes] == [STATE_PENDING, STATE_UNDECIDABLE]
    assert outcomes[0].decided_by == DECIDED_BY_MACHINE


def test_outcome_carries_observed_value_for_reporting() -> None:
    outcome = evaluate_one("std < 0.01", {"std": 0.0031})
    assert outcome.state == STATE_SATISFIED
    assert outcome.detail == "std=0.0031"
    assert outcome.value == 0.0031


def test_normalize_canonicalizes_machine_criteria() -> None:
    assert normalize("  std  <  0.01 ") == "std < 0.01"
    assert normalize("std < 0.01") == normalize("std<0.01")
    assert normalize("  无   NaN ") == "无 NaN"
