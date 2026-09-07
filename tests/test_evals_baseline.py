"""Tests for `evals/run.py`'s `--baseline` (no-tools) arm.

Golden and agent mode are exercised end to end elsewhere against the real
in-process MCP server (`tests/test_connector.py` notes as much for the
connector-alias cases). This mode never touches the MCP server, respx, or
any registry at all -- it makes exactly one kind of call, to the Anthropic
Messages API -- so every test here drives it with a small hand-rolled fake
client instead, the same "scripted fake client" approach `evals/README.md`
says agent mode's own loop mechanics were first validated with. None of
this needs the real `anthropic` package installed (it is deliberately kept
out of the project's runtime and `dev` dependencies -- see
`pyproject.toml`'s `eval` dependency group and `evals/README.md`'s cost
note), and none of it makes a network call of any kind.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import evals.run as run_module
import pytest

ALL_CASES = run_module.load_cases(None)
CASES_BY_ID = {c["id"]: c for c in ALL_CASES}

#: The exact 15 cases this arm's design selected (evals/README.md "The
#: baseline (no-tools) arm") -- a case whose whole point in --agent mode is
#: a tool-selection or trajectory choice (E14/E15/E17/E18/E23/E24/E25/E26,
#: every connector-alias case in group G) is meaningless without tools and
#: must never gain a `baseline` block.
EXPECTED_ELIGIBLE_IDS = {
    "E01", "E02", "E05", "E06", "E07", "E08", "E09", "E10",
    "E12", "E13", "E16", "E19", "E20", "E21", "E22",
}


def _case(case_id: str) -> dict[str, Any]:
    return CASES_BY_ID[case_id]


class _FakeUsage:
    def __init__(self, input_tokens: int = 11, output_tokens: int = 22) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class _FakeTextBlock:
    type = "text"

    def __init__(self, text: str) -> None:
        self.text = text


class _FakeMessage:
    def __init__(self, text: str, stop_reason: str = "end_turn") -> None:
        self.content = [_FakeTextBlock(text)]
        self.stop_reason = stop_reason
        self.usage = _FakeUsage()


class _FakeMessagesEndpoint:
    """Records every `create()` call's kwargs -- so a test can assert on
    exactly what was sent, in particular that no `tools`/`system` key was
    ever present, this mode's core safety property -- and returns queued
    fake answers in order."""

    def __init__(self, texts: list[str]) -> None:
        self.calls: list[dict[str, Any]] = []
        self._texts = list(texts)

    async def create(self, **kwargs: Any) -> _FakeMessage:
        self.calls.append(kwargs)
        text = self._texts.pop(0)
        return _FakeMessage(text)


class _FakeAsyncClient:
    def __init__(self, texts: list[str]) -> None:
        self.messages = _FakeMessagesEndpoint(texts)


class _FakeAnthropicModule:
    """Stands in for the real `anthropic` module. `run_baseline_mode` only
    ever calls `.AsyncAnthropic()` on whatever `_import_anthropic()`
    returns, so a plain object exposing exactly that is enough to drive it
    without the real package installed."""

    def __init__(self, client: _FakeAsyncClient) -> None:
        self._client = client

    def AsyncAnthropic(self) -> _FakeAsyncClient:
        return self._client


# ---------------------------------------------------------------------------
# cases.json: the 15 baseline-eligible cases are exactly the selected set,
# and each one is internally well-formed
# ---------------------------------------------------------------------------


def test_baseline_eligible_cases_are_the_selected_fifteen() -> None:
    eligible = [c for c in ALL_CASES if c.get("baseline", {}).get("eligible")]
    assert {c["id"] for c in eligible} == EXPECTED_ELIGIBLE_IDS


def test_baseline_blocks_are_well_formed() -> None:
    """Guards against silent drift -- a typo'd regex or a malformed signal
    list fails at test time, not at real-money spend time."""
    for case in ALL_CASES:
        baseline_cfg = case.get("baseline")
        if baseline_cfg is None:
            continue
        assert isinstance(baseline_cfg.get("why"), str) and baseline_cfg["why"]
        for key in ("correct_signals", "wrong_signals"):
            entries = baseline_cfg.get(key, [])
            assert isinstance(entries, list)
            for entry in entries:
                if isinstance(entry, list):
                    assert entry and all(isinstance(opt, str) and opt for opt in entry)
                else:
                    assert isinstance(entry, str) and entry
        pattern = baseline_cfg.get("wrong_pattern")
        if pattern is not None:
            re.compile(pattern)  # must be a valid regex


def test_baseline_eligible_cases_never_use_the_forbidden_identifier() -> None:
    """833286602 is off limits project-wide (see this task's own rules and
    E15's notes on why); this mode makes no network call regardless, but a
    future case reusing this id under a new case id should still trip this
    guard."""
    for case in ALL_CASES:
        if case.get("baseline", {}).get("eligible"):
            assert "833286602" not in case.get("prompt", "")


# ---------------------------------------------------------------------------
# classify_baseline_answer: the three-way (plus "unclear") scorer
# ---------------------------------------------------------------------------


def test_classify_correct_when_all_required_signals_present() -> None:
    verdict, _ = run_module.classify_baseline_answer(
        _case("E01"),
        "Company 923609016 is EQUINOR ASA, and it is currently active in Enhetsregisteret.",
    )
    assert verdict == "correct"


def test_classify_wrong_when_contradicting_fact_asserted() -> None:
    # Deliberately no "no"/"not"/"never" elsewhere in the sentence: the
    # shared negation-cue list `find_unnegated_occurrence` uses is a blunt,
    # whole-sentence heuristic (documented in evals/README.md's "Known
    # limitations"), so a phrase like "no longer trades" nearby would
    # itself read as a negation cue and defeat this assertion for a reason
    # unrelated to what this test checks.
    verdict, evidence = run_module.classify_baseline_answer(
        _case("E01"), "Equinor ASA (923609016) was dissolved in 2019."
    )
    assert verdict == "wrong"
    assert "dissolved" in evidence


def test_classify_hedge_when_pure_capability_refusal() -> None:
    verdict, _ = run_module.classify_baseline_answer(
        _case("E01"),
        "I don't have access to a live business register, so I can't confirm Equinor's current status.",
    )
    assert verdict == "hedge"


def test_classify_unclear_when_no_signal_fires() -> None:
    verdict, evidence = run_module.classify_baseline_answer(
        _case("E01"), "Equinor is a large Norwegian energy company."
    )
    assert verdict == "unclear"
    assert "manual read" in evidence


def test_classify_wrong_takes_priority_over_correct() -> None:
    """A confidently wrong claim must be flagged even when the same answer
    also contains a correct-looking phrase elsewhere -- the dangerous case
    must never be masked by a coincidental hit (see the module note above
    `classify_baseline_answer` in evals/run.py)."""
    verdict, evidence = run_module.classify_baseline_answer(
        _case("E01"),
        "Some directories list Equinor as dissolved, though other pages describe it as active.",
    )
    assert verdict == "wrong"
    assert "dissolved" in evidence


def test_classify_negation_aware_correct_not_flagged_wrong() -> None:
    """Reuses `find_unnegated_occurrence` -- a correctly-negated wrong claim
    ('is not dissolved') must not itself trigger the wrong verdict, and the
    answer should fall through to its real correct signals."""
    verdict, _ = run_module.classify_baseline_answer(
        _case("E01"), "Equinor ASA is not dissolved; it remains active and trading."
    )
    assert verdict == "correct"


def test_classify_wrong_pattern_flags_unsourced_employee_count() -> None:
    verdict, evidence = run_module.classify_baseline_answer(
        _case("E20"), "Tesco PLC has approximately 345,000 employees according to public reports."
    )
    assert verdict == "wrong"
    assert "345,000 employees" in evidence


def test_classify_wrong_pattern_not_checked_once_correct_signal_fires() -> None:
    """A properly-caveated mention of a public headcount figure is not
    penalised for the number itself -- `wrong_pattern` is only a fallback,
    checked after `correct_signals`."""
    verdict, _ = run_module.classify_baseline_answer(
        _case("E20"),
        "Companies House does not publish employee counts, though Tesco is widely "
        "reported to employ around 345,000 people.",
    )
    assert verdict == "correct"


def test_classify_case_with_no_baseline_block_is_always_unclear() -> None:
    """E23 is deliberately excluded (a tool-restraint case, meaningless
    without tools) and carries no `baseline` block -- it has no signals to
    match, so any text falls through to 'unclear' rather than erroring."""
    verdict, _ = run_module.classify_baseline_answer(_case("E23"), "anything at all")
    assert verdict == "unclear"


# ---------------------------------------------------------------------------
# run_baseline_case: one case end to end, against a fake client
# ---------------------------------------------------------------------------


async def test_run_baseline_case_sends_no_tools_and_no_system() -> None:
    """The entire point of this mode: the API call must carry no `tools`
    and no `system`. If either ever creeps back in, the arm silently stops
    measuring the counterfactual it exists to measure."""
    case = _case("E01")
    client = _FakeAsyncClient(["Equinor ASA is active."])
    await run_module.run_baseline_case(client, "claude-sonnet-5", case, trials=1)

    assert len(client.messages.calls) == 1
    sent = client.messages.calls[0]
    assert "tools" not in sent
    assert "system" not in sent
    assert sent["model"] == "claude-sonnet-5"
    assert sent["messages"] == [{"role": "user", "content": case["prompt"]}]


async def test_run_baseline_case_records_full_transcript_and_verdict() -> None:
    case = _case("E01")
    client = _FakeAsyncClient(["Equinor ASA (923609016) is active and still trading."])
    result = await run_module.run_baseline_case(client, "claude-sonnet-5", case, trials=1)

    assert result.case_id == "E01"
    assert result.group == "A"
    assert result.status == "measured"
    assert result.why  # every eligible case carries a non-empty reason
    assert len(result.trials) == 1
    trial = result.trials[0]
    assert trial.verdict == "correct"
    assert trial.response_text == "Equinor ASA (923609016) is active and still trading."
    assert trial.input_tokens == 11
    assert trial.output_tokens == 22
    assert trial.stop_reason == "end_turn"
    assert trial.requested_at  # non-empty ISO timestamp


async def test_run_baseline_case_makes_one_call_per_trial() -> None:
    case = _case("E19")
    client = _FakeAsyncClient(
        [
            "Companies House does not publish VAT registration status.",
            "I can't verify VAT status without a live register.",
            "Tesco is not VAT-registered.",
        ]
    )
    result = await run_module.run_baseline_case(client, "claude-sonnet-5", case, trials=3)

    assert len(client.messages.calls) == 3
    assert [t.verdict for t in result.trials] == ["correct", "hedge", "wrong"]


# ---------------------------------------------------------------------------
# run_baseline_mode: cost-control skip paths, and the eligibility filter
# ---------------------------------------------------------------------------


async def test_run_baseline_mode_skips_cleanly_without_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    results = await run_module.run_baseline_mode(ALL_CASES, "claude-sonnet-5", 1)

    assert {r.case_id for r in results} == EXPECTED_ELIGIBLE_IDS
    assert all(r.status == "skip" for r in results)
    assert all(r.skip_reason == "ANTHROPIC_API_KEY is not set" for r in results)
    assert all(r.trials == [] for r in results)


async def test_run_baseline_mode_skips_cleanly_without_anthropic_package(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake-for-test-only")
    monkeypatch.setattr(run_module, "_import_anthropic", lambda: None)
    results = await run_module.run_baseline_mode(ALL_CASES, "claude-sonnet-5", 1)

    assert all(r.status == "skip" for r in results)
    assert all(r.skip_reason == "anthropic package not installed" for r in results)


async def test_run_baseline_mode_only_runs_eligible_cases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A case with no `baseline` block (e.g. E23) must never be asked --
    confirms the eligibility filter, independent of the skip-path tests
    above."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake-for-test-only")
    fake_client = _FakeAsyncClient(["placeholder"] * len(EXPECTED_ELIGIBLE_IDS))
    monkeypatch.setattr(run_module, "_import_anthropic", lambda: _FakeAnthropicModule(fake_client))

    results = await run_module.run_baseline_mode(ALL_CASES, "claude-sonnet-5", 1)

    assert {r.case_id for r in results} == EXPECTED_ELIGIBLE_IDS
    assert len(fake_client.messages.calls) == len(EXPECTED_ELIGIBLE_IDS)


# ---------------------------------------------------------------------------
# Rendering: the markdown table and the full-fidelity JSON sidecar
# ---------------------------------------------------------------------------


def test_render_baseline_markdown_table_and_summary_counts() -> None:
    results = [
        run_module.BaselineResult(
            case_id="E01",
            group="A",
            prompt="p1",
            why="w1",
            status="measured",
            trials=[
                run_module.BaselineTrial(
                    "2026-01-01T00:00:00+00:00", "resp1", "end_turn", 1, 2, "correct", "ev1"
                )
            ],
        ),
        run_module.BaselineResult(
            case_id="E02", group="A", prompt="p2", why="w2", status="skip", skip_reason="no key"
        ),
    ]
    table = run_module.render_baseline_markdown(results, "claude-sonnet-5")

    assert "1 correct, 0 wrong" in table
    assert "1 case(s) skipped" in table
    assert "1 model call(s) made" in table
    assert "E01" in table
    assert "E02" in table


def test_baseline_results_to_json_round_trips_full_untruncated_text() -> None:
    long_text = "x" * 500  # longer than the markdown table's excerpt window
    results = [
        run_module.BaselineResult(
            case_id="E01",
            group="A",
            prompt="p1",
            why="w1",
            status="measured",
            trials=[
                run_module.BaselineTrial(
                    "2026-01-01T00:00:00+00:00", long_text, "end_turn", 1, 2, "correct", "ev1"
                )
            ],
        ),
    ]
    payload = run_module.baseline_results_to_json(results, "claude-sonnet-5")

    assert payload["model"] == "claude-sonnet-5"
    assert payload["total_calls"] == 1
    assert payload["cases"][0]["trials"][0]["response_text"] == long_text
    json.dumps(payload)  # must be JSON-serialisable


# ---------------------------------------------------------------------------
# CLI wiring: opt-in only, never bundled with the CI-run --golden default
# ---------------------------------------------------------------------------


def test_default_flags_run_golden_only() -> None:
    args = run_module.parse_args([])
    assert args.golden is True
    assert args.agent is False
    assert args.baseline is False


def test_baseline_flag_is_opt_in_and_does_not_enable_golden() -> None:
    args = run_module.parse_args(["--baseline"])
    assert args.golden is False
    assert args.agent is False
    assert args.baseline is True


def test_ci_invocation_never_touches_baseline() -> None:
    """CI's literal invocation (`.github/workflows/ci.yml`) is
    `python evals/run.py --golden` -- confirms it can never accidentally
    also run the paid --baseline arm."""
    args = run_module.parse_args(["--golden"])
    assert args.baseline is False


# ---------------------------------------------------------------------------
# main_async: baseline verdicts never affect the exit code, and
# --baseline-json writes the full record
# ---------------------------------------------------------------------------


async def test_baseline_verdicts_never_affect_exit_code(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 'wrong' verdict is an expected, informative measurement, not a
    harness failure -- it must never fail a CI-adjacent run."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake-for-test-only")
    fake_client = _FakeAsyncClient(["Equinor was dissolved and no longer trades."])
    monkeypatch.setattr(run_module, "_import_anthropic", lambda: _FakeAnthropicModule(fake_client))

    args = run_module.parse_args(["--baseline", "--case", "E01"])
    exit_code = await run_module.main_async(args)

    assert exit_code == 0


async def test_baseline_json_written_when_requested(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake-for-test-only")
    fake_client = _FakeAsyncClient(["Equinor ASA is active."])
    monkeypatch.setattr(run_module, "_import_anthropic", lambda: _FakeAnthropicModule(fake_client))
    out = tmp_path / "baseline.json"

    args = run_module.parse_args(["--baseline", "--case", "E01", "--baseline-json", str(out)])
    exit_code = await run_module.main_async(args)

    assert exit_code == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["cases"][0]["id"] == "E01"
    assert payload["cases"][0]["trials"][0]["response_text"] == "Equinor ASA is active."
