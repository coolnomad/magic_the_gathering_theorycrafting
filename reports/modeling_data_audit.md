# Modeling data audit -- raw HOB game-level dataset

Section-17 audit of the 17Lands HOB Premier Draft file. Every number below is computed by `deckbench.audit` from the raw CSV. No modeling table, feature, split or model is produced here.

Source file: `data/raw/game_data_public.HOB.PremierDraft.csv.gz`

## 1. Key columns, named verbatim

| Role | Column |
| --- | --- |
| Draft identifier | `draft_id` |
| Per-game outcome | `won` |
| Deck contents | `deck_ column family` |
| Draft timestamp | `draft_time` |
| Per-game timestamp | `game_time` |
| Rank | `rank` |
| User historical win-rate bucket | `user_game_win_rate_bucket` |
| User games-played bucket | `user_n_games_bucket` |

## 2. Persistent player identifier

No persistent player identifier exists in the dataset. rank and opp_rank are six-level skill buckets, not player ids, and are not nominated as a substitute.

## 3. Dataset totals (computed, not transcribed)

- Total games (rows): **241727**
- Total drafts (distinct `draft_id`): **43161**
- Total columns: **985**
- Malformed rows (wrong width): **0**
- `draft_time` span: 2026-08-11 15:43:42 .. 2026-08-29 23:39:41

Manifest declares rows=241727, drafts=43161, columns=1165. Observed matches declared: rows=True, drafts=True, columns=False.

> **Discrepancy.** At least one declared total does not match the file. Per the card, this is a finding, reported rather than reconciled silently.

## 4. Column census by family

| Family | Columns |
| --- | --- |
| `deck_` | 193 |
| `sideboard_` | 193 |
| `opening_hand_` | 193 |
| `drawn_` | 193 |
| `tutored_` | 193 |
| non-card | 20 |

Non-card columns: `expansion`, `event_type`, `draft_id`, `draft_time`, `game_time`, `build_index`, `match_number`, `game_number`, `rank`, `opp_rank`, `main_colors`, `splash_colors`, `on_play`, `num_mulligans`, `opp_num_mulligans`, `opp_colors`, `num_turns`, `won`, `user_n_games_bucket`, `user_game_win_rate_bucket`

## 5. Within-draft deck variation

- Drafts with more than one deck configuration: **8191** (0.189778 of drafts)
- Games played after a deck change: **28397** (0.117475 of games)
- Distinct deck configurations per draft (configs: drafts): 1: 34970, 2: 6636, 3: 1314, 4: 210, 5: 29, 6: 2

## 6. `build_index` -- what it actually varies with

- Drafts where `build_index` is non-constant: 8241
- Drafts where the deck config is non-constant: 8191
- Drafts where `build_index` determines the deck config: 43161
- Drafts where the deck config determines `build_index`: 43100
- Drafts where `build_index` <-> deck config is bijective: 43100
- `build_index` varies while the deck is constant: 50
- Deck varies while `build_index` is constant: 0

## 7. Deck-size distribution and legality

- Legal Limited minimum deck size: 40
- Observed deck size: min 40, max 60, modal 40
- Rows below the legal minimum: **0**
- Distribution (size: rows): 40: 226047, 41: 13424, 42: 1064, 43: 568, 44: 245, 45: 142, 46: 63, 47: 27, 48: 36, 49: 24, 50: 27, 51: 5, 52: 8, 53: 10, 54: 12, 55: 8, 56: 3, 57: 4, 58: 5, 60: 5

## 8. Card-count consistency

No standalone deck-size column exists; deck size is defined as the sum of the deck_ columns. The consistency check is whether that sum lands on the modal legal size on every row.

- Rows off the modal deck size: **15680**
- Rows below the legal minimum: **0**

## 9. Skill-variable constancy within draft

| Column | Drafts where it is not constant |
| --- | --- |
| `rank` | 5420 |
| `user_game_win_rate_bucket` | 0 |
| `user_n_games_bucket` | 0 |

## 10. Recommended observational unit

**Unit: game.**

The deck is recorded per game and it changes within a draft: 0.1898 of drafts carry more than one deck configuration and 0.1175 of games are played after a deck change. Averaging a draft's games would blend distinct decks in exactly those drafts, so the observational unit is the game, keyed by draft_id + game_time. This follows benchmark section 6.

This is a recommendation; the operator ratifies the unit at card 007. The machine-readable form of every number above is in `reports/modeling_data_audit.json`.
