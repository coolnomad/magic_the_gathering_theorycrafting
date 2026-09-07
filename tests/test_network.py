"""Tests for layer-3 set-wide network view."""

from __future__ import annotations

import json
import pathlib

import pytest

from hobkg import network

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def result():
    return network.build_and_cluster(seed=42)


def test_all_faces_appear_as_cards(result):
    """Every face in card_ports.jsonl must be a card node in the bipartite."""
    assert result["n_cards"] == 210


def test_concept_count_reasonable(result):
    """Concept count should be in a sane range for HOB (types, subtypes,
    events, keywords, gates, colors, cmc buckets)."""
    n = result["n_concepts"]
    assert 100 <= n <= 300, f"unexpected concept count: {n}"


def test_shared_projection_produces_manageable_communities(result):
    """The shared projection should yield a small number of large,
    meaningful clusters -- not 210 singletons and not 1 giant."""
    pdata = result["projections"]["shared"]
    n = pdata["n_communities"]
    assert 4 <= n <= 15, f"expected 4-15 clusters, got {n}"
    assert pdata["size_stats"]["max"] < 100, "one cluster contains almost the whole set"
    assert pdata["size_stats"]["min"] >= 3, "trivial singleton clusters"


def test_storied_archetype_clusters_together(result):
    """The Storied cards (Balin, Bifur, Bombur, Dain, Fili, Kili, Oin,
    Ori, Thorin) should end up in the same shared-projection cluster
    -- storied is a well-defined mechanical archetype."""
    STORIED_NAMES = {
        "Balin, Loremaster", "Bifur, Melodic Rider", "Bombur, Gentle Dreamer",
        "Dáin, Lord of the Iron Hills", "Fíli the Pathfinder",
        "Kíli the Resourceful", "Óin the Brave",
        "Ori, Keeper of Songs", "Thorin Oakenshield",
    }
    for c in result["projections"]["shared"]["communities"]:
        cards_in = STORIED_NAMES & set(c["cards"])
        if cards_in:
            # If any storied card is in this cluster, most of them should be.
            assert len(cards_in) >= 7, (
                f"Storied cards split across clusters; found only "
                f"{cards_in} in cluster {c['cluster_id']}"
            )
            return
    assert False, "no cluster contained any Storied card"


def test_equipment_cluster_forms(result):
    """Equipment cards (Dwarven Mattock, Dwarven Shortsword, Glamdring,
    Sting, Wizard's Staff, etc.) should form a coherent cluster."""
    EQUIP_SAMPLES = {
        "Dwarven Mattock", "Dwarven Shortsword", "Glamdring, Foe-hammer",
        "Sting, Bilbo's Sword", "Crude Bent Blade",
    }
    for c in result["projections"]["shared"]["communities"]:
        cards_in = EQUIP_SAMPLES & set(c["cards"])
        if len(cards_in) >= 3:
            # Cluster should be equipment-labeled
            concepts = {tc["concept"] for tc in c["top_concepts"]}
            assert any("equipment" in cp or "equip" in cp for cp in concepts), (
                f"cluster with equipment cards missing equipment concept: {concepts}"
            )
            return
    assert False, "no cluster contained multiple equipment cards"


def test_bipartite_edges_tagged_with_roles():
    """Every bipartite edge should carry a `roles` set."""
    ports = [json.loads(l) for l in (ROOT / "data" / "graph_global" / "card_ports.jsonl").read_text(
        encoding="utf-8").splitlines() if l.strip()]
    faces = {json.loads(l)["id"]: json.loads(l) for l in (ROOT / "data" / "normalized" / "faces.jsonl").read_text(
        encoding="utf-8").splitlines() if l.strip()}
    B = network.build_bipartite(ports, faces=faces)
    for u, v, d in B.edges(data=True):
        assert "roles" in d
        assert isinstance(d["roles"], set)
        assert d["roles"]


def test_communities_file_written(tmp_path):
    """write_communities produces one row per (face, projection)."""
    r = network.build_and_cluster(seed=42)
    out = tmp_path / "card_communities.jsonl"
    network.write_communities(r, out_path=out)
    rows = [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines() if l.strip()]
    # Every face * every projection should have a row
    per_proj = {p: 0 for p in r["projections"]}
    for row in rows:
        per_proj[row["projection"]] += 1
    # Each projection may be a subset (e.g. creatures-only); check against
    # the projection's own community coverage rather than the global n_cards.
    expected = {
        p: sum(len(c["face_ids"]) for c in pdata["communities"])
        for p, pdata in r["projections"].items()
    }
    for p, n in per_proj.items():
        assert n == expected[p], (
            f"projection {p} has {n} rows, expected {expected[p]}"
        )
    # And the full-set projections should cover every card.
    for p in ("shared", "flow", "gate"):
        assert per_proj[p] == r["n_cards"], (
            f"full-set projection {p} has {per_proj[p]} rows, expected {r['n_cards']}"
        )
