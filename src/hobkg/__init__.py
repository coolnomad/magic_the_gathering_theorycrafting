"""hobkg — deterministic normalization pipeline for the MTG—The Hobbit (HOB) set.

Phase 1 only: read the frozen Scryfall snapshot and emit validated, provenance-
bearing normalized entities (cards, faces, tokens) plus high-precision structural
parses (type lines, mana, exact syntactic extractions). No LLM, no graph assembly,
no card-pair projection, no value judgments. See docs/hob-knowledge-graph-build-spec.md.
"""

__version__ = "0.1.0"
