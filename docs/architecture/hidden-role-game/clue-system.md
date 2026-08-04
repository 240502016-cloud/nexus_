# Constrained clue system

## Principle

The rules engine creates clue meaning; the LLM may only render that meaning. MVP uses curated scenario definitions and localized string templates. Generated flavor is optional and cannot change logical difficulty.

Each crisis contains three disposition options (`SEAL`, `REVEAL`, `REDIRECT`) and exactly one safe option. It also contains:

- one public anchor proposition;
- one private `CONTAINMENT` proposition for the Sentinel;
- one private `PROVENANCE` proposition for the Archivist;
- one private `CONSEQUENCE` proposition for the Envoy.

The player receives the clue associated with their Office, not a clue that names their Mandate. This makes Office an information lens and Mandate an incentive layer.

## Definition schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "three-seals/scenario-v1",
  "type": "object",
  "additionalProperties": false,
  "required": ["scenario_key", "theme_tags", "options", "safe_option_id", "clues"],
  "properties": {
    "scenario_key": {"type": "string", "pattern": "^[A-Z0-9_]{3,64}$"},
    "theme_tags": {
      "type": "array",
      "minItems": 1,
      "maxItems": 5,
      "uniqueItems": true,
      "items": {"enum": ["ARCANE", "SCI_FI", "MYSTERY", "DIPLOMACY", "ARCHIVE"]}
    },
    "options": {
      "type": "array",
      "minItems": 3,
      "maxItems": 3,
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["id", "disposition", "title_key", "description_key"],
        "properties": {
          "id": {"type": "string", "pattern": "^[ABC]$"},
          "disposition": {"enum": ["SEAL", "REVEAL", "REDIRECT"]},
          "title_key": {"type": "string", "maxLength": 80},
          "description_key": {"type": "string", "maxLength": 120}
        }
      }
    },
    "safe_option_id": {"enum": ["A", "B", "C"]},
    "clues": {
      "type": "array",
      "minItems": 4,
      "maxItems": 4,
      "items": {"$ref": "#/$defs/clue"}
    }
  },
  "$defs": {
    "clue": {
      "type": "object",
      "additionalProperties": false,
      "required": ["id", "lens", "subject_option_id", "proposition", "strength", "template_key", "allowed_claims"],
      "properties": {
        "id": {"type": "string", "pattern": "^[A-Z0-9_]{3,64}$"},
        "lens": {"enum": ["PUBLIC", "CONTAINMENT", "PROVENANCE", "CONSEQUENCE"]},
        "subject_option_id": {"enum": ["A", "B", "C"]},
        "proposition": {"enum": ["SUPPORTS_SAFE", "EXCLUDES_SAFE", "RISK_HIGH", "RISK_LOW"]},
        "strength": {"enum": ["DECISIVE", "CORROBORATING"]},
        "template_key": {"type": "string", "pattern": "^[A-Z0-9_]{3,64}$"},
        "qualifier_tags": {
          "type": "array",
          "maxItems": 4,
          "uniqueItems": true,
          "items": {"type": "string", "pattern": "^[A-Z0-9_]{1,32}$"}
        },
        "allowed_claims": {
          "type": "array",
          "minItems": 1,
          "maxItems": 4,
          "uniqueItems": true,
          "items": {"enum": ["SUPPORTS_SAFE", "EXCLUDES_SAFE", "RISK_HIGH", "RISK_LOW"]}
        }
      }
    }
  }
}
```

## Offline validation

A scenario pack is rejected unless exhaustive enumeration proves all of these:

1. Options contain each disposition exactly once and `safe_option_id` exists.
2. There is exactly one clue for each lens and exactly one safe option under the canonical logic table.
3. The public clue plus any one private clue leaves at least two viable options; one player cannot solve the crisis alone.
4. The public clue plus any two honest private clues identifies exactly one safe option; cooperation can solve it even if the third player bluffs.
5. All four propositions are mutually consistent and every `SUPPORTS_SAFE`/`EXCLUDES_SAFE` statement is true under the solution.
6. No clue contains an Office, Mandate, player ID, personality trait, Party Lore fact or previous-match fact.
7. Each Office is decisive/corroborating equally often across the content pack and each disposition is safe equally often.
8. Reading length and logical operators are comparable across lenses so phrasing does not reveal which clue is decisive.
9. Scenarios are versioned and immutable after release; running games pin a content version.

## Rendered-clue output schema

The renderer receives only one canonical proposition, a cosmetic theme and at most one approved lore alias. It does not receive the safe option, assignments, other clues or player history.

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["rendered_text", "canonical_meaning_echo", "lore_reference_ids"],
  "properties": {
    "rendered_text": {"type": "string", "minLength": 8, "maxLength": 240},
    "canonical_meaning_echo": {
      "type": "object",
      "additionalProperties": false,
      "required": ["subject_option_id", "proposition", "qualifier_tags"],
      "properties": {
        "subject_option_id": {"enum": ["A", "B", "C"]},
        "proposition": {"enum": ["SUPPORTS_SAFE", "EXCLUDES_SAFE", "RISK_HIGH", "RISK_LOW"]},
        "qualifier_tags": {
          "type": "array",
          "maxItems": 4,
          "items": {"type": "string", "pattern": "^[A-Z0-9_]{1,32}$"}
        }
      }
    },
    "lore_reference_ids": {
      "type": "array",
      "maxItems": 1,
      "uniqueItems": true,
      "items": {"type": "string", "minLength": 1, "maxLength": 128}
    }
  }
}
```

Validation requires an exact normalized equality between `canonical_meaning_echo` and engine input. Text is rejected if it mentions an option other than the canonical subject, uses a role/mandate label, adds a number/negation not licensed by the template, claims certainty beyond the proposition, contains instructions, or exceeds length. Because semantic validation is not perfectly reliable, generated wording remains behind a feature flag and the curated deterministic renderer is the production default.

## Claims and evidence

The engine scores only the structured portion of a claim. Free text never becomes evidence.

```json
{
  "kind": "EVIDENCE",
  "subject_option_id": "B",
  "proposition": "EXCLUDES_SAFE",
  "flavor_text": "B seçeneğinin kayıt zinciri bana pek temiz görünmedi."
}
```

At round resolution, the engine compares this tuple to the scenario truth model:

- `SUPPORTED`: +1 public Insight and +1 Reputation, capped at 5.
- `CONTRADICTED`: no Insight and −1 Reputation, floored at 1.
- `UNRESOLVED`: no score/reputation change.

The verdict evaluates the proposition, not whether the player's private clue actually contained it. Players may truthfully infer or strategically bluff; the system does not expose which clue they saw.
