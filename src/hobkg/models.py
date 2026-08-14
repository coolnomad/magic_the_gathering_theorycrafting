"""Pydantic models for Phase 1 normalized entities.

These are the authoritative schema definitions. JSON Schema files under `schema/`
are generated from these models (see `hobkg.pipeline.export_schemas`), satisfying
the spec's discipline rule "write schemas ... before bulk LLM extraction."

Scope: entities produced by deterministic normalization only. Graph node/edge/gate
schemas are intentionally deferred to the assembly phase.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- provenance -------------------------------------------------------------

class Provenance(_Base):
    """A pointer back to the exact source of an asserted fact (principle #10)."""

    card_id: str
    face_id: Optional[str] = None
    source: str = Field(description="e.g. 'scryfall.keywords', 'scryfall.oracle_text', 'scryfall.all_parts'")
    span: Optional[tuple[int, int]] = Field(
        default=None, description="[start, end) char offsets into the cited text, when applicable"
    )
    text: Optional[str] = Field(default=None, description="verbatim matched substring, when applicable")
    rule_ref: Optional[str] = Field(default=None, description="Comprehensive Rules reference, when applicable")


# --- mana / types -----------------------------------------------------------

ManaSymbolKind = Literal[
    "generic", "colored", "colorless", "variable", "hybrid",
    "hybrid_mono", "phyrexian", "snow", "tap", "untap", "energy", "other",
]


class ManaSymbol(_Base):
    raw: str
    kind: ManaSymbolKind
    value: Optional[int] = Field(default=None, description="integer amount for generic symbols")
    colors: list[str] = Field(default_factory=list, description="WUBRG letters this symbol can represent")
    phyrexian: bool = False


class ManaCost(_Base):
    raw: str
    symbols: list[ManaSymbol] = Field(default_factory=list)
    generic: int = 0
    pips: dict[str, int] = Field(default_factory=dict, description="count of colored pip demand by color")
    has_variable: bool = False


class ParsedTypeLine(_Base):
    raw: str
    supertypes: list[str] = Field(default_factory=list)
    types: list[str] = Field(default_factory=list)
    subtypes: list[str] = Field(default_factory=list)


# --- entities ---------------------------------------------------------------

class Card(_Base):
    id: str                       # card:{oracle_id}
    oracle_id: str
    scryfall_id: str
    name: str
    set_code: str
    collector_number: str
    layout: str
    rarity: str
    color_identity: list[str] = Field(default_factory=list)
    colors: list[str] = Field(default_factory=list)
    cmc: Optional[float] = None
    keywords_scryfall: list[str] = Field(default_factory=list)
    face_ids: list[str] = Field(default_factory=list)


FaceRole = Literal["primary", "adventure"]


class Face(_Base):
    id: str                       # face:{oracle_id}:{index}
    card_id: str
    index: int
    role: FaceRole
    name: str
    type_line_raw: Optional[str] = None
    type_line: Optional[ParsedTypeLine] = None
    mana_cost_raw: Optional[str] = None
    mana_cost: Optional[ManaCost] = None
    oracle_text: Optional[str] = None
    power: Optional[str] = None
    toughness: Optional[str] = None
    produced_mana: list[str] = Field(default_factory=list)
    provenance: Provenance


class TokenSpec(_Base):
    id: str                       # token:{slug}
    name: str
    type_line_raw: Optional[str] = None
    type_line: Optional[ParsedTypeLine] = None
    produced_by_card_ids: list[str] = Field(default_factory=list)
    scryfall_related_ids: list[str] = Field(default_factory=list)
    provenance: list[Provenance] = Field(default_factory=list)


# --- mechanic detection -----------------------------------------------------

class MechanicDetection(_Base):
    face_id: str
    card_id: str
    mechanic: str
    source: Literal["scryfall_keyword", "oracle_text"]
    provenance: Provenance


# --- deterministic syntactic extraction ------------------------------------

ExtractionKind = Literal[
    "draw", "discard", "mill", "create_token", "sacrifice", "add_mana",
    "put_counter", "return_from_graveyard", "exile",
    "trigger_etb", "trigger_dies", "trigger_attacks", "trigger_upkeep",
    "trigger_end_step", "activated_ability",
]


class MechanicalExtraction(_Base):
    id: str
    face_id: str
    card_id: str
    kind: ExtractionKind
    quantity: Optional[int] = None
    detail: dict[str, str] = Field(default_factory=dict, description="parsed slots, e.g. {'counter_type': '+1/+1'}")
    qualifiers: list[str] = Field(default_factory=list, description="e.g. 'another', 'up_to', 'may', 'only_once_each_turn'")
    certainty: Literal["rules_explicit", "high"] = "high"
    provenance: Provenance


class UnresolvedExtraction(_Base):
    """A signal whose deterministic parse was ambiguous — queued for Phase 3 LLM.
    Per the spec: never guess; emit an unresolved task instead."""

    id: str
    face_id: str
    card_id: str
    signal: str = Field(description="the extraction kind the signal points at, e.g. 'draw'")
    reason: str
    provenance: Provenance


class ConditionRecord(_Base):
    """Deterministically-recoverable condition/limit stubs (e.g. 'only once each turn').
    Full structured gate conditions are built with mechanic templates in Phase 2."""

    condition_id: str
    face_id: str
    card_id: str
    kind: str
    human_readable: str
    provenance: Provenance


# --- Phase 2: graph primitives ---------------------------------------------

NodeType = Literal[
    "Card", "CardFace", "Ability", "Operation", "Event", "Resource",
    "ObjectClass", "Zone", "CounterType", "State", "Gate", "Cost",
    "Effect", "Rule", "TokenSpec",
]

Predicate = Literal[
    "HAS_FACE", "HAS_ABILITY", "HAS_TYPE", "HAS_KEYWORD", "HAS_COST",
    "REQUIRES", "CONSUMES", "PRODUCES", "CAUSES", "TRIGGERS", "MODIFIES",
    "COUNTS", "CONTRIBUTES_TO", "SATISFIES", "ENABLES", "PREVENTS",
    "REPLACES", "MOVES_FROM", "MOVES_TO", "CREATES_OBJECT", "ADDS_COUNTER",
    "REMOVES_COUNTER", "SCALES_WITH", "PERSISTS_AS", "REFERENCES_RULE",
    "DERIVED_FROM",
]


class Node(_Base):
    id: str
    type: NodeType
    label: str
    data: dict = Field(default_factory=dict)
    provenance: list[Provenance] = Field(default_factory=list)


class Edge(_Base):
    edge_id: str
    source: str
    target: str
    predicate: Predicate
    polarity: Literal["positive", "negative"] = "positive"
    scope: Optional[str] = None
    timing: Optional[str] = None
    condition_ids: list[str] = Field(default_factory=list)
    quantity: Optional[int] = None
    optional: bool = False
    certainty: Literal["rules_explicit", "high", "medium", "low"] = "rules_explicit"
    provenance: list[Provenance] = Field(default_factory=list)
    extractor: Literal["mechanical", "llm", "rule_expansion", "derived_projection"] = "rule_expansion"
    review_status: Literal["unreviewed", "accepted", "rejected"] = "accepted"


class Gate(_Base):
    gate_id: str
    gate_type: str
    label: str
    definition: dict = Field(default_factory=dict)
    output_state: Optional[str] = None
    provenance: list[Provenance] = Field(default_factory=list)


class StructuredCondition(_Base):
    condition_id: str
    expression: dict
    human_readable: str
    provenance: list[Provenance] = Field(default_factory=list)
