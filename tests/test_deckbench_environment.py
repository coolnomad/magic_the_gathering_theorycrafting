"""The environment guard must actually stop a fit, not merely agree with today.

A guard that only ever passes is indistinguishable from no guard at all, so the
load-bearing tests here are the ones that *break* the environment and require the
failure: `test_fit_and_predict_refuses_under_a_mismatched_stack` is the one that
matters, because it exercises the real fitting entry point rather than the check
in isolation.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from test_deckbench_estimator import _Wired

from deckbench import environment, estimator


@pytest.fixture
def wired(tmp_path: Path) -> _Wired:
    """The same fixture the estimator tests use; it is defined there."""
    return _Wired(tmp_path)


def test_the_current_stack_matches_the_pins() -> None:
    """The artifacts in data/runs/ were fitted with exactly this stack."""
    assert environment.environment_problems() == []
    assert environment.require_pinned_environment() is None


def test_pins_cover_every_package_that_can_change_an_artifact() -> None:
    """xgboost trains, numpy computes, pyarrow writes the parquets.

    Pinning fewer would leave a route to divergence; pinning packages deckbench
    never imports would train people to ignore the guard.
    """
    assert set(environment.PINNED_VERSIONS) == {"xgboost", "numpy", "pyarrow"}


def test_a_wrong_version_is_reported_as_a_problem(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(environment.PINNED_VERSIONS, "numpy", "0.0.1-not-installed")
    problems = environment.environment_problems()
    assert len(problems) == 1
    assert "numpy" in problems[0]
    assert "0.0.1-not-installed is pinned" in problems[0]


def test_a_missing_package_is_reported_as_a_problem(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(environment.PINNED_VERSIONS, "not-a-real-package", "1.0.0")
    problems = environment.environment_problems()
    assert any("not-a-real-package is not installed" in p for p in problems)


def test_require_raises_and_names_what_is_wrong(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(environment.PINNED_VERSIONS, "pyarrow", "0.0.1")
    with pytest.raises(environment.EnvironmentMismatch) as excinfo:
        environment.require_pinned_environment()
    message = str(excinfo.value)
    assert "pyarrow" in message
    assert "0.0.1 is pinned" in message
    # The message has to be actionable: it must say which interpreter was used,
    # because the whole failure mode is "the wrong one was on PATH".
    assert "interpreter:" in message


def test_fit_and_predict_refuses_under_a_mismatched_stack(
    wired: _Wired, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The guard must bite on the real fitting path, before anything is written.

    This is the non-vacuous half: the other tests could all pass while
    `fit_and_predict` never consulted the guard at all.
    """
    monkeypatch.setitem(environment.PINNED_VERSIONS, "xgboost", "0.0.1-wrong")

    with pytest.raises(environment.EnvironmentMismatch):
        estimator.fit_and_predict(
            wired.features, wired.y_binary, **wired.kwargs(model_id="guard_probe")
        )

    # Nothing may be left behind by a refused fit.
    assert not (wired.runs_dir / "guard_probe_run.json").exists()
    assert not (wired.runs_dir / "guard_probe.xgb").exists()
    assert not (wired.runs_dir / "guard_probe_predictions.parquet").exists()


def test_fit_and_predict_still_works_when_the_stack_matches(wired: _Wired) -> None:
    """The guard must not block the legitimate path -- the control for the above."""
    result = estimator.fit_and_predict(
        wired.features, wired.y_binary, **wired.kwargs(model_id="guard_control")
    )
    assert result.run_record["model_id"] == "guard_control"
    assert np.isfinite(np.asarray(result.predictions)).all()


def test_cli_reports_ok_on_a_matching_stack(capsys: pytest.CaptureFixture[str]) -> None:
    assert environment.main([]) == 0
    assert "environment OK" in capsys.readouterr().out


def test_cli_exits_non_zero_on_a_mismatch(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setitem(environment.PINNED_VERSIONS, "numpy", "0.0.1")
    assert environment.main([]) == 1
    assert "MISMATCH" in capsys.readouterr().out
