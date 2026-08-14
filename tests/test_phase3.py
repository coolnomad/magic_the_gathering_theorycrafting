"""Phase 3 control-plane tests (no model calls)."""

import json

from hobkg import phase3
from hobkg.pipeline import REPO


def _valid(face_id="face:x:0"):
    return {
        "face_id": face_id,
        "abilities": [{
            "ability_id": "a1", "kind": "triggered", "trigger": {"event": "etb"},
            "costs": [], "conditions": [], "effects": [{"op": "draw", "quantity": 1}],
            "oracle_spans": [[0, 10]], "confidence": "high", "unresolved": [],
        }],
        "proposed_edges": [{
            "source": face_id, "target": "event:card-drawn", "predicate": "PRODUCES",
            "provenance": {"oracle_span": [0, 10]},
        }],
        "schema_extension_requests": [],
    }


def test_valid_extraction_passes():
    assert phase3.validate_output(_valid(), face_id="face:x:0", oracle_len=100) == []


def test_bad_predicate_rejected():
    o = _valid()
    o["proposed_edges"][0]["predicate"] = "SYNERGIZES_WITH"
    assert any("schema" in e for e in phase3.validate_output(o))


def test_missing_provenance_rejected():
    o = _valid()
    del o["proposed_edges"][0]["provenance"]
    assert phase3.validate_output(o)


def test_evaluative_language_rejected():
    o = _valid()
    o["abilities"][0]["effects"] = [{"note": "this creates great synergy with elves"}]
    assert any("evaluative" in e for e in phase3.validate_output(o))


def test_span_start_out_of_bounds_rejected():
    o = _valid()
    o["abilities"][0]["oracle_spans"] = [[150, 160]]  # start past end of text
    assert any("start invalid" in e for e in phase3.validate_output(o, face_id="face:x:0", oracle_len=100))


def test_span_end_overrun_is_warning_not_error():
    o = _valid()
    o["abilities"][0]["oracle_spans"] = [[0, 120]]  # end drifts past len — soft, not a reject
    assert phase3.validate_output(o, face_id="face:x:0", oracle_len=100) == []
    assert phase3.span_warnings(o, 100)


def test_descriptive_keys_allowed_on_ability_and_edge():
    o = _valid()
    o["abilities"][0]["controller"] = "you"
    o["abilities"][0]["duration"] = "until end of turn"
    o["proposed_edges"][0]["note"] = "self-reference resolved to this face"
    assert phase3.validate_output(o, face_id="face:x:0", oracle_len=100) == []


def test_face_id_mismatch_rejected():
    assert any("mismatch" in e for e in phase3.validate_output(_valid("face:x:0"), face_id="face:y:0"))


def test_build_tasks_covers_all_oracle_faces():
    stats = phase3.build_tasks()
    assert stats["faces_with_oracle_text"] == 209
    index = (REPO / "data/llm/tasks_index.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(index) == 209
    # a known face packet is self-contained and carries Oracle text + shared context exists
    first = json.loads(index[0])
    packet = json.loads((REPO / "data/llm/tasks" / first["file"]).read_text(encoding="utf-8"))
    assert packet["face"]["oracle_text"]
    assert (REPO / "data/llm/shared_context.json").exists()


def test_build_prompt_is_self_contained():
    phase3.build_tasks()
    idx = json.loads((REPO / "data/llm/tasks_index.jsonl").read_text(encoding="utf-8").splitlines()[0])
    prompt = phase3.build_prompt(idx["face_id"])
    assert "controlled_predicates" in prompt
    assert "Return a single JSON object" in prompt
    assert idx["face_id"] in prompt


def test_finalize_covers_all_210_faces():
    phase3.build_tasks()
    phase3.reconcile()
    phase3.finalize_faces()
    status = [json.loads(l) for l in (REPO / "data/review/llm_face_status.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(status) == 210
    empties = [s for s in status if s["status"] == "reviewed_empty"]
    assert len(empties) == 1 and empties[0]["card"] == "Ordinary Bear"
    assert empties[0].get("reason")
    # the reviewed_empty face must have an accepted record too
    acc = {json.loads(l)["face_id"] for l in (REPO / "data/review/llm_accepted.jsonl").read_text(encoding="utf-8").splitlines()}
    assert empties[0]["face_id"] in acc


def test_reconcile_accepts_agreement_and_queues_disputes(tmp_path):
    # minimal tmp repo layout
    (tmp_path / "data/review").mkdir(parents=True)
    (tmp_path / "data/llm/critiques").mkdir(parents=True)
    (tmp_path / "data/llm/tasks").mkdir(parents=True)
    face = "face:z:0"
    (tmp_path / "data/llm/tasks" / f"{phase3.safe_id(face)}.json").write_text(
        json.dumps({"face": {"oracle_text": "x" * 50}}), encoding="utf-8")
    cand = _valid(face)
    cand["proposed_edges"].append({"source": face, "target": "zone:graveyard",
                                   "predicate": "MOVES_TO", "provenance": {"oracle_span": [0, 5]}})
    (tmp_path / "data/review/llm_candidates.jsonl").write_text(json.dumps(cand) + "\n", encoding="utf-8")
    # critic agrees on the first edge, drops the second (dispute)
    crit = _valid(face)
    (tmp_path / "data/llm/critiques" / f"{phase3.safe_id(face)}.json").write_text(json.dumps(crit), encoding="utf-8")

    stats = phase3.reconcile(tmp_path)
    assert stats["accepted_faces"] == 1
    accepted = json.loads((tmp_path / "data/review/llm_accepted.jsonl").read_text(encoding="utf-8").strip())
    assert len(accepted["proposed_edges"]) == 1  # only the agreed edge
    queued = (tmp_path / "data/review/llm_queued.jsonl").read_text(encoding="utf-8").strip()
    assert "disagreement" in queued
