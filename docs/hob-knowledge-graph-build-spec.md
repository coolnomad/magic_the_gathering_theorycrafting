# HOB Mechanistic Knowledge Graph: CLI Agent Build Specification

## Objective

Build a rules-grounded, executable mechanistic knowledge graph for the 193 mechanically unique cards in *Magic: The Gathering—The Hobbit* (`HOB`). The graph must describe what cards can do, what their operations consume and produce, what states enable them, and how their outputs can satisfy other operations' requirements.

Do **not** use card quality, win rate, draft statistics, archetype labels, community ratings, or subjective statements such as “synergizes with.” The base graph represents rules-defined possibility. Empirical support and outcome effects belong in later layers.

The graph must support:

1. expansion from a card-to-card relationship into the exact mechanistic path that justifies it;
2. multiple directed relationships between the same ordered card pair;
3. higher-order mechanisms such as Storied without enumerating every card triple;
4. deck projection into mechanistic capacity space;
5. later attachment of deck outcomes, replays, and causal intervention estimates;
6. complete provenance back to card face, Oracle-text span, comprehensive-rules rule, or official release note.

## Source corpus

### Required

- Scryfall API query: `set:hob`, `unique=cards`, excluding extras, multilingual copies, and variations.
- Official HOB release notes and mechanics article.
- Current Magic Comprehensive Rules, especially rules for zones, objects, mana, costs, casting, triggered and activated abilities, replacement effects, tokens, counters, Adventures, Sagas, Equipment, Vehicles, and the legend rule.

### Expected Scryfall payload

At the time of this specification, the normalized Scryfall query returns:

- 193 unique cards;
- 168 normal layouts;
- 17 Adventure layouts;
- 8 Saga layouts;
- 17 records without top-level `oracle_text`, corresponding to face-based Adventure cards;
- 49 cards with `all_parts` links, primarily token/component relations;
- 23 cards with `produced_mana`;
- 10 Oracle texts containing Recruit;
- 9 containing Storied;
- 2 containing hone-counter text.

Do not use the 321-print gallery count. Alternate art, frames, and treatments are not distinct game components.

### Source snapshot

Save raw sources with retrieval timestamps and hashes. Builds must be reproducible from a frozen source snapshot.

```text
data/raw/
  scryfall_hob.json
  hob_release_notes.html
  hob_mechanics.html
  comprehensive_rules.txt
  source_manifest.json
```

## Non-negotiable modeling principles

1. **Direction is mandatory.** `A -> B` and `B -> A` are separate claims.
2. **Primitive edges are typed.** Avoid generic `INTERACTS_WITH` or `SYNERGIZES_WITH` edges.
3. **Cards are not the only nodes.** Include card faces, abilities, operations, events, resources, zones, object predicates, counters, and state/gate nodes.
4. **Pair relations are derived views.** The authoritative claim is normally a path through intermediate nodes.
5. **Conditions are explicit.** “Recruit enables Master's Councillors” requires the condition that the Recruit draw is the second draw of that turn.
6. **Higher-order conditions use gates/factors.** Storied is a distinct-object counting gate, not a set of pairwise edges or enumerated triples.
7. **No value judgments.** Rules-grounded compatibility is not empirical complementarity and not outcome synergy.
8. **Absence is valid.** Most ordered pairs may have no bounded mechanistic relationship.
9. **Infrastructure stays queryable but separable.** Mana-payment paths belong in the graph but should be filterable so they do not dominate mechanism-specific analyses.
10. **Every asserted primitive edge requires provenance.** Derived paths require references to the primitive edges and derivation rule.

## Graph model

Use a typed, directed property multigraph with reified gate/transition nodes. A hypergraph or factor-graph view can be exported from the same representation.

### Node types

Minimum node vocabulary:

| Node type | Examples |
|---|---|
| `Card` | Patient Instructor |
| `CardFace` | Bilbo, Luckwearer; Burglar's Plot |
| `Ability` | Patient Instructor ETB ability |
| `Operation` | recruit, draw, discard, create token, mill |
| `Event` | creature enters, creature dies, attack declared, second card drawn |
| `Resource` | blue mana, generic-payment capacity, card in hand, creature body |
| `ObjectClass` | Human, Soldier, artifact, legendary permanent, Saga |
| `Zone` | library, hand, battlefield, graveyard, exile, stack |
| `CounterType` | +1/+1, hone, lore, quest |
| `State` | enduring story, threshold active, ferocious active |
| `Gate` | Storied distinct-count threshold, nonland-discard branch |
| `Cost` | mana cost, crew 2, sacrifice a creature, discard a card |
| `Effect` | +1/+1 until EOT, create Human Soldier, ward {1} |
| `Rule` | recruit definition, Adventure casting rule |

### Primitive edge types

Start with a controlled vocabulary. Add a new type only through a schema change.

```text
HAS_FACE              Card -> CardFace
HAS_ABILITY           CardFace -> Ability
HAS_TYPE              CardFace/Object -> ObjectClass
HAS_KEYWORD           CardFace/Ability -> Rule or Operation
HAS_COST              CardFace/Ability -> Cost
REQUIRES              Ability/Transition/Gate -> Resource/State/ObjectClass
CONSUMES              Operation/Transition -> Resource/Object
PRODUCES              CardFace/Ability/Operation -> Resource/Event/Object/State
CAUSES                Event/Operation/Ability -> Event/Effect
TRIGGERS               Event -> Ability
MODIFIES               Ability/Effect -> Operation/State/ObjectClass
COUNTS                 Gate -> qualifying ObjectClass predicate
CONTRIBUTES_TO         CardFace/Object -> Gate
SATISFIES              Resource/State/Event -> Cost/Gate/Condition
ENABLES                State/Resource/Event -> Ability/Operation
PREVENTS               Effect/State -> Event/Operation
REPLACES               Ability/Effect -> Event/Effect
MOVES_FROM             Operation -> Zone
MOVES_TO               Operation -> Zone
CREATES_OBJECT         Operation -> ObjectClass/token specification
ADDS_COUNTER           Operation -> CounterType
REMOVES_COUNTER        Operation -> CounterType
SCALES_WITH            Ability/Effect -> Resource/State
PERSISTS_AS            State -> State
REFERENCES_RULE        assertion -> Rule
DERIVED_FROM           derived assertion -> primitive assertion
```

The edge record must permit parallel edges between the same nodes.

### Edge properties

```json
{
  "edge_id": "stable-id",
  "source": "node-id",
  "target": "node-id",
  "predicate": "ENABLES",
  "polarity": "positive",
  "scope": "controller",
  "timing": "same_turn",
  "condition_ids": ["condition-id"],
  "quantity": null,
  "optional": false,
  "certainty": "rules_explicit",
  "provenance_ids": ["prov-id"],
  "extractor": "mechanical|llm|rule_expansion|derived_projection",
  "review_status": "unreviewed|accepted|rejected"
}
```

### Conditions and gates

Represent conditions as structured expressions, not prose alone.

```json
{
  "condition_id": "second-draw-condition",
  "expression": {
    "op": "eq",
    "args": [
      {"state": "cards_drawn_this_turn_after_event"},
      2
    ]
  },
  "human_readable": "The draw is the controller's second card drawn that turn."
}
```

Storied must be represented once as a gate:

```json
{
  "gate_id": "storied-gate",
  "gate_type": "distinct_object_threshold",
  "population": {
    "zone": "battlefield",
    "controller": "you",
    "predicate": {
      "op": "or",
      "args": [
        {"has_supertype": "Legendary"},
        {"has_type": "Artifact"},
        {"has_subtype": "Saga"}
      ]
    }
  },
  "aggregation": "count_distinct_objects",
  "comparison": ">=",
  "threshold": 3,
  "output_state": "enduring_story",
  "output_persistence": "rest_of_game",
  "double_count_multiqualifying_object": false
}
```

Do not enumerate approximately 1.18 million triples. Cards and token-producing operations contribute qualifying objects to this gate.

## Repository deliverables

```text
hob-kg/
  README.md
  pyproject.toml
  data/
    raw/
    normalized/cards.jsonl
    normalized/faces.jsonl
    normalized/tokens.jsonl
    rules/mechanics.jsonl
    rules/conditions.jsonl
    graph/nodes.jsonl
    graph/edges.jsonl
    graph/hyperedges.jsonl
    graph/card_pair_projection.jsonl
    review/llm_candidates.jsonl
    review/llm_rejections.jsonl
  schema/
    node.schema.json
    edge.schema.json
    condition.schema.json
    gate.schema.json
    llm_output.schema.json
  src/hobkg/
    fetch.py
    normalize.py
    mana.py
    types.py
    rules.py
    extract_mechanical.py
    infer_llm.py
    assemble.py
    project_pairs.py
    validate.py
    cli.py
  tests/
    fixtures/
    test_normalize.py
    test_mana.py
    test_adventure.py
    test_recruit.py
    test_storied.py
    test_projection.py
    test_invariants.py
  reports/
    coverage.md
    unresolved.md
    validation.md
```

Recommended implementation: Python, Pydantic or JSON Schema for validation, NetworkX or a simple JSONL edge store for early analysis, and optional RDF/Neo4j export later. Do not begin with a graph database; establish correct semantics and stable schemas first.

## Build pipeline

### Phase 0: initialize and freeze scope

1. Create repository and tests.
2. Fetch exactly the 193 unique HOB card identities.
3. Store source hashes and retrieval timestamps.
4. Assert set code `hob`, card count 193, Adventure count 17, Saga count 8.
5. Exclude HOC, tokens as deckable cards, alternate printings, and treatments from the 193-card universe.

### Phase 1: deterministic normalization

This phase must not call an LLM.

#### Card and face normalization

```python
def normalize_card(raw):
    card = Card(
        id=f"card:{raw['oracle_id']}",
        scryfall_id=raw['id'],
        name=raw['name'],
        set_code=raw['set'],
        collector_number=raw['collector_number'],
        layout=raw['layout'],
        rarity=raw['rarity'],
        color_identity=raw['color_identity'],
    )

    if raw['layout'] == 'adventure':
        faces = [normalize_face(card.id, i, f) for i, f in enumerate(raw['card_faces'])]
    else:
        faces = [normalize_top_level_as_face(card.id, raw)]

    return card, faces
```

Preserve each Adventure face independently. The permanent face and Adventure spell have different names, types, costs, zones of operation, and effects.

#### Type-line parsing

Mechanically parse supertypes, card types, and subtypes around em dash separators. Preserve raw text.

```python
KNOWN_SUPERTYPES = {'Basic', 'Legendary', 'Snow', 'World', 'Ongoing'}
KNOWN_TYPES = {'Artifact','Battle','Creature','Enchantment','Instant','Kindred',
               'Land','Planeswalker','Sorcery'}

def parse_type_line(text):
    left, *right = text.split(' — ', 1)
    words = left.split()
    return {
        'supertypes': [w for w in words if w in KNOWN_SUPERTYPES],
        'types': [w for w in words if w in KNOWN_TYPES],
        'subtypes': right[0].split() if right else []
    }
```

#### Mana parsing

Parse mana symbols structurally, including generic, colored, hybrid, variable, and tap symbols. Create resource nodes rather than direct land-to-every-card assertions.

```python
def parse_mana_cost(cost_string):
    symbols = TOKEN_RE.findall(cost_string or '')
    return [classify_symbol(s) for s in symbols]

def payment_capabilities(produced_mana):
    # Colored mana can pay a matching colored/hybrid option and generic costs.
    # Colorless mana can pay {C} and generic costs.
    # Never infer that colored mana satisfies a different colored pip.
    ...
```

Represent:

```text
Island -> PRODUCES -> blue mana
blue mana -> SATISFIES -> generic mana payment
blue mana -> SATISFIES -> blue pip payment
Card face -> HAS_COST -> structured mana cost
```

The card-to-card projection may later derive `Island ENABLES_CASTING BlueCard`, but mark it as an infrastructure relation and retain the underlying path.

#### Token/component links

Use `all_parts` mechanically where present, but verify that the linked component matches Oracle text. Create token specification nodes even if a token object link is absent.

#### Keyword and reminder-text handling

Store Scryfall `keywords`, but do not assume completeness. HOB's new mechanics are often present only in Oracle text. Expand named mechanics from the official rule library, not from reminder text independently on every card.

```python
for face in faces:
    for mechanic in MECHANIC_LEXICON:
        if mechanic.pattern.search(face.oracle_text):
            add(face, HAS_KEYWORD, mechanic.rule_node)
            instantiate_rule_template(face, mechanic)
```

#### Exact syntactic extractions

Use conservative parsers/regex for high-precision patterns:

- `create ... token(s)`;
- `draw N card(s)`;
- `discard ...`;
- `mill N`;
- `sacrifice ...`;
- `add {mana}`;
- `put ... counter(s)`;
- `return ... from graveyard to hand/battlefield`;
- `exile ...`;
- ETB, death, attack, upkeep, end-step triggers;
- activated ability delimiter `cost: effect`;
- static type/count predicates;
- explicit “other,” “another,” “up to,” “may,” and “only once each turn.”

Only emit a mechanical primitive edge when the parse is unambiguous. Otherwise create an unresolved extraction task for the LLM.

### Phase 2: mechanic templates

Encode reusable rules once and instantiate them on cards.

#### Recruit

```python
def expand_recruit(source_ability):
    event = new_operation('recruit', source_ability)
    draw = new_operation('draw', quantity=1)
    discard = new_operation('discard', quantity=1, choice='controller')
    gate = new_gate('discarded_card_is_nonland')
    soldier = token_spec(colors=['W'], power=1, toughness=1,
                         types=['Creature'], subtypes=['Human','Soldier'])

    edge(event, CAUSES, draw)
    edge(draw, CAUSES, discard, ordering='after')
    edge(discard, MOVES_TO, GRAVEYARD)
    edge(discard, CAUSES, gate)
    edge(gate, CREATES_OBJECT, soldier, condition='true')
```

#### Storied

Instantiate the single gate defined above. Each card face with an appropriate permanent type contributes its own battlefield object. Operations that create qualifying tokens contribute the created object, not the source card itself. Cards with Storied payoffs receive edges from `enduring_story` to the specific enabled/static effect.

#### Hone

Represent hone counters as counters on Equipment objects. The counter modifies the attached creature's power by +1 per counter. Do not attach the power bonus directly to the source card that placed the counter.

#### Adventure

Represent the spell face as castable from hand. On resolution, it moves to exile under the Adventure rule and enables later casting of the permanent face from exile. Preserve the alternative of casting the permanent face normally from hand.

#### Saga

Represent lore counters, chapter triggers, and sacrifice after the final chapter. A Saga is a qualifying Storied permanent only while it remains on the battlefield, but crossing the Storied threshold produces a persistent state.

### Phase 3: LLM semantic extraction

Use the LLM only where semantic interpretation is necessary. Do not ask the model to compare all 37,249 ordered pairs from raw text independently. First extract each card into structured operations; then derive most pair relations mechanically by output-to-requirement matching. Pairwise LLM review is a backstop for unresolved or ambiguous cases.

#### LLM responsibilities

The LLM should:

1. split complex Oracle text into distinct abilities and clauses;
2. identify trigger, cost, target, effect, duration, controller, optionality, and conditions;
3. resolve pronouns and local references such as “it,” “that card,” “that creature,” and “this way”;
4. distinguish costs from effects and replacement effects from triggers;
5. identify resources/states produced and requirements consumed;
6. recognize conditional branches and ordering;
7. identify when one effect changes the magnitude, timing, target set, or availability of another operation;
8. flag rules ambiguity rather than improvise;
9. propose a controlled-vocabulary extension when no existing predicate fits;
10. cite exact Oracle spans and rule definitions for every proposed assertion.

The LLM must **not**:

- infer that cards are good or bad;
- infer empirical synergy;
- use color/archetype co-membership as an interaction;
- invent an edge because two cards share a theme;
- treat possible co-occurrence as causation;
- omit conditions to make an edge simpler;
- infer opponent cooperation or favorable decisions;
- assert a pair interaction without an explicit mechanistic path;
- translate flavor text into mechanics.

#### LLM input unit

Prefer one card face plus already-normalized rules context:

```json
{
  "card": {...},
  "face": {...},
  "mechanic_templates": [...],
  "controlled_predicates": [...],
  "known_tokens": [...],
  "relevant_rules": [...],
  "mechanical_extractions": [...]
}
```

Require JSON-only output conforming to `llm_output.schema.json`.

#### LLM output

```json
{
  "abilities": [
    {
      "ability_id": "...",
      "kind": "triggered|activated|static|replacement|spell_effect",
      "trigger": {...},
      "costs": [...],
      "conditions": [...],
      "effects": [...],
      "oracle_spans": [...],
      "confidence": "high|medium|low",
      "unresolved": []
    }
  ],
  "proposed_edges": [...],
  "schema_extension_requests": []
}
```

Reject outputs containing unsupported predicates, missing provenance, invalid node IDs, unstructured conditions, or evaluative language.

#### Second-pass LLM review

Run an independent critic prompt over the candidate extraction:

```text
Given the Oracle text, normalized fields, mechanic rules, and candidate assertions:
1. identify assertions not entailed by the rules;
2. identify missing conditions, scope, timing, optionality, or duration;
3. identify omitted mechanistic outputs or requirements;
4. identify incorrect identity resolution;
5. return corrected JSON, not prose.
```

Accept automatically only high-confidence assertions on which extractor and critic agree and which pass deterministic validation. Queue the rest for review.

### Phase 4: graph assembly

Assemble card-local structured operations into the global graph.

```python
def assemble_global_graph(cards, faces, abilities, rule_templates):
    graph = MultiDiGraph()
    add_normalized_entity_nodes(graph, cards, faces)
    add_rule_nodes(graph, rule_templates)
    add_ability_subgraphs(graph, abilities)
    canonicalize_shared_nodes(graph)  # e.g., draw event, Human class, blue mana
    instantiate_gates(graph)
    validate_primitive_edges(graph)
    return graph
```

Canonicalize concepts carefully. All Recruit abilities should point to one Recruit rule/operation template, while each execution remains attributable to its source ability.

### Phase 5: derive card-pair projections

Do not treat the 37,249 pair scan as the source of truth. Derive ordered pair relationships by bounded traversal through the primitive graph.

#### Allowed path grammar

Define meaningful path templates, for example:

```text
Card -> Ability -> Operation -> Resource/State -> Requirement -> Ability -> Card
Card -> Ability -> Event -> TriggeredAbility -> Card
Card -> Type/Object -> CountGate -> State -> Effect/Ability -> Card
Card -> ManaResource -> Cost -> Card
Card -> RemovalEffect -> RequiredObject/State -> Card
```

Exclude meaningless paths that merely share an ancestor or ontology class.

```python
PATH_TEMPLATES = {
  'ENABLES_TRIGGER': [...],
  'SATISFIES_COST': [...],
  'SUPPLIES_RESOURCE': [...],
  'AMPLIFIES_EFFECT': [...],
  'PREVENTS_OPERATION': [...],
  'CONTRIBUTES_TO_GATE': [...],
  'RECOVERS_RESOURCE': [...],
  'INFRASTRUCTURE_CASTING': [...],
}

def project_pair(graph, source_card, target_card, max_depth=8):
    results = []
    for relation, grammar in PATH_TEMPLATES.items():
        for path in constrained_paths(graph, source_card, target_card,
                                      grammar=grammar, max_depth=max_depth):
            results.append(metaedge_from_path(relation, path))
    return deduplicate_semantically(results)

for a in cards:
    for b in cards:  # includes self-pairs
        emit(a, b, project_pair(graph, a, b))
```

Each projected metaedge stores:

- ordered source and target cards;
- derived relation type;
- complete primitive path;
- combined conditions;
- whether the relationship is infrastructure-only;
- minimum path length;
- provenance closure;
- whether the path involves a gate or persistent state.

If no allowed path exists, emit `relations: []`. Do not ask the LLM to manufacture one.

#### Pairwise LLM audit

After mechanical projection, give the LLM only pairs likely to contain a missed relationship:

- shared resource/output vocabulary but no derived path;
- direct named references;
- replacement or prevention effects;
- copy/self-pair questions;
- ambiguous “this way”/“that card” scope;
- cards with schema-extension requests;
- pairs nominated by a human query.

The audit prompt must return either a path grounded in primitive operations or `NO_RELATION`.

### Phase 6: higher-order mechanism assembly

Discover higher-order structures by grouping edges around shared gates, resources, and state transitions—not by enumerating all triples.

```python
def mechanism_modules(graph):
    for gate in graph.nodes(type='Gate'):
        yield {
          'gate': gate,
          'contributors': upstream_components(graph, gate),
          'consumers': downstream_consumers(graph, gate),
          'conditions': gate.conditions,
          'feedback_cycles': directed_cycles_through(graph, gate)
        }
```

Create explicit module views for Recruit, Storied, Hone/Equipment, Amass, Ferocious, Landfall, graveyard reuse, token production, second-draw triggers, and other structures discovered from the graph. These labels index formal subgraphs; they are not subjective archetype assignments.

## Validation requirements

### Schema and integrity

- Every node and edge validates against JSON Schema.
- Every ID is stable and unique.
- Every primitive edge has provenance.
- Every derived pair relation has at least one valid primitive path.
- Every condition ID resolves.
- Every card and face is represented exactly once.
- Every Adventure has exactly two face nodes and correct face roles.
- All graph targets exist.

### Semantic invariants

Write tests for at least these claims:

1. Recruit always yields draw then discard; Soldier creation is conditional on nonland discard.
2. A Recruit source can enable Master's Councillors only through the second-draw condition; Councillors does not affect Recruit.
3. Bard, King of Dale modifies both Recruit's draw quantity and token quantity through replacement effects.
4. Storied counts three distinct controlled battlefield objects satisfying a union predicate.
5. A legendary artifact counts once, not twice, for Storied.
6. Enduring story persists after qualifying permanents leave.
7. A card that creates a qualifying artifact token may install an additional qualifying object.
8. Adventure spell and permanent faces remain distinct.
9. Island produces blue mana; blue mana can pay blue and generic requirements, but not white pips.
10. “Other” and “another” exclusions prevent false self-effects.
11. Legend-rule conflicts are represented as state constraints, not subjective negative synergy.
12. Self-pair output distinguishes one object affecting itself from one copy affecting another copy.

### Coverage report

Report:

- cards/faces fully parsed;
- abilities by type;
- primitive edges by predicate and extractor;
- unresolved Oracle clauses;
- LLM assertions accepted/rejected;
- cards with no non-infrastructure outgoing edges;
- cards with no non-infrastructure incoming edges;
- pair relations by type;
- pairs with multiple relation types;
- gate-mediated relations;
- infrastructure-only relations;
- source/provenance gaps.

Coverage is not correctness. Do not maximize edge count.

### Manual gold set

Before full acceptance, hand-review a stratified sample:

- all 10 Recruit cards;
- all 9 Storied cards;
- all 17 Adventures;
- all 8 Sagas;
- all cards with replacement effects;
- all cards producing multiple tokens or object types;
- at least 20 null card pairs;
- at least 10 self-pairs;
- at least 20 multi-edge pairs.

Use these as regression fixtures.

## CLI interface

Implement commands approximately as follows:

```bash
hobkg fetch --set hob --output data/raw
hobkg normalize --input data/raw/scryfall_hob.json
hobkg extract-mechanical
hobkg expand-rules --mechanics recruit,storied,hone,adventure,saga
hobkg infer-llm --model-config config/model.json --resume
hobkg review-llm --critic-config config/critic.json --resume
hobkg assemble
hobkg project-pairs --max-depth 8
hobkg validate --strict
hobkg report
hobkg export --format jsonl
hobkg query-card "Patient Instructor"
hobkg query-pair "Patient Instructor" "Master's Councillors"
hobkg query-mechanism storied
```

All stages must be idempotent and resumable. Cache LLM requests by hash of prompt, source text, rule context, schema version, and model configuration.

## Agent execution discipline

The CLI agent implementing this specification must:

1. write schemas and tests before bulk LLM extraction;
2. inspect repository instructions and preserve unrelated files;
3. implement and validate deterministic normalization first;
4. build the mechanic-rule library before pair projection;
5. test on Recruit and Storied as vertical slices;
6. show that the Recruit-to-Councillors direction and Storied gate are correct;
7. then process the remaining cards;
8. never silently repair invalid LLM output—reject or queue it;
9. record every schema revision;
10. stop and report if source counts change, rules conflict, or a new mechanic cannot be represented without a schema decision.

## Completion criteria

The build is complete only when:

- all 193 cards are normalized;
- all 17 Adventures and 8 Sagas pass dedicated tests;
- all named HOB mechanics have reusable rule templates;
- every Oracle clause is parsed, deliberately ignored with a reason, or listed unresolved;
- the global typed multigraph validates;
- all 37,249 ordered pairs, including self-pairs, have a derived projection record, even when empty;
- no projected relationship lacks an expandable primitive path;
- higher-order gates are represented without combinatorial enumeration;
- infrastructure edges can be filtered independently;
- validation and coverage reports are generated;
- a human can query any pair and see: relation type, direction, conditions, intermediate nodes, exact provenance, and whether the relation is primitive, mechanically derived, or LLM-inferred.

## Final epistemic boundary

The completed HOB KG establishes:

> Given the game rules and specified state conditions, component A can produce, enable, modify, prevent, consume, or satisfy something used by component B.

It does **not** establish:

> The pairing improves deck win rate, is worth drafting, is causal in observed games, or constitutes empirical synergy.

Those claims require deck composition, outcomes, adjustment for selection and player/context variables, and eventually replay-level evidence.
