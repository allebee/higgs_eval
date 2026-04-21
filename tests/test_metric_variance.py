"""Per-metric variance across repeats — task requires this, not a hidden average."""
from drleval.schema import CaseAggregate, CaseRunResult, Verdict


def _run(idx: int, verdicts: list[tuple[str, bool]]) -> CaseRunResult:
    return CaseRunResult(
        case_id="c",
        run_index=idx,
        trace_hash="h",
        verdicts=[Verdict(metric=m, kind="hard", passed=p) for m, p in verdicts],
        passed=all(p for _, p in verdicts),
    )


def test_metric_variance_reports_per_metric_pass_rate():
    runs = [
        _run(0, [("m1", True), ("m2", True)]),
        _run(1, [("m1", True), ("m2", False)]),  # m2 flaky
        _run(2, [("m1", True), ("m2", True)]),
    ]
    mv = CaseAggregate(case_id="c", runs=runs).metric_variance()
    by = {x["metric"]: x for x in mv}
    assert by["m1"]["passed"] == 3 and by["m1"]["total"] == 3 and not by["m1"]["flaky"]
    assert by["m2"]["passed"] == 2 and by["m2"]["total"] == 3 and by["m2"]["flaky"]
    # Failed-run index is reported so reviewer can find which run broke it.
    assert by["m2"]["failed_on_runs"] == [1]


def test_metric_variance_empty_when_no_runs():
    assert CaseAggregate(case_id="c", runs=[]).metric_variance() == []
