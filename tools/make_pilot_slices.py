"""Build the small, prompt-sized input slices for the task 001 layer-2 pilot.

Compact inlines every declared Input into the executor prompt. The full graph
and the comprehensive rules are ~1.0M tokens together, which exceeds the model's
context on its own. This script cuts each source down to the eleven pilot faces
so the card can declare real Inputs that fit.

Deterministic: sorted keys, sorted rows, LF endings. Two runs agree byte for byte.

    python tools/make_pilot_slices.py
"""

from __future__ import annotations

import collections
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
GG = ROOT / "data" / "graph_global"
OUT = ROOT / "data" / "pilot"

PILOT_FACES: tuple[str, ...] = (
    "face:89a2fab8-b074-42aa-a871-d9c5de2d0895:0",  # Ordinary Bear
    "face:961e3023-39ea-4141-99b6-738280a2815d:0",  # Pinecone Strike
    "face:b8d563e4-e2bc-4e8b-8841-6655beff9138:0",  # Bifur, Melodic Rider
    "face:20535126-f811-4386-bdce-d73f30691724:0",  # Smaug, Wicked Worm
    "face:dda607bd-f419-4b7f-b052-a5ce6ce22bfe:0",  # Stir Up Trouble
    "face:3f4d6f91-95ad-4687-8899-5a21a0abb49e:0",  # Elrond, Moon-Reader
    "face:8a0e35ac-6c03-4922-b3b4-e419419fe3d7:0",  # Bofur, Reliable Guardian
    "face:8a0e35ac-6c03-4922-b3b4-e419419fe3d7:1",  # Concerted Care (adventure)
    "face:32ad5b3e-92c0-45be-b2e4-6f1794552f36:0",  # The Mountain-king's Return
    "face:30c3c700-46f4-4a77-8c45-5c7e3a21bd62:0",  # Wizard's Staff
    "face:008a11c1-d283-49fe-abd7-ff4fe8b1fe79:0",  # Rhovanion Rampager
)

UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
FACE_RE = re.compile(r"face:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}:\d+")
PLUMBING = frozenset(
    {"HAS_ABILITY", "HAS_FACE", "HAS_COST", "CAN_LEAD_TO", "CAN_UNDERGO",
     "REFERENCES_RULE", "HAS_ALTERNATIVE"}
)
PROPERTY_PREDICATES = frozenset({"HAS_TYPE", "HAS_KEYWORD", "HAS_STATE", "HAS_COUNTER_TYPE"})


def read(path: pathlib.Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write(path: pathlib.Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"{path.stat().st_size:>9,} B  {len(rows):>4} rows  {path.relative_to(ROOT)}")


def owner(node_id: object) -> str | None:
    match = UUID_RE.search(str(node_id or ""))
    return match.group(0) if match else None


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    wanted = set(PILOT_FACES)
    card_uuids = {UUID_RE.search(f).group(0) for f in PILOT_FACES}  # type: ignore[union-attr]

    faces = [r for r in read(ROOT / "data/normalized/faces.jsonl") if r["id"] in wanted]
    missing = wanted - {r["id"] for r in faces}
    if missing:
        raise SystemExit(f"pilot faces absent from faces.jsonl: {sorted(missing)}")
    write(OUT / "faces.jsonl", sorted(faces, key=lambda r: r["id"]))

    accepted = [r for r in read(ROOT / "data/review/llm_accepted.jsonl") if r["face_id"] in wanted]
    write(OUT / "llm_accepted.jsonl", sorted(accepted, key=lambda r: r["face_id"]))

    census = [r for r in read(GG / "effect_census.jsonl") if r["face_id"] in wanted]
    write(OUT / "effect_census.jsonl", sorted(census, key=lambda r: r["clause_id"]))

    # Vocabulary seed: every shared concept, its kind, and how many cards touch it.
    edges: list[dict] = []
    for path in sorted(GG.glob("*edges*.jsonl")):
        edges.extend(read(path))
    node_kind = {r["id"]: r.get("type") for r in read(GG / "nodes.jsonl")}
    for path in sorted(GG.glob("*_nodes.jsonl")):
        node_kind.update({r["id"]: r.get("type") for r in read(path)})

    touched: dict[str, set[str]] = collections.defaultdict(set)
    for edge in edges:
        if edge["predicate"] in PLUMBING:
            continue
        source, target = owner(edge.get("source")), owner(edge.get("target"))
        if source and not target:
            touched[edge["target"]].add(source)
        elif target and not source:
            touched[edge["source"]].add(target)
    seed = [
        {
            "concept_id": concept,
            "kind": node_kind.get(concept),
            "cards": len(cards),
            "hub": len(cards) > 1,
        }
        for concept, cards in touched.items()
    ]
    write(OUT / "vocabulary_seed.jsonl", sorted(seed, key=lambda r: (-r["cards"], r["concept_id"])))

    # Control: the frozen graph's view of the pilot faces, and which abilities are dead.
    outgoing = collections.Counter(e["source"] for e in edges)
    control = []
    for row in read(GG / "nodes.jsonl"):
        if owner(row["id"]) not in card_uuids:
            continue
        if not str(row["id"]).startswith("ability:"):
            continue
        match = FACE_RE.search(row["id"])
        if match is None or match.group(0) not in wanted:
            continue
        control.append(
            {
                "ability_id": row["id"],
                "face_id": match.group(0),
                "outgoing_edges": outgoing.get(row["id"], 0),
                "dead_in_frozen_graph": outgoing.get(row["id"], 0) == 0,
            }
        )
    write(OUT / "frozen_control.jsonl", sorted(control, key=lambda r: r["ability_id"]))
    dead = sum(1 for r in control if r["dead_in_frozen_graph"])
    print(f"\n  {len(control)} abilities across {len(faces)} faces; {dead} dead in the frozen graph")


if __name__ == "__main__":
    main()
