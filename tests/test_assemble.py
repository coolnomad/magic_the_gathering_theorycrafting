"""Phase 4 global assembly gate tests (v2).

The gate is strict: zero dangling endpoints, zero unknown types, zero signature
violations, zero leaked (non-face-namespaced) LLM ability aliases, zero
unintended template duplicates, every edge carries a stable edge_id, and every
condition reference resolves in the self-contained global conditions file.
"""

import json

import pytest

from hobkg import assemble
from hobkg.pipeline import REPO

GLOBAL = REPO / "data" / "graph_global"


@pytest.fixture(scope="module")
def stats():
    return assemble.assemble()


@pytest.fixture(scope="module")
def edges():
    return [json.loads(l) for l in (GLOBAL / "edges.jsonl").read_text(encoding="utf-8").splitlines()]


@pytest.fixture(scope="module")
def nodes():
    return {json.loads(l)["id"]: json.loads(l)
            for l in (GLOBAL / "nodes.jsonl").read_text(encoding="utf-8").splitlines()}


# --- blocking issue 1 + the reviewer's original gate -------------------------
def test_gate_all_zero(stats):
    """Every gate metric must be exactly zero — no weakened bound, no residual."""
    for k in ("dangling_edges", "signature_violations", "unknown_endpoint_edges",
              "unknown_type_nodes", "leaked_ability_aliases", "unresolved_condition_refs",
              "edges_missing_id", "template_duplicate_edges", "face_to_rule_amass_edges"):
        assert stats[k] == 0, f"{k} = {stats[k]} (must be 0)"


def test_seven_corrections_landed(edges, nodes):
    def has(s, p, t):
        return any(e["source"] == s and e["predicate"] == p and e["target"] == t for e in edges)
    # the two bogus reified-op targets are gone entirely
    assert "op:add-mana" not in nodes and "op:gain-life" not in nodes
    # Food: sac the artifact -> consume Food, produce life
    food = "op:face:4d891515-39da-492e-ac19-1aa524245449:0:granted-food-sac"
    assert has(food, "CONSUMES", "obj:food") and has(food, "PRODUCES", "resource:life")
    # Gollum: return this card from graveyard -> MOVES_FROM a Zone
    assert has("op:face:8d88facd-cf7e-498e-ab6b-6bd021316162:0:gollum-ab-recur",
               "MOVES_FROM", "zone:graveyard")
    # Bolg: sacrifice a Goblin -> consume the Goblin + cause the sacrifice event
    assert any(e["predicate"] == "CAUSES" and e["target"] == "event:sacrifice"
               and e["source"].startswith("op:face:fa602f8f") for e in edges)
    # Dwarven Mattock: the Equipment face attaches to the Dwarf
    assert has("face:f75bb13b-41fc-4614-b35e-f456069ce9c6:0", "ATTACHED_TO",
               "obj:target-dwarf-you-control")
    # Vow to Erebor: a generic Equipment object attaches to the creature
    assert has("obj:an-equipment-you-control", "ATTACHED_TO", "obj:target-creature-you-control")


# --- blocking issue 2: no leaked ability aliases -----------------------------
def test_no_leaked_ability_nodes(nodes):
    leaked = [nid for nid in nodes
              if nid.startswith("ability:") and not nid.startswith("ability:face:")]
    assert leaked == []
    # 418 LLM abilities (face-namespaced) + 29 Phase 2 (`ab:` prefix) = 447
    assert sum(1 for n in nodes.values() if n["type"] == "Ability") == 447


# --- blocking issue 3: conditions + edge properties preserved ----------------
def test_conditions_self_contained_and_referenced(edges):
    cond_ids = {json.loads(l)["condition_id"]
                for l in (GLOBAL / "conditions.jsonl").read_text(encoding="utf-8").splitlines()}
    referenced = {c for e in edges for c in (e.get("condition_ids") or [])}
    assert referenced and referenced <= cond_ids            # every reference resolves
    # inline free-text conditions became structured records with ids
    assert any(e.get("condition_ids") for e in edges)


def test_edge_properties_preserved(edges):
    # scope / timing / optional / polarity / certainty survive onto global edges
    assert any(e.get("scope") for e in edges)
    assert any(e.get("timing") for e in edges)
    assert any(e.get("certainty") for e in edges)
    assert any(e.get("polarity") for e in edges)


# --- blocking issue 4: ability semantics retained ----------------------------
def test_ability_semantics_retained(nodes):
    ab = nodes["ability:face:008a11c1-d283-49fe-abd7-ff4fe8b1fe79:0:rampager-attack-sac"]["data"]
    for field in ("trigger", "costs", "conditions", "effects", "kind", "confidence"):
        assert field in ab, f"ability node dropped {field}"
    assert ab["effects"], "ability effects must be retained, not discarded"


# --- blocking issue 5: property multigraph + stable edge ids -----------------
def test_property_multigraph_and_edge_ids(edges):
    assert all(e.get("edge_id") for e in edges)
    assert len({e["edge_id"] for e in edges}) == len(edges)        # unique
    # parallel edges that differ only by a meaningful property coexist
    from collections import defaultdict
    grp = defaultdict(list)
    for e in edges:
        grp[(e["source"], e["predicate"], e["target"])].append(e)
    parallels = [es for es in grp.values() if len(es) > 1]
    assert parallels, "property multigraph should preserve at least one parallel edge"
    for es in parallels:                                            # each pair truly differs
        sigs = {(tuple(sorted(e.get("condition_ids") or [])), e.get("scope"),
                 e.get("timing"), str(e.get("quantity")), bool(e.get("optional")),
                 e.get("polarity") or "positive") for e in es}
        assert len(sigs) == len(es)


# --- blocking issue 6: reification grouped by ability/clause ------------------
def test_reification_grouped_by_ability(edges, nodes):
    # actor edges are Operation/Gate-subject
    for e in edges:
        if e["predicate"] in ("MOVES_TO", "MOVES_FROM", "ADDS_COUNTER", "CREATES_OBJECT"):
            assert nodes[e["source"]]["type"] in ("Operation", "Gate")
    # the old per-edge `op:{face}:effN` splitting is gone
    assert not any(":eff" in nid for nid in nodes)
    # Rampager's attack-sac ability: its consequences hang off ONE operation
    op = "op:face:008a11c1-d283-49fe-abd7-ff4fe8b1fe79:0:rampager-attack-sac"
    outs = {(e["predicate"], e["target"]) for e in edges if e["source"] == op}
    assert ("CONSUMES", "obj:another-creature") in outs
    assert ("ADDS_COUNTER", "counter:+1/+1") in outs


# --- blocking issue 7 + amass invariant --------------------------------------
def test_template_dedup_all_mechanics(edges):
    # no LLM re-derivation of template-owned outputs survives from a non-owner source
    for e in edges:
        if e["predicate"] == "INSTANTIATES":
            assert e["target"] not in ("rule:amass", "rule:typecycling")
        if e["predicate"] in ("CREATES_OBJECT", "CAN_LEAD_TO"):
            if e["target"] in ("token:human-soldier", "token:goblin-army", "obj:army-A"):
                assert e["source"].startswith("gate:")     # only the Phase 2 gate creates them
    # amass canonical: 14 op:{face}:amass INSTANTIATES op:amass
    op_amass = [e for e in edges if e["predicate"] == "INSTANTIATES"
                and e["target"] == "op:amass" and e["source"].endswith(":amass")]
    assert len(op_amass) == 14


def test_all_faces_and_cards_present(stats):
    assert stats["node_types"]["Card"] == 193
    assert stats["node_types"]["CardFace"] == 210


# --- v3 completeness gate (blocking issues 1 & 2) ----------------------------
def test_completeness_gate_all_zero(stats):
    for k in ("faces_missing_type_data", "faces_missing_type_edges", "faces_missing_cost_edge",
              "mana_faces_without_mana_path", "false_direct_mana_operations",
              "materialized_edges_without_provenance", "tokens_missing_characteristics"):
        assert stats[k] == 0, f"{k} = {stats[k]} (must be 0)"


def test_faces_retain_normalized_characteristics(nodes):
    creature = nodes["face:6f83da19-fd89-44ec-88f3-0c3fddfbd1b2:0"]["data"]
    for field in ("type_line", "mana_cost", "power", "toughness", "produced_mana", "oracle_text", "role"):
        assert field in creature
    # canonical type edges exist for a Goblin, an Island (land), etc.
    assert "obj:subtype:dog" in nodes and nodes["obj:subtype:dog"]["type"] == "ObjectClass"


def test_cards_retain_metadata(nodes):
    card = nodes["card:6f83da19-fd89-44ec-88f3-0c3fddfbd1b2"]["data"]
    for field in ("layout", "rarity", "color_identity", "cmc", "set_code", "scryfall_id"):
        assert field in card


def test_all_tokens_have_characteristics(nodes, stats):
    tokens = [n for n in nodes.values() if n["type"] == "TokenSpec"]
    assert len(tokens) == 12
    for t in tokens:
        assert t["data"].get("type_line"), f"token {t['id']} missing type_line"
    assert stats["tokens_missing_characteristics"] == 0


# --- v3 conditions gate (blocking issue 3) -----------------------------------
def test_conditions_structured_or_marked_unresolved(stats):
    conds = [json.loads(l) for l in (GLOBAL / "conditions.jsonl").read_text(encoding="utf-8").splitlines()]
    # no raw condition may be executable, and every raw one is explicitly unresolved
    assert stats["raw_executable_conditions"] == 0
    assert stats["raw_conditions_not_marked_unresolved"] == 0
    for c in conds:
        if c.get("expression", {}).get("raw") is not None:
            assert c["status"] == "raw_unresolved" and c.get("executable") is False
    assert stats["structured_conditions"] > 0        # common families were converted


# --- v3 Adventure path-level dedup gate (blocking issue 4) --------------------
def test_adventure_path_dedup(stats, edges):
    assert stats["adventure_faces"] == 17
    assert stats["adventure_resolution_state_paths"] == 17
    assert stats["llm_reminder_adventure_exile_paths"] == 0
    # the authoritative resolution path carries the merged reminder provenance
    resolve = [e for e in edges
               if e["source"] == "op:face:27e17542-549b-4c05-8091-c10a245c916b:1:resolve"
               and e["predicate"] == "PRODUCES" and e["target"].endswith(":adventure-exiled")]
    assert resolve and len(resolve[0]["provenance"]) >= 2
    # genuine (non-self-exile) adventure effect-exiles are retained
    assert any(e["predicate"] == "MOVES_TO" and e["target"] == "zone:exile"
               and "f48f2a9b" in e["source"] and ":1:" in e["source"] for e in edges)


# --- v4 semantic-safety gate (review pt4) ------------------------------------
def test_condition_parser_lossless_or_unresolved():
    from hobkg.assemble import _parse_condition
    # negation must NOT become a positive assertion
    expr, st = _parse_condition("you do not have an enduring story")
    assert st == "structured" and expr == {"op": "not", "arg": {"op": "state_active", "state": "enduring_story"}}
    # a dropped conjunct (combat-damage requirement) => unresolved, not a bare mode
    _, st = _parse_condition("combat damage to a player, mode: second option chosen")
    assert st == "raw_unresolved"
    # specific variable-binding rule beats the general discard rule
    expr, st = _parse_condition("X = number of cards discarded this way")
    assert st == "structured" and expr["op"] == "eq" and expr["left"] == {"variable": "X"}
    # intended conversion that was previously missed
    expr, st = _parse_condition("third resolution this turn")
    assert st == "structured" and expr == {"op": "eq",
                                           "left": {"state": "ability_resolutions_this_turn"}, "right": 3}


def test_indirect_mana_has_no_false_direct_edge(stats, edges):
    assert stats["false_direct_mana_operations"] == 0
    assert stats["mana_faces_without_mana_path"] == 0
    # Long-Bodied Grey Dog produces mana only via a Treasure token — no direct op
    dog = "face:6f83da19-fd89-44ec-88f3-0c3fddfbd1b2:0"
    assert not any(e["source"] == f"op:{dog}:produce-mana" for e in edges)
    assert any(e["predicate"] == "CREATES_OBJECT" and e["target"] == "token:treasure"
               and dog.split(":")[1] in e["source"] for e in edges)
    assert any(e["source"].startswith("op:token:treasure") and e["target"].startswith("resource:mana")
               for e in edges)


def test_every_materialized_edge_has_provenance(stats, edges):
    assert stats["materialized_edges_without_provenance"] == 0
    assert all(e.get("provenance") for e in edges)
    # a materialized primitive edge cites its deterministic derivation
    ht = next(e for e in edges if e["predicate"] == "HAS_TYPE"
              and e["source"].startswith("face:") and e["target"].startswith("obj:type:"))
    assert any(p.get("derivation") == "phase4_materialization" for p in ht["provenance"])


# --- v4.1 closure (review pt5) -----------------------------------------------
def test_bilbo_mana_goes_to_opponent_not_controller(stats, edges):
    from hobkg import assemble
    from hobkg.pipeline import REPO
    bilbo = "face:ef71ef07-8a35-41ec-a851-d95e9e3a221b:0"
    # the Treasure Bilbo makes belongs to the opponent
    treasure = [e for e in edges if e["source"].startswith(f"op:{bilbo}")
                and e["predicate"] == "CREATES_OBJECT" and e["target"] == "token:treasure"]
    assert treasure and all(e.get("creates_for") == "opponent" for e in treasure)
    # Bilbo has no direct mana operation of its own
    assert not any(e["source"] == f"op:{bilbo}:produce-mana" for e in edges)
    # participant-aware reachability: opponent path only, never controller
    g = assemble.Graph()
    for e in edges:
        g.add_edge(e["source"], e["predicate"], e["target"], creates_for=e.get("creates_for"), scope=e.get("scope"))
    paths = assemble._face_mana_paths(g, bilbo)
    assert paths == {"opponent"}
    assert stats["opponent_only_mana_faces"] == 1


def test_shared_condition_keeps_all_provenance():
    conds = [json.loads(l) for l in (GLOBAL / "conditions.jsonl").read_text(encoding="utf-8").splitlines()]
    gift = [c for c in conds if c["human_readable"] == "gift promised"]
    assert len(gift) == 1 and len(gift[0]["provenance"]) >= 2   # both citations retained


def test_rebuild_is_byte_identical():
    import hashlib
    from hobkg import assemble
    files = ["nodes.jsonl", "edges.jsonl", "conditions.jsonl", "assembly_review.jsonl"]

    def digest():
        assemble.assemble()
        return {f: hashlib.sha256((GLOBAL / f).read_bytes()).hexdigest() for f in files}

    assert digest() == digest()
