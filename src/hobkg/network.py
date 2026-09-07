"""Layer-3 set-wide network view over Card 002's port graph.

Not stored per-card the way ports are — this is a VIEW derived from
data/graph_global/card_ports.jsonl. It answers "which cards belong
together" via three complementary projections:

  * P_shared — symmetric IDF-weighted shared-concept overlap.
    "Both cards touch keyword:storied" is a stronger signal than
    "both are creatures" because storied is rarer.

  * P_flow — directional producer→consumer projection.
    Card A produces / references concept X (e.g. "Destroy target
    creature" points at obj:type:creature); card B IS_A that concept.
    Weight A→B measures how much A can act on B. Removal + creatures
    fall out of this projection.

  * P_gate — shared state-gate co-occurrence. Cards that both install
    or depend on gate:storied (or landfall/ferocious/threshold, or a
    shared event trigger) link with high weight. Archetype anchors
    live here.

Community detection (Louvain) runs on each projection independently;
converged clusters across all three are the strongest archetype claims.
"""

from __future__ import annotations

import json
import math
import pathlib
import statistics
from collections import Counter, defaultdict
from typing import Any

import networkx as nx
from networkx.algorithms.community import louvain_communities

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent

# ---------------------------------------------------------------------------
# Bipartite construction
# ---------------------------------------------------------------------------


def _edge_concepts(edge: dict[str, Any]) -> list[tuple[str, str]]:
    """Yield (concept_id, role) tuples for every concept the edge references.

    role is a coarse classification of what the edge does with that concept:
      * "IS_A"      -> the card IS this concept (from properties)
      * "PROPERTY"  -> a static property of the card (keyword, power, ...)
      * "TRIGGER"   -> the card consumes this event (TRIGGERS_ON)
      * "PRODUCE"   -> the card produces / acts on this concept
      * "COST"      -> the card pays this as a cost
      * "GATE"      -> the card installs or depends on a watcher/gate
    """
    out: list[tuple[str, str]] = []
    pred = edge.get("predicate")
    tgt = edge.get("target")
    cls = edge.get("class")

    def _push(c: object, role: str) -> None:
        if isinstance(c, str) and c and ":" in c:
            out.append((c, role))

    if pred == "IS_A":
        _push(tgt, "IS_A")
    elif pred == "HAS_KEYWORD":
        _push(tgt, "PROPERTY")
    elif pred in ("HAS_POWER", "HAS_TOUGHNESS"):
        # Numeric attrs don't participate in concept co-occurrence usefully.
        pass
    elif pred == "TRIGGERS_ON":
        _push(tgt, "TRIGGER")
    elif pred == "INSTALLS_WATCHER":
        _push(tgt, "GATE")
    elif pred == "REPLACES_ON":
        _push(tgt, "GATE")
    else:
        # Any producing / cost edge: lift target and class.
        role = "COST" if edge.get("purpose") in ("cast", "activation") else "PRODUCE"
        _push(tgt, role)
        _push(cls, role)
    return out


def build_bipartite(
    ports: list[dict[str, Any]],
    faces: dict[str, dict[str, Any]] | None = None,
) -> nx.Graph:
    """Card ↔ concept bipartite graph, edges tagged by role.

    When `faces` (face_id -> normalized face dict) is provided, adds
    color concepts (color:W, color:U, color:B, color:R, color:G,
    color:colorless) drawn from the face's mana_cost, and cmc:{0..7}
    concepts drawn from the face's converted mana cost. These give the
    projection color-pair and curve signal alongside the mechanical
    concepts from the port.
    """
    B = nx.Graph()
    for port in ports:
        fid = port["face_id"]
        B.add_node(fid, kind="card", name=port.get("name"))
        seen: set[tuple[str, str]] = set()
        for sec in ("properties", "installs", "consumes", "produces", "costs"):
            for e in port.get(sec, []):
                for concept, role in _edge_concepts(e):
                    key = (concept, role)
                    if key in seen:
                        continue
                    seen.add(key)
                    B.add_node(concept, kind="concept")
                    if not B.has_edge(fid, concept):
                        B.add_edge(fid, concept, roles=set())
                    B[fid][concept]["roles"].add(role)
        # Color + CMC concepts (from normalized face).
        if faces is not None:
            face = faces.get(fid)
            if face:
                _add_color_and_cmc(B, fid, face, seen)
    return B


def _add_color_and_cmc(
    B: nx.Graph,
    fid: str,
    face: dict[str, Any],
    seen: set[tuple[str, str]],
) -> None:
    mc = face.get("mana_cost") or {}
    syms = mc.get("symbols") if isinstance(mc, dict) else None
    colors_seen: set[str] = set()
    cmc = 0
    if isinstance(syms, list):
        for s in syms:
            if not isinstance(s, dict):
                continue
            for _c in (s.get("colors") or []):
                if isinstance(_c, str):
                    colors_seen.add(_c.upper())
            v = s.get("value")
            if isinstance(v, (int, float)):
                cmc += int(v)
            elif isinstance(v, str) and v.isdigit():
                cmc += int(v)
    if not colors_seen and isinstance(syms, list) and syms:
        colors_seen.add("C")  # colorless
    color_name = {"W": "white", "U": "blue", "B": "black",
                   "R": "red", "G": "green", "C": "colorless"}
    for c in colors_seen:
        concept = f"color:{color_name.get(c, c.lower())}"
        key = (concept, "PROPERTY")
        if key in seen:
            continue
        seen.add(key)
        B.add_node(concept, kind="concept")
        if not B.has_edge(fid, concept):
            B.add_edge(fid, concept, roles=set())
        B[fid][concept]["roles"].add("PROPERTY")
    # cmc bucket (only if there was a cost)
    if isinstance(syms, list) and syms:
        bucket = min(cmc, 7)
        concept = f"cmc:{bucket}"
        key = (concept, "PROPERTY")
        if key not in seen:
            seen.add(key)
            B.add_node(concept, kind="concept")
            if not B.has_edge(fid, concept):
                B.add_edge(fid, concept, roles=set())
            B[fid][concept]["roles"].add("PROPERTY")


# ---------------------------------------------------------------------------
# Projections
# ---------------------------------------------------------------------------


def _concept_idf(B: nx.Graph) -> dict[str, float]:
    """Inverse document-frequency weight per concept.

    A concept touched by half the set has weight ~0; a concept touched by
    3 cards has a large weight. Keeps common-type shared-concept blobs
    from dominating card-card projections.
    """
    card_nodes = [n for n, d in B.nodes(data=True) if d.get("kind") == "card"]
    n_cards = len(card_nodes)
    idf: dict[str, float] = {}
    for c, d in B.nodes(data=True):
        if d.get("kind") != "concept":
            continue
        df = sum(1 for _ in B.neighbors(c))
        if df >= n_cards:
            idf[c] = 0.0
        else:
            idf[c] = math.log((n_cards + 1) / (df + 1))
    return idf


def project_shared(B: nx.Graph, idf: dict[str, float]) -> nx.Graph:
    """Symmetric IDF-weighted shared-concept card-card graph."""
    P = nx.Graph()
    card_nodes = [n for n, d in B.nodes(data=True) if d.get("kind") == "card"]
    for c in card_nodes:
        P.add_node(c, **B.nodes[c])
    # Iterate concepts, add weight to every pair of cards touching it.
    for concept, d in B.nodes(data=True):
        if d.get("kind") != "concept":
            continue
        w = idf.get(concept, 0.0)
        if w <= 0:
            continue
        touchers = list(B.neighbors(concept))
        # only card-nodes are on the other side of a concept
        for i in range(len(touchers)):
            for j in range(i + 1, len(touchers)):
                a, b = touchers[i], touchers[j]
                if P.has_edge(a, b):
                    P[a][b]["weight"] += w
                else:
                    P.add_edge(a, b, weight=w)
    return P


def project_flow(B: nx.Graph, idf: dict[str, float]) -> nx.DiGraph:
    """Directional producer→consumer: card A points at concept X in a
    non-IS_A role; card B IS_A that concept. Draws an edge A→B weighted
    by IDF. Removal + creatures, sac-outlet + fodder, etc.
    """
    D = nx.DiGraph()
    card_nodes = [n for n, d in B.nodes(data=True) if d.get("kind") == "card"]
    for c in card_nodes:
        D.add_node(c, **B.nodes[c])
    for concept, d in B.nodes(data=True):
        if d.get("kind") != "concept":
            continue
        w = idf.get(concept, 0.0)
        if w <= 0:
            continue
        producers: list[str] = []
        consumers_isa: list[str] = []
        for card in B.neighbors(concept):
            roles = B[card][concept]["roles"]
            if "IS_A" in roles:
                consumers_isa.append(card)
            if roles - {"IS_A"}:
                producers.append(card)
        for a in producers:
            for b in consumers_isa:
                if a == b:
                    continue
                if D.has_edge(a, b):
                    D[a][b]["weight"] += w
                else:
                    D.add_edge(a, b, weight=w)
    return D


def project_gate(B: nx.Graph, idf: dict[str, float]) -> nx.Graph:
    """Shared gate / trigger / archetype-anchor projection.

    Restricts to concepts that carry archetype signal: gate:*, event:*,
    keyword:storied / landfall / ferocious / kicker / flashback, and any
    concept whose IDF is very high (rare co-occurrence).
    """
    ARCHETYPE_ANCHOR_PREFIXES = ("gate:", "event:")
    ARCHETYPE_ANCHOR_KEYWORDS = {
        "keyword:storied", "keyword:landfall", "keyword:ferocious",
        "keyword:threshold", "keyword:flashback", "keyword:kicker",
        "keyword:amass", "keyword:recruit", "keyword:beholds",
        "keyword:equip", "keyword:cycling", "keyword:enchant",
    }
    P = nx.Graph()
    card_nodes = [n for n, d in B.nodes(data=True) if d.get("kind") == "card"]
    for c in card_nodes:
        P.add_node(c, **B.nodes[c])
    for concept, d in B.nodes(data=True):
        if d.get("kind") != "concept":
            continue
        is_anchor = (
            any(concept.startswith(p) for p in ARCHETYPE_ANCHOR_PREFIXES)
            or concept in ARCHETYPE_ANCHOR_KEYWORDS
        )
        if not is_anchor:
            continue
        w = idf.get(concept, 0.0)
        if w <= 0:
            continue
        touchers = list(B.neighbors(concept))
        for i in range(len(touchers)):
            for j in range(i + 1, len(touchers)):
                a, b = touchers[i], touchers[j]
                if P.has_edge(a, b):
                    P[a][b]["weight"] += w
                else:
                    P.add_edge(a, b, weight=w)
    return P


# ---------------------------------------------------------------------------
# Community detection + labeling
# ---------------------------------------------------------------------------


def detect_communities(
    G: nx.Graph | nx.DiGraph,
    seed: int = 42,
    resolution: float = 1.0,
) -> list[set[str]]:
    """Louvain on an undirected view (converts DiGraph if needed)."""
    if G.is_directed():
        UG = G.to_undirected(as_view=False)
        # Sum weights of A→B and B→A into a single weight
        for u, v in UG.edges():
            wu = G[u][v]["weight"] if G.has_edge(u, v) else 0.0
            wv = G[v][u]["weight"] if G.has_edge(v, u) else 0.0
            UG[u][v]["weight"] = wu + wv
    else:
        UG = G
    return list(louvain_communities(UG, weight="weight", seed=seed, resolution=resolution))


def label_communities(
    communities: list[set[str]],
    B: nx.Graph,
    idf: dict[str, float],
    top_k: int = 6,
) -> list[dict[str, Any]]:
    """For each community, name its most-central concepts."""
    result = []
    for i, comm in enumerate(communities):
        # Sum IDF-weighted incidence within community.
        cscore: dict[str, float] = defaultdict(float)
        for card in comm:
            for concept in B.neighbors(card):
                if B.nodes[concept].get("kind") != "concept":
                    continue
                cscore[concept] += idf.get(concept, 0.0)
        top = sorted(cscore.items(), key=lambda x: -x[1])[:top_k]
        card_names = sorted(
            (B.nodes[c].get("name") or c) for c in comm
        )
        result.append({
            "cluster_id": i,
            "size": len(comm),
            "top_concepts": [{"concept": c, "score": round(s, 2)} for c, s in top],
            "cards": card_names,
            "face_ids": sorted(comm),
        })
    return sorted(result, key=lambda x: -x["size"])


# ---------------------------------------------------------------------------
# End-to-end
# ---------------------------------------------------------------------------


def _is_creature_port(port: dict[str, Any]) -> bool:
    return any(
        e.get("predicate") == "IS_A" and e.get("target") == "obj:type:creature"
        for e in port.get("properties", [])
    )


def _is_spell_port(port: dict[str, Any]) -> bool:
    """Non-creature, non-land: instant / sorcery / enchantment / artifact.

    Equipment is an artifact subtype, so equipment is included.
    """
    types = {
        e.get("target") for e in port.get("properties", [])
        if e.get("predicate") == "IS_A"
    }
    if "obj:type:land" in types or "obj:type:creature" in types:
        return False
    return bool(types & {
        "obj:type:instant",
        "obj:type:sorcery",
        "obj:type:enchantment",
        "obj:type:artifact",
    })


# ---------------------------------------------------------------------------
# Enabler <-> payoff projection
# ---------------------------------------------------------------------------
#
# The bipartite / IDF projections group cards by shared vocabulary.  This
# projection groups them by a functional relationship: which cards *fire*
# an event, and which cards *care* that the event fired.  Each card can be
# both (a card that draws and cares about the second draw is on both sides
# of the draw loop), so the resulting graph is directed enabler -> payoff
# and we symmetrise for community detection.
#
# Each category is (payoff_events_set, enabler_predicate_set, extra_filter)
# where extra_filter runs on the port (used to include cards that ARE the
# thing being triggered on, e.g. every artifact for artifact-enters).

# Predicates in `produces` that put a card in your hand (fires draw triggers).
_DRAW_ENABLER_PREDS = {"DRAWS", "RECRUIT", "TUTORS"}
# Predicates that put a land onto the battlefield without playing your normal
# land drop (fires landfall).  A vanilla land is *not* an enabler here; the
# landfall archetype is powered by extra land drops.
_LANDFALL_ENABLER_PREDS = {"PLAYS_LAND"}
# Predicates that generate creatures/tokens that can be sacrificed later.
_TOKEN_ENABLER_PREDS = {"CREATES_TOKEN", "AMASS", "RECRUIT"}


def _has_type(port: dict[str, Any], type_target: str) -> bool:
    return any(
        e.get("predicate") == "IS_A" and e.get("target") == type_target
        for e in port.get("properties", [])
    )


def _has_subtype(port: dict[str, Any], sub_target: str) -> bool:
    return any(
        e.get("predicate") == "IS_A" and e.get("target") == sub_target
        for e in port.get("properties", [])
    )


def _payoff_events(port: dict[str, Any]) -> set[str]:
    """Categories this card cares about (TRIGGERS_ON targets, bucketed).

    Self-scope triggers (this-creature-enters, saga-chapter, this-creature-
    attacks, ...) are excluded because they don't depend on other cards.
    """
    cats: set[str] = set()
    for e in port.get("consumes", []):
        if e.get("predicate") != "TRIGGERS_ON":
            continue
        t = e.get("target") or ""
        if t in ("event:you-draw-second-card", "event:you-draw-card",
                 "event:player-draws-card"):
            cats.add("draw")
        elif t == "event:land-enters-under-your-control":
            cats.add("landfall")
        elif t == "event:you-cast-noncreature-spell":
            cats.add("cast-noncreature")
        elif t == "event:artifact-enters-under-your-control":
            cats.add("artifact-enters")
        elif t == "event:another-dwarf-or-equipment-enters":
            cats.add("dwarf-or-equipment-enters")
        elif t == "event:you-sacrifice-token":
            cats.add("sac-token")
    return cats


def _enabler_events(port: dict[str, Any]) -> set[str]:
    """Categories this card *fires* when it resolves / is on the battlefield.

    Deliberately narrow: only produce-predicates that map to a payoff event
    someone else in the set is asking for.  Population-wide identities (every
    creature "enables" creature-death) are excluded because they blur the
    archetypes rather than reveal them.
    """
    cats: set[str] = set()
    prod_preds = {e.get("predicate") for e in port.get("produces", [])}
    if prod_preds & _DRAW_ENABLER_PREDS:
        cats.add("draw")
    if prod_preds & _LANDFALL_ENABLER_PREDS:
        cats.add("landfall")
    # Every land card enables landfall by being played.
    if _has_type(port, "obj:type:land"):
        cats.add("landfall")
    if prod_preds & _TOKEN_ENABLER_PREDS:
        cats.add("sac-token")
    # Casting an instant / sorcery / adventure fires cast-noncreature payoffs.
    # (Casting an artifact or enchantment also technically does, but the
    # tempo profile of the payoff is aimed at nonpermanent spells; narrowing
    # here keeps the archetype tight.)
    types = {
        e.get("target") for e in port.get("properties", [])
        if e.get("predicate") == "IS_A"
    }
    if types & {"obj:type:instant", "obj:type:sorcery"}:
        cats.add("cast-noncreature")
    if "obj:type:artifact" in types:
        cats.add("artifact-enters")
    if _has_subtype(port, "obj:subtype:dwarf") or _has_subtype(port, "obj:subtype:equipment"):
        cats.add("dwarf-or-equipment-enters")
    return cats


def project_enabler_payoff(
    ports: list[dict[str, Any]],
    faces: dict[str, dict] | None = None,
) -> nx.Graph:
    """Undirected weighted graph over cards that participate in the enabler
    <-> payoff economy.  An edge exists whenever card A enables a category
    B cares about (or vice versa); its weight is the sum of category IDF
    weights across both directions, so a rare / archetype-defining loop
    (e.g. dwarf-or-equipment-enters, only 2 payoffs) contributes more than
    a common one (e.g. cast-noncreature).
    """
    faces = faces or {}
    payoffs = {p["face_id"]: _payoff_events(p) for p in ports}
    enablers = {p["face_id"]: _enabler_events(p) for p in ports}
    active = {fid for fid, ev in enablers.items() if ev} | \
             {fid for fid, ev in payoffs.items() if ev}
    # IDF over enabler+payoff population per category: rarer categories
    # (few enablers or few payoffs) get more weight per shared edge.
    n_total = max(1, len(active))
    cat_counts: dict[str, int] = {}
    for fid in active:
        for c in enablers.get(fid, set()) | payoffs.get(fid, set()):
            cat_counts[c] = cat_counts.get(c, 0) + 1
    import math as _math
    idf = {c: _math.log((n_total + 1) / (n + 1)) + 1.0 for c, n in cat_counts.items()}
    G: nx.Graph = nx.Graph()
    for fid in active:
        f = faces.get(fid, {}) if faces else {}
        G.add_node(
            fid,
            kind="card",
            name=f.get("name") or fid,
            enables=sorted(enablers.get(fid, set())),
            pays_off=sorted(payoffs.get(fid, set())),
        )
    active_list = list(active)
    SAME_SIDE_WEIGHT = 0.5  # payoff<->payoff and enabler<->enabler get half
    for i, a in enumerate(active_list):
        for b in active_list[i + 1:]:
            shared_ep = (enablers[a] & payoffs[b]) | (enablers[b] & payoffs[a])
            shared_pp = payoffs[a] & payoffs[b]
            shared_ee = enablers[a] & enablers[b]
            union_cats = shared_ep | shared_pp | shared_ee
            if not union_cats:
                continue
            w = 0.0
            for c in shared_ep:
                w += idf[c]
            for c in shared_pp:
                w += idf[c] * SAME_SIDE_WEIGHT
            for c in shared_ee:
                w += idf[c] * SAME_SIDE_WEIGHT
            G.add_edge(
                a, b, weight=w, categories=sorted(union_cats)
            )
    return G


def _label_enabler_payoff_communities(
    communities: list[list[str]],
    G: nx.Graph,
) -> list[dict[str, Any]]:
    """Label each community by the most common shared enabler-payoff
    categories, plus counts of enabler / payoff / dual cards."""
    out: list[dict[str, Any]] = []
    for cid, members in enumerate(sorted(communities, key=len, reverse=True)):
        cat_counter: dict[str, int] = {}
        payoff_ct = enabler_ct = both_ct = 0
        for fid in members:
            data = G.nodes[fid]
            enables_set = set(data.get("enables") or ())
            pays_set = set(data.get("pays_off") or ())
            if enables_set and pays_set:
                both_ct += 1
            elif enables_set:
                enabler_ct += 1
            elif pays_set:
                payoff_ct += 1
            for c in enables_set | pays_set:
                cat_counter[c] = cat_counter.get(c, 0) + 1
        top_cats = sorted(cat_counter.items(), key=lambda kv: -kv[1])
        out.append({
            "cluster_id": cid,
            "size": len(members),
            "face_ids": list(members),
            "cards": [G.nodes[fid].get("name") or fid for fid in members],
            "top_concepts": [
                {"concept": f"event:{c}", "score": float(n)} for c, n in top_cats[:6]
            ],
            "enabler_count": enabler_ct,
            "payoff_count": payoff_ct,
            "dual_count": both_ct,
        })
    return out


def build_and_cluster(
    ports_path: pathlib.Path = ROOT / "data" / "graph_global" / "card_ports.jsonl",
    faces_path: pathlib.Path = ROOT / "data" / "normalized" / "faces.jsonl",
    seed: int = 42,
    resolution: float = 1.0,
) -> dict[str, Any]:
    ports = [json.loads(l) for l in ports_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    faces = {}
    if faces_path.exists():
        for line in faces_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                d = json.loads(line)
                faces[d["id"]] = d
    B = build_bipartite(ports, faces=faces)
    idf = _concept_idf(B)
    # Creatures-only projection: rebuild bipartite from just creature ports
    # so IDF is calibrated to that population and the projection is
    # dominated by creature-relevant concepts (subtype/keyword) rather
    # than nonpermanent-vs-permanent structure.
    creature_ports = [p for p in ports if _is_creature_port(p)]
    B_creatures = build_bipartite(creature_ports, faces=faces)
    idf_creatures = _concept_idf(B_creatures)
    # Spells-only projection: non-creature, non-land cards (instants,
    # sorceries, enchantments, artifacts / equipment). IDF re-fit on this
    # population so the projection is dominated by interaction / support
    # patterns instead of subtype/tribal signal.
    spell_ports = [p for p in ports if _is_spell_port(p)]
    B_spells = build_bipartite(spell_ports, faces=faces)
    # Drop the big type-line buckets that would otherwise dominate the
    # spells projection (nearly every non-creature card is one of these);
    # keep the subtype concepts (saga, adventure, equipment, aura, …) that
    # actually differentiate spells.
    _type_bucket_drop = {
        "obj:type:instant",
        "obj:type:sorcery",
        "obj:type:enchantment",
        "obj:type:artifact",
        "obj:type:permanent",
        "obj:type:nonpermanent",
    }
    for n in list(B_spells.nodes):
        if n in _type_bucket_drop:
            B_spells.remove_node(n)
    idf_spells = _concept_idf(B_spells)
    G_ep = project_enabler_payoff(ports, faces=faces)
    projs = {
        "shared": project_shared(B, idf),
        "flow": project_flow(B, idf),
        "gate": project_gate(B, idf),
        "creatures": project_shared(B_creatures, idf_creatures),
        "spells": project_shared(B_spells, idf_spells),
        "enablers": G_ep,
    }
    result: dict[str, Any] = {
        "n_cards": sum(1 for _, d in B.nodes(data=True) if d.get("kind") == "card"),
        "n_concepts": sum(1 for _, d in B.nodes(data=True) if d.get("kind") == "concept"),
        "projections": {},
    }
    _label_bipartite = {
        "shared": (B, idf),
        "flow": (B, idf),
        "gate": (B, idf),
        "creatures": (B_creatures, idf_creatures),
        "spells": (B_spells, idf_spells),
    }
    for name, G in projs.items():
        comms = detect_communities(G, seed=seed, resolution=resolution)
        if name == "enablers":
            labeled = _label_enabler_payoff_communities(comms, G_ep)
        else:
            _lb, _lidf = _label_bipartite[name]
            labeled = label_communities(comms, _lb, _lidf)
        result["projections"][name] = {
            "n_edges": G.number_of_edges(),
            "n_communities": len(comms),
            "size_stats": {
                "min": min((len(c) for c in comms), default=0),
                "max": max((len(c) for c in comms), default=0),
                "median": int(statistics.median([len(c) for c in comms])) if comms else 0,
            },
            "communities": labeled,
        }
    return result


def write_communities(
    result: dict[str, Any],
    out_path: pathlib.Path = ROOT / "data" / "graph_global" / "card_communities.jsonl",
) -> None:
    """One row per face per projection, with its cluster and neighbors."""
    rows = []
    for proj_name, pdata in result["projections"].items():
        for comm in pdata["communities"]:
            for face_id, name in zip(comm["face_ids"], comm["cards"]):
                rows.append({
                    "face_id": face_id,
                    "name": name,
                    "projection": proj_name,
                    "cluster_id": comm["cluster_id"],
                    "cluster_size": comm["size"],
                    "top_concepts": comm["top_concepts"][:3],
                })
    with out_path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def main(argv: list[str] | None = None) -> int:
    result = build_and_cluster()
    write_communities(result)
    print(f"Bipartite: {result['n_cards']} cards, {result['n_concepts']} concepts")
    for pname, pdata in result["projections"].items():
        print(f"  {pname:8s} {pdata['n_edges']:5d} edges, "
              f"{pdata['n_communities']:3d} communities "
              f"(sizes {pdata['size_stats']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
