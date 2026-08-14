"""Deterministic card/face/token normalization (spec Phase 1).

Turns raw Scryfall card records into Card + Face entities, preserving each
Adventure face independently, and extracts TokenSpec nodes from `all_parts`
(verified against Oracle text where possible). No LLM. No value judgments.
"""

from __future__ import annotations

import re

from .mana import parse_mana_cost
from .models import Card, Face, Provenance, TokenSpec
from .types import parse_type_line


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _face_provenance(card_id: str, face_id: str) -> Provenance:
    return Provenance(card_id=card_id, face_id=face_id, source="scryfall.card")


def _build_face(card_id: str, oracle_id: str, index: int, src: dict) -> Face:
    face_id = f"face:{oracle_id}:{index}"
    type_line_raw = src.get("type_line")
    parsed = parse_type_line(type_line_raw)
    role = "adventure" if (parsed and "Adventure" in parsed.subtypes) else "primary"
    return Face(
        id=face_id,
        card_id=card_id,
        index=index,
        role=role,
        name=src.get("name", ""),
        type_line_raw=type_line_raw,
        type_line=parsed,
        mana_cost_raw=src.get("mana_cost"),
        mana_cost=parse_mana_cost(src.get("mana_cost")),
        oracle_text=src.get("oracle_text"),
        power=src.get("power"),
        toughness=src.get("toughness"),
        produced_mana=src.get("produced_mana", []),
        provenance=_face_provenance(card_id, face_id),
    )


def normalize_card(raw: dict) -> tuple[Card, list[Face]]:
    """Normalize one raw Scryfall record into a Card and its Face list."""
    oracle_id = raw["oracle_id"]
    card_id = f"card:{oracle_id}"

    if raw["layout"] == "adventure":
        faces = [_build_face(card_id, oracle_id, i, f) for i, f in enumerate(raw["card_faces"])]
    else:
        # Single top-level face. produced_mana lives at top level on Scryfall.
        top = dict(raw)
        faces = [_build_face(card_id, oracle_id, 0, top)]

    card = Card(
        id=card_id,
        oracle_id=oracle_id,
        scryfall_id=raw["id"],
        name=raw["name"],
        set_code=raw["set"],
        collector_number=raw["collector_number"],
        layout=raw["layout"],
        rarity=raw["rarity"],
        color_identity=raw.get("color_identity", []),
        colors=raw.get("colors", []),
        cmc=raw.get("cmc"),
        keywords_scryfall=raw.get("keywords", []),
        face_ids=[f.id for f in faces],
    )
    return card, faces


def extract_tokens(raw: dict, card_id: str) -> list[TokenSpec]:
    """Extract token specification nodes from `all_parts` component == 'token'.

    Verified-against-text is handled by the caller (which knows the card's Oracle
    text); here we surface the token components with provenance so they can be
    canonicalized/deduped globally in the pipeline.
    """
    out: list[TokenSpec] = []
    for part in raw.get("all_parts", []):
        if part.get("component") != "token":
            continue
        name = part.get("name", "")
        type_line_raw = part.get("type_line")
        out.append(
            TokenSpec(
                id=f"token:{_slug(name)}",
                name=name,
                type_line_raw=type_line_raw,
                type_line=parse_type_line(type_line_raw),
                produced_by_card_ids=[card_id],
                scryfall_related_ids=[part["id"]] if part.get("id") else [],
                provenance=[
                    Provenance(card_id=card_id, source="scryfall.all_parts", text=name)
                ],
            )
        )
    return out


def enrich_tokens(tokens: list[TokenSpec], token_raw_by_id: dict[str, dict]) -> None:
    """Hydrate token specs in place from fetched Scryfall token objects (colors, P/T,
    keywords, Oracle text, produced mana) so later phases can reason about token
    characteristics, not just names/type lines (Phase 2 review #8)."""
    for t in tokens:
        raw = next((token_raw_by_id[rid] for rid in t.scryfall_related_ids if rid in token_raw_by_id), None)
        if raw is None:
            continue
        t.colors = raw.get("colors", [])
        t.power = raw.get("power")
        t.toughness = raw.get("toughness")
        t.keywords = raw.get("keywords", [])
        t.oracle_text = raw.get("oracle_text")
        t.produced_mana = raw.get("produced_mana", [])
        t.mana_cost = parse_mana_cost(raw.get("mana_cost"))
        if raw.get("type_line"):
            t.type_line_raw = raw["type_line"]
            t.type_line = parse_type_line(raw["type_line"])
        t.enriched = True


def canonicalize_tokens(token_lists: list[list[TokenSpec]]) -> list[TokenSpec]:
    """Merge duplicate token specs (same id) across all producing cards."""
    merged: dict[str, TokenSpec] = {}
    for lst in token_lists:
        for t in lst:
            if t.id in merged:
                m = merged[t.id]
                for cid in t.produced_by_card_ids:
                    if cid not in m.produced_by_card_ids:
                        m.produced_by_card_ids.append(cid)
                for rid in t.scryfall_related_ids:
                    if rid not in m.scryfall_related_ids:
                        m.scryfall_related_ids.append(rid)
                m.provenance.extend(t.provenance)
            else:
                merged[t.id] = t.model_copy(deep=True)
    return list(merged.values())
