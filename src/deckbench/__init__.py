"""deckbench -- the rebuilt deck-strength modeling arm.

This package holds the card-driven rebuild governed by
``docs/MTG_Deck-Strength_Modeling_Benchmark.md``. The first module is the
section-17 data audit (:mod:`deckbench.audit`); it produces reports only and
fits no model.
"""

__all__ = ["audit"]
