"""Multiface keyword attribution + Amass normalization (Phase 3 review pt2).

Great Ugly-Looking Goblin // Clap! Snap!: the card-level Scryfall `Amass` keyword
belongs to Clap! Snap! (face :1, "Amass Goblins 2"), NOT the permanent face :0.
"""

import glob
import json
import re

from hobkg import pipeline
from hobkg.pipeline import REPO

CLAP_SNAP_1 = "face:27e17542-549b-4c05-8091-c10a245c916b:1"
GREAT_UGLY_0 = "face:27e17542-549b-4c05-8091-c10a245c916b:0"


def _rebuild():
    pipeline.run()
    pipeline.build_templates()


def _mechs():
    return [json.loads(l) for l in (REPO / "data/rules/mechanics.jsonl").read_text(encoding="utf-8").splitlines()]


def test_amass_attributed_to_supporting_face_not_primary():
    _rebuild()
    amass = {x["face_id"] for x in _mechs() if x["mechanic"] == "Amass"}
    assert CLAP_SNAP_1 in amass       # face whose Oracle says "Amass Goblins 2"
    assert GREAT_UGLY_0 not in amass  # not the permanent face


def test_no_multiface_keyword_on_unsupported_face():
    # Invariant: a card-level keyword is assigned to a multiface card's face only if
    # that face's Oracle text supports it (word-boundary). No primary-face fallback.
    _rebuild()
    faces = {json.loads(l)["id"]: json.loads(l)
             for l in (REPO / "data/normalized/faces.jsonl").read_text(encoding="utf-8").splitlines()}
    cards = {json.loads(l)["id"]: json.loads(l)
             for l in (REPO / "data/normalized/cards.jsonl").read_text(encoding="utf-8").splitlines()}
    for x in _mechs():
        if x["source"] != "scryfall_keyword":
            continue
        face = faces[x["face_id"]]
        if len(cards[face["card_id"]]["face_ids"]) < 2:
            continue  # single-face card: the card IS the face
        ot = face.get("oracle_text") or ""
        assert re.search(r"\b" + re.escape(x["mechanic"]) + r"\b", ot, re.I), \
            f"{x['mechanic']} attributed to unsupported multiface face {x['face_id']}"


def test_phase2_amass_instantiations_and_spans():
    _rebuild()
    nodes = {json.loads(l)["id"]: json.loads(l)
             for l in (REPO / "data/graph/nodes.jsonl").read_text(encoding="utf-8").splitlines()}
    edges = [json.loads(l) for l in (REPO / "data/graph/edges.jsonl").read_text(encoding="utf-8").splitlines()]
    assert f"op:{CLAP_SNAP_1}:amass" in nodes
    assert nodes[f"op:{CLAP_SNAP_1}:amass"]["data"] == {"army_subtype": "Goblins", "n": "2"}
    assert f"op:{GREAT_UGLY_0}:amass" not in nodes
    inst = [e for e in edges if e["predicate"] == "INSTANTIATES"
            and e["source"].endswith(":amass") and e["target"] == "op:amass"]
    assert len(inst) == 14
    ops = [n for n in nodes if n.startswith("op:face:") and n.endswith(":amass")]
    assert ops and all(nodes[n].get("provenance") and nodes[n]["provenance"][0].get("span") for n in ops)


def test_no_inline_amass_expansion_in_llm_layer():
    # count_inline_amass_expansions() == 0
    bad = [g for g in glob.glob(str(REPO / "data/llm/extractions/*.json"))
           if any(e["predicate"] == "CREATES_OBJECT" and e["target"] == "token:goblin-army"
                  for e in json.load(open(g, encoding="utf-8"))["proposed_edges"])]
    assert bad == []
