# Selector Grammar

Port edges reference bare concept IDs and encode targeting/restriction/controller
scope as structured selector data on the edge, not in the concept name.

## Structure

```json
{
  "controller": "you" | "any" | "opponent",
  "target": {
    "count": 1 | 2,
    "optional": true
  },
  "restriction": [
    {"another": true},
    {"excludes_type": "Land"},
    {"is_token": true}
  ]
}
```

## Fields

### `controller`

Who controls the selected object. Defaults to `"any"` if omitted.

- `"you"` — you control it
- `"any"` — any player controls it (typically for targets)
- `"opponent"` — an opponent controls it

### `target`

Targeting requirements per CR 114. Present only if the effect targets.

- `count`: how many objects must/may be chosen (1, 2, etc.)
- `optional`: whether this is "up to N" targeting

### `restriction`

List of constraints that filter the selectable set.

- `{"another": true}` — another (not this permanent)
- `{"excludes_type": "<Type>"}` — exclude permanents of that type
- `{"is_token": true}` — must be a token

## Examples

### "target creature"

```json
{
  "class": "obj:type:creature",
  "selector": {
    "target": {"count": 1}
  }
}
```

### "up to two other target nonland permanents you control"

```json
{
  "class": "obj:category:permanent",
  "selector": {
    "controller": "you",
    "target": {"count": 2, "optional": true},
    "restriction": [
      {"another": true},
      {"excludes_type": "Land"}
    ]
  }
}
```

### "target artifact token"

```json
{
  "class": "obj:type:artifact",
  "selector": {
    "target": {"count": 1},
    "restriction": [{"is_token": true}]
  }
}
```

## Anti-patterns

❌ `obj:target-creature` — selector baked into concept name

✅ `obj:type:creature` + `{"target": {"count": 1}}` — selector as edge data

The concept vocabulary contains only the *class* of object. Quantifiers, targeting,
controller scope, and restrictions live on the edge that references the concept.
