"""The environment guard: refuse to fit when the stack is not the pinned one.

Governed by ``docs/MTG_Deck-Strength_Modeling_Benchmark.md``. Section 8 holds the
learner family constant so that a difference between two models is attributable
to the representation or the target formulation and not to the algorithm. That
requirement is not satisfied by pinning a version in ``pyproject.toml``: a pin
binds an *installation*, and this project is fitted from more than one.

**What went wrong, and why this module exists.** The compact orchestrator runs
its executor inside ``C:/GitHub/control_plane/.venv``; an interactive session in
this repo runs a different interpreter entirely. Those two environments drifted
apart across the whole numerical stack -- xgboost 3.4.1 against 3.1.2, numpy
2.5.1 against 2.3.5, pandas 3.0.3 against 2.3.3, pyarrow 25.0.1 against 22.0.0 --
and nothing noticed, because none of those packages is a declared dependency of
the orchestrator. Cards 011 and 014 fitted T0 under one stack and later refits
produced a *different grid point* (``max_depth`` 3 to 4, 367 boosting rounds to
136). Six models are compared against each other in a single irreversible
holdout read at card 017; one of them having been built by a different library
version is precisely the confound section 8 forbids.

The environments were aligned by hand on 2026-09-10 and a T2 refit in the
orchestrator's venv then reproduced all six committed artifacts byte-for-byte.
But hand-alignment is a fact about a machine on a day. This module makes it a
fact about the code: every fit checks, and a mismatched stack stops the run
instead of quietly producing artifacts that cannot be compared with the ones
already on disk.

**Scope: only what can change the bytes.** ``deckbench`` imports exactly three
packages that can affect a fitted artifact -- ``xgboost`` trains, ``numpy``
carries the arithmetic, and ``pyarrow`` writes the prediction and reconstruction
parquets whose byte-identity is an acceptance criterion. ``pandas``,
``scikit-learn`` and ``scipy`` appear in the ``modeling`` extra but are not
imported anywhere under ``src/deckbench``, so they cannot move a result and are
deliberately not pinned here. Pinning things that cannot matter trains people to
ignore the guard.

**There is no override.** A pin that can be switched off under deadline is not a
pin. Changing the stack is allowed -- it is a deliberate, recorded decision that
edits :data:`PINNED_VERSIONS` and ``pyproject.toml`` together, and invalidates
every artifact under ``data/runs/``, which is exactly the weight such a change
deserves.

Run ``python -m deckbench.environment`` to report the current stack against the
pins; it exits non-zero on a mismatch, so it works as a task-card check.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from importlib.metadata import PackageNotFoundError, version

# The stack every artifact under data/runs/ was fitted with. Changing a value
# here is a decision to invalidate those artifacts; change pyproject.toml's
# `modeling` extra in the same commit and refit.
PINNED_VERSIONS: dict[str, str] = {
    "xgboost": "3.1.2",
    "numpy": "2.3.5",
    "pyarrow": "22.0.0",
}


class EnvironmentMismatch(RuntimeError):
    """Raised when the installed stack is not the pinned one.

    Fitting under a different stack produces artifacts that cannot honestly be
    compared with the ones already on disk, so this stops the run rather than
    adding an incomparable model to a benchmark whose whole point is comparison.
    """


def installed_versions() -> dict[str, str | None]:
    """Return the installed version of each pinned package, ``None`` if absent.

    Read from distribution metadata rather than by importing, so the check is
    cheap and does not depend on a package being importable in this process.
    """
    found: dict[str, str | None] = {}
    for package in PINNED_VERSIONS:
        try:
            found[package] = version(package)
        except PackageNotFoundError:
            found[package] = None
    return found


def environment_problems() -> list[str]:
    """Return one human-readable problem per package that is missing or wrong.

    Empty means the stack matches the pins exactly.
    """
    problems: list[str] = []
    for package, pinned in sorted(PINNED_VERSIONS.items()):
        actual = installed_versions()[package]
        if actual is None:
            problems.append(f"{package} is not installed; {pinned} is pinned")
        elif actual != pinned:
            problems.append(f"{package} is {actual}; {pinned} is pinned")
    return problems


def require_pinned_environment() -> None:
    """Raise :class:`EnvironmentMismatch` unless the stack matches the pins.

    Called at the top of :func:`deckbench.estimator.fit_and_predict`, the single
    path every benchmark model is fitted through, so no model can be produced
    under an unpinned stack by any route.
    """
    problems = environment_problems()
    if not problems:
        return
    raise EnvironmentMismatch(
        "the installed stack does not match the pinned one, so a fit here would "
        "produce artifacts that cannot be compared with those already in "
        "data/runs/:\n  - "
        + "\n  - ".join(problems)
        + f"\ninterpreter: {sys.executable}\n"
        "Either use the interpreter the existing artifacts were fitted with, or "
        "change deckbench.environment.PINNED_VERSIONS and pyproject.toml "
        "together and refit every model -- a mismatched stack has already "
        "changed a chosen grid point on this project (see the LABNOTEBOOK entry "
        "[2026-09-10 20:15])."
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Report the stack against the pins. Non-zero exit on a mismatch."""
    del argv
    actual = installed_versions()
    width = max(len(p) for p in PINNED_VERSIONS)
    print(f"interpreter: {sys.executable}")
    for package, pinned in sorted(PINNED_VERSIONS.items()):
        got = actual[package] or "NOT INSTALLED"
        mark = "ok " if got == pinned else "BAD"
        print(f"  [{mark}] {package:<{width}}  pinned {pinned:<10} installed {got}")
    problems = environment_problems()
    if problems:
        print("\nenvironment MISMATCH:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("\nenvironment OK: the stack matches the pins")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
