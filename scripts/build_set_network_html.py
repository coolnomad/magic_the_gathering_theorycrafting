"""Build reports/set_network.html from the current port graph.

Regenerates the DATA blob (community lists + thresholded graph edges)
for every projection returned by ``network.build_and_cluster``. The
HTML/CSS/JS scaffold is written inline here so the whole dashboard is
reproducible from this one script.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

from src.hobkg import network

ROOT = pathlib.Path(__file__).resolve().parents[1]
FACES_PATH = ROOT / "data" / "normalized" / "faces.jsonl"
OUT_PATH = ROOT / "reports" / "set_network.html"

TABS: list[tuple[str, str]] = [
    ("shared", "Shared concepts"),
    ("flow", "Producer -> consumer flow"),
    ("creatures", "Creatures only"),
    ("spells", "Spells only"),
    ("enablers", "Enablers <-> payoffs"),
]

GRAPH_TOP_K_PER_NODE = 6


def _face_meta(face_id, faces):
    f = faces.get(face_id, {})
    return {
        "id": face_id,
        "name": f.get("name") or face_id,
        "type_line": f.get("type_line_raw") or "",
        "mana_cost": f.get("mana_cost_raw") or "",
    }


def _list_blob(pdata, faces):
    out = {"n_edges": pdata["n_edges"], "communities": []}
    for c in pdata["communities"]:
        out["communities"].append({
            "cluster_id": c["cluster_id"],
            "size": c["size"],
            "top_concepts": c["top_concepts"][:6],
            "cards": [_face_meta(fid, faces) for fid in c["face_ids"]],
        })
    return out


def _graph_blob(G, cluster_of, faces):
    # Keep top-K by weight per node.  Directed graphs use out-edges only;
    # undirected sees each edge once per endpoint.  We dedup so the same
    # pair isn't rendered twice.
    kept = {}  # (u,v) -> weight
    for n in G.nodes:
        # For directed graphs G[n] iterates successors; for undirected, neighbors.
        neighbors = sorted(
            G[n].items(), key=lambda kv: -kv[1].get("weight", 0.0)
        )[:GRAPH_TOP_K_PER_NODE]
        for m, d in neighbors:
            key = (n, m) if G.is_directed() else tuple(sorted((n, m)))
            w = float(d.get("weight", 0.0))
            if key not in kept or w > kept[key]:
                kept[key] = w
    nodes = []
    for n in G.nodes:
        f = faces.get(n, {})
        nodes.append({
            "id": n,
            "name": f.get("name") or n,
            "type_line": f.get("type_line_raw") or "",
            "cluster": cluster_of.get(n, -1),
        })
    edges = [
        {"from": u, "to": v, "weight": round(w, 2)}
        for (u, v), w in kept.items()
    ]
    return {"nodes": nodes, "edges": edges}


def build_data(faces):
    r = network.build_and_cluster(seed=42)
    data = {
        "n_cards": r["n_cards"],
        "n_concepts": r["n_concepts"],
        "lists": {},
        "graphs": {},
    }
    from src.hobkg.network import (
        build_bipartite, _concept_idf, project_shared, project_flow,
        project_enabler_payoff, _is_creature_port, _is_spell_port,
    )
    ports = [
        json.loads(l) for l in
        (ROOT / "data" / "graph_global" / "card_ports.jsonl")
        .read_text(encoding="utf-8").splitlines()
        if l.strip()
    ]
    B_all = build_bipartite(ports, faces=faces)
    idf_all = _concept_idf(B_all)
    creature_ports = [p for p in ports if _is_creature_port(p)]
    B_cre = build_bipartite(creature_ports, faces=faces)
    idf_cre = _concept_idf(B_cre)
    spell_ports = [p for p in ports if _is_spell_port(p)]
    B_spe = build_bipartite(spell_ports, faces=faces)
    _drop = {
        "obj:type:instant", "obj:type:sorcery", "obj:type:enchantment",
        "obj:type:artifact", "obj:type:permanent", "obj:type:nonpermanent",
    }
    for n in list(B_spe.nodes):
        if n in _drop:
            B_spe.remove_node(n)
    idf_spe = _concept_idf(B_spe)

    proj_graphs = {
        "shared":    project_shared(B_all, idf_all),
        "flow":      project_flow(B_all, idf_all),
        "creatures": project_shared(B_cre, idf_cre),
        "spells":    project_shared(B_spe, idf_spe),
        "enablers":  project_enabler_payoff(ports, faces=faces),
    }

    for name, _label in TABS:
        pdata = r["projections"][name]
        cluster_of = {}
        for c in pdata["communities"]:
            for fid in c["face_ids"]:
                cluster_of[fid] = c["cluster_id"]
        data["lists"][name] = _list_blob(pdata, faces)
        data["graphs"][name] = _graph_blob(proj_graphs[name], cluster_of, faces)
    return data


HTML_TMPL = r"""<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>HOB Set Network - Graph View</title>
<style>
:root { --bg:#f7f5ee; --ink:#1a1a1a; --muted:#6b6b6b; --line:#d9d3c1; --accent:#6a3f00; }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--ink); font:14px/1.4 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
header { padding:14px 20px; background:#fff; border-bottom:1px solid var(--line); }
header h1 { margin:0; font-size:18px; }
header .sub { color:var(--muted); font-size:12px; margin-top:2px; }
.tabs { display:flex; gap:0; background:#fff; padding:0 20px; border-bottom:1px solid var(--line); flex-wrap:wrap; }
.tabs button { background:none; border:none; padding:10px 16px; cursor:pointer; font-size:13px; color:var(--muted); border-bottom:2px solid transparent; }
.tabs button.active { color:var(--accent); border-bottom-color:var(--accent); font-weight:600; }
.tabs .sep { flex:1; }
.metrics { padding:8px 20px; background:#fff; border-bottom:1px solid var(--line); font-size:12px; color:var(--muted); }
.legend { padding:8px 20px; background:#fff; border-bottom:1px solid var(--line); display:flex; flex-wrap:wrap; gap:6px; }
.chip { padding:3px 8px; border-radius:12px; font-size:11px; }
main { padding:0; }
.cluster { padding:16px 20px; border-bottom:1px solid var(--line); }
.cluster h2 { margin:0 0 4px 0; font-size:14px; display:flex; align-items:center; gap:8px; }
.cluster h2 .swatch { width:12px; height:12px; border-radius:2px; }
.cluster .concepts { font-family:"SF Mono",Menlo,monospace; font-size:11px; color:var(--muted); margin-bottom:8px; }
.cluster .cards { display:grid; grid-template-columns:repeat(auto-fill,minmax(230px,1fr)); gap:6px; }
.card { background:#fff; border:1px solid var(--line); border-radius:3px; padding:6px 8px; font-size:12px; }
.card .name { font-weight:600; }
.card .type { color:var(--muted); font-size:10px; }
.card .mana { color:var(--accent); font-family:"SF Mono",Menlo,monospace; font-size:10px; float:right; }
#graph-container { position:relative; width:100%; height:calc(100vh - 175px); background:#fafaf5; }
#graph-svg { width:100%; height:100%; }
#graph-tooltip { position:absolute; background:#fff; border:1px solid var(--line); padding:6px 10px; border-radius:4px; font-size:12px; pointer-events:none; display:none; box-shadow:0 2px 6px rgba(0,0,0,0.1); z-index:10; }
.g-node { cursor:pointer; }
.g-node:hover { stroke:#000; stroke-width:2px; }
.g-edge { stroke:#999; stroke-opacity:0.25; }
</style>
</head><body>
<header>
  <h1>HOB Set Network - Card Communities</h1>
  <div class="sub">Force-directed graph of cards, colored by Louvain cluster over the port graph. Hover for card info; switch projections.</div>
</header>
<div class="tabs">
__TAB_BUTTONS__
  <span class="sep"></span>
  <button data-view="graph" class="active">Graph</button>
  <button data-view="list">List</button>
</div>
<div class="metrics" id="metrics"></div>
<div class="legend" id="legend"></div>
<div id="graph-container">
  <svg id="graph-svg" xmlns="http://www.w3.org/2000/svg"></svg>
  <div id="graph-tooltip"></div>
</div>
<main id="main" style="display:none"></main>
<script>
const DATA = __DATA__;
const PALETTE = ['#1b4d8b','#8b1b1b','#4d8b1b','#8b6b1b','#5c1b8b','#1b8b8b','#8b1b6b','#4b4b4b','#7d5a3a','#3a7d5a','#5a3a7d','#7d3a5a'];

let currentProj = 'shared';
let currentView = 'graph';

function esc(s) { return (s || '').toString().replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
function color(cid) { return PALETTE[cid % PALETTE.length]; }

function renderMetrics() {
  const p = DATA.lists[currentProj];
  const g = DATA.graphs[currentProj];
  document.getElementById('metrics').textContent =
    `${g.nodes.length} cards - ${p.n_edges.toLocaleString()} projection edges - ${p.communities.length} communities - showing top-${g.edges.length} strongest links`;
  const leg = document.getElementById('legend');
  leg.innerHTML = '';
  for (const c of p.communities) {
    const chip = document.createElement('span');
    chip.className = 'chip';
    chip.style.background = color(c.cluster_id);
    chip.style.color = '#fff';
    const label = c.top_concepts.slice(0,2).map(t => t.concept.split(':').pop()).join(' + ');
    chip.textContent = `#${c.cluster_id} (${c.size}) ${label}`;
    leg.appendChild(chip);
  }
  document.getElementById('graph-container').style.display = currentView === 'graph' ? 'block' : 'none';
  document.getElementById('main').style.display = currentView === 'list' ? 'block' : 'none';
}

function renderList() {
  const p = DATA.lists[currentProj];
  const main = document.getElementById('main');
  let h = '';
  const sorted = p.communities.slice().sort((a,b) => b.size - a.size);
  for (const c of sorted) {
    h += `<section class="cluster"><h2><span class="swatch" style="background:${color(c.cluster_id)}"></span>Cluster #${c.cluster_id} - ${c.size} cards</h2>`;
    h += `<div class="concepts">${c.top_concepts.map(t => `${esc(t.concept)} (${t.score.toFixed(1)})`).join(' - ')}</div>`;
    h += `<div class="cards">`;
    for (const card of c.cards) {
      h += `<div class="card"><span class="mana">${esc(card.mana_cost)}</span><div class="name">${esc(card.name)}</div><div class="type">${esc(card.type_line)}</div></div>`;
    }
    h += `</div></section>`;
  }
  main.innerHTML = h;
}

function renderGraph() {
  const svg = document.getElementById('graph-svg');
  const c = document.getElementById('graph-container');
  const W = c.clientWidth, H = c.clientHeight;
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  svg.innerHTML = '<g id="g-root"></g>';

  const g = DATA.graphs[currentProj];
  const nodes = g.nodes.map(n => ({...n, x: W/2 + (Math.random()-0.5)*W*0.6, y: H/2 + (Math.random()-0.5)*H*0.6, vx:0, vy:0}));
  const idIdx = new Map(nodes.map((n,i) => [n.id, i]));
  const edges = g.edges.map(e => ({source: nodes[idIdx.get(e.from)], target: nodes[idIdx.get(e.to)], weight: e.weight}));
  const N = nodes.length;
  const REPULSE = 4500, SPRING = 0.02, DAMP = 0.85, CENTER = 0.006;

  for (let iter = 0; iter < 160; iter++) {
    for (let i = 0; i < N; i++) {
      for (let j = i+1; j < N; j++) {
        const a = nodes[i], b = nodes[j];
        const dx = a.x - b.x, dy = a.y - b.y;
        const d2 = dx*dx + dy*dy + 0.01;
        const f = REPULSE / d2;
        const d = Math.sqrt(d2);
        const fx = f*dx/d, fy = f*dy/d;
        a.vx += fx; a.vy += fy;
        b.vx -= fx; b.vy -= fy;
      }
    }
    for (const e of edges) {
      const dx = e.target.x - e.source.x, dy = e.target.y - e.source.y;
      const d = Math.sqrt(dx*dx + dy*dy) + 0.01;
      const rest = 60;
      const f = SPRING * (d - rest) * Math.min(2.5, e.weight/3);
      const fx = f * dx / d, fy = f * dy / d;
      e.source.vx += fx; e.source.vy += fy;
      e.target.vx -= fx; e.target.vy -= fy;
    }
    for (const n of nodes) {
      n.vx += (W/2 - n.x) * CENTER;
      n.vy += (H/2 - n.y) * CENTER;
      n.vx *= DAMP; n.vy *= DAMP;
      n.x += n.vx; n.y += n.vy;
      n.x = Math.max(10, Math.min(W-10, n.x));
      n.y = Math.max(10, Math.min(H-10, n.y));
    }
  }

  const root = document.getElementById('g-root');
  let s = '';
  for (const e of edges) {
    s += `<line class="g-edge" x1="${e.source.x.toFixed(1)}" y1="${e.source.y.toFixed(1)}" x2="${e.target.x.toFixed(1)}" y2="${e.target.y.toFixed(1)}" stroke-width="${Math.max(0.3, Math.log(1+e.weight)*0.4).toFixed(2)}"/>`;
  }
  for (const n of nodes) {
    const col = color(n.cluster);
    s += `<circle class="g-node" cx="${n.x.toFixed(1)}" cy="${n.y.toFixed(1)}" r="5" fill="${col}" stroke="#fff" stroke-width="1" data-name="${esc(n.name)}" data-type="${esc(n.type_line)}" data-cluster="${n.cluster}"/>`;
  }
  root.innerHTML = s;

  const tip = document.getElementById('graph-tooltip');
  root.querySelectorAll('.g-node').forEach(el => {
    el.addEventListener('mouseenter', ev => {
      const r = c.getBoundingClientRect();
      tip.innerHTML = `<div style="font-weight:600">${el.dataset.name}</div><div style="color:#888;font-size:11px">${el.dataset.type}</div><div style="color:#888;font-size:11px">cluster #${el.dataset.cluster}</div>`;
      tip.style.left = (ev.clientX - r.left + 12) + 'px';
      tip.style.top = (ev.clientY - r.top + 12) + 'px';
      tip.style.display = 'block';
    });
    el.addEventListener('mouseleave', () => tip.style.display = 'none');
  });
}

function render() {
  renderMetrics();
  if (currentView === 'graph') renderGraph(); else renderList();
  for (const btn of document.querySelectorAll('.tabs button[data-proj]')) {
    btn.classList.toggle('active', btn.dataset.proj === currentProj);
  }
  for (const btn of document.querySelectorAll('.tabs button[data-view]')) {
    btn.classList.toggle('active', btn.dataset.view === currentView);
  }
}

document.querySelectorAll('.tabs button[data-proj]').forEach(btn => {
  btn.addEventListener('click', () => { currentProj = btn.dataset.proj; render(); });
});
document.querySelectorAll('.tabs button[data-view]').forEach(btn => {
  btn.addEventListener('click', () => { currentView = btn.dataset.view; render(); });
});
render();
</script>
</body></html>
"""


def main():
    faces = {}
    for line in FACES_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip():
            d = json.loads(line)
            faces[d["id"]] = d
    data = build_data(faces)
    buttons_parts = []
    for i, (name, label) in enumerate(TABS):
        cls = ' class="active"' if i == 0 else ""
        buttons_parts.append(f'  <button data-proj="{name}"{cls}>{label}</button>')
    buttons = "\n".join(buttons_parts)
    html = HTML_TMPL.replace("__TAB_BUTTONS__", buttons).replace(
        "__DATA__", json.dumps(data, separators=(",", ":"))
    )
    OUT_PATH.write_text(html, encoding="utf-8")
    print(f"wrote {OUT_PATH.relative_to(ROOT)}  ({len(html)/1024:.1f} KB)")
    for name, _lbl in TABS:
        n = len(data["graphs"][name]["nodes"])
        e = len(data["graphs"][name]["edges"])
        cc = len(data["lists"][name]["communities"])
        print(f"  {name:<10s} {n:3d} nodes, {e:4d} edges, {cc:2d} communities")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
