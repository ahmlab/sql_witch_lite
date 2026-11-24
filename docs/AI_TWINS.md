# The Twin Archivists: AI document

Game AI only (no machine learning). Teaches `JOIN`.
Play: `python -m sim.play_cli --foe twins --seed 7` · Evaluate: `python -m sim.twin_eval --n 300`

## The fight in one paragraph
Archivist Quill and Archivist Ink share one desk, one spell book and one mana pool, but each has
its own HP. If one twin falls, the other restores it on its next turn, so Ada must drop **both in
the same query**. Their elements and weaknesses are dealt again every round, so a hard-coded
element goes stale. A `WHERE` filter cannot aim two different spells at two different twins, but a
`JOIN` can: `JOIN enemies AS e ON s.element = e.weakness` returns one row per twin, with the twin's
name in the row as the target. The twins teach this by example: every query they write is a `JOIN`
(they JOIN to find Ada, and to find each other), so their first query is the Invitation.

## The five concepts and where they live
| Concept | File | What it does here |
|---|---|---|
| Finite state machine | `ai/archivists.py` `PairBrain.next_mode` | Five modes as a `match`: *bonded*, *pressed* (Ada found a way to hit both), *bereaved* (one twin down), *desperate* (pair HP under 30%), *winded* (not enough shared mana). The mode multiplies each goal's desirability. |
| Goal-driven behaviour | `ai/archivists.py` evaluators and plans, `ai/goals.py` | Seven joint goals: restore, mend, guard, volley, barrage, strike, rest. Each is scored from the Percept and the mode, noise and a repeat penalty keep it varied, and the winner runs as a multi-turn plan. A plan that becomes impossible (mana spent) fails and they replan in the same turn. |
| Perception | `PairPerception` | Reads both twins' HP, who has fallen, who leads and who is weaker, the shared pool and what it can afford, whether Ada knows `JOIN`, whether her last query hit both twins (with a fading memory), and a pair-wide threat estimate. The brain never reads the battle state directly. |
| Steering behaviours | `ai/pair.py`, `ai/steering.py` | Each twin has a body on a small stage. The leader charges (arrive), its partner shadows it (pursue), the weaker twin backs off (evade), the living twin walks to the fallen one to restore it, both drift (wander) when resting, and a separation push keeps them from merging. Movement is only for show: no roll or decision reads a position (tested). |
| Procedural generation | `ai/pair.py` `Pair.reroll` | Each round, with a seeded generator of its own, each twin gets an element and a weakness drawn from the two elements that really beat it in the type chart. The weaknesses always differ, so one `JOIN` yields one spell per twin. Same seed, same deals. |

Navigation was not used: the fight has no map to path through, and a forced A* would not
serve the mechanic.

## One turn of the twins
1. **Perceive**: `PairPerception.sense` builds a `PairPercept`.
2. **Mode**: `next_mode` matches the percept (for example `bereaved` when a twin is down).
3. **Think**: every goal is scored, the best becomes a plan (a restore is worth far more than a volley when a twin is down and mana allows).
4. **Move**: the plan sets a movement for the lead, and the partner's order follows from the plan.
5. **Express**: `render_archivists` writes the joint move as one `JOIN` query with one row per spell; the intent is then discarded.
6. **Execute**: the query goes through the same casting contract as Ada's. Rows cost shared mana; a restore revives a fallen twin at 60 HP.
7. **Round end**: new elements and weaknesses are dealt and mirrored into `enemies`.

## Changes to shared code (all small and additive)
- `magic/rules.py`: `BattleState.twin` and `.pair`; `side("twin")`; the foe side loses only when both twins are down; the twin's ward halves and exhaustion clears with the first twin; `CastMemory.targets`.
- `magic/cast.py`: the second twin's name is a valid target; new `restore` spell kind; a restore with no named target reaches for the partner; exhaustion applies to both twins; `sync_state` mirrors the pair.
- `magic/battle.py`: builds the pair, re-deals weaknesses at round end, lets the twins walk after they cast, and remembers which foes Ada hit.
- `ai/roster.py`: the `twins` guardian (`world`, `extra_foe_ids` fields). In `ORDER` as the third fight (Slime, Knight, Twins, Lich).
- `sim/play_cli.py`: `--foe twins`, two HP bars, the stage line, `:map`, restore narration.
- `data/foes.csv`, `data/foe_spells.csv`: two foes, five spells. `tests/test_tutorial_logic.py`: the hard-coded foe count went from 3 to 5.

## Evaluation (300 seeded battles per row, Ada level 4, 105 HP)
| Player | vs | Ada wins | Rounds | Ada HP left |
|---|---|---|---|---|
| Novice (strongest spell, no target in the row) | PairBrain | 0% | 7.3 | 0 |
| Aimer (WHERE + ORDER BY, one twin only) | PairBrain | 0% | stalemate (40+) | 58.9 |
| Joiner (the JOIN lesson, heals when low) | PairBrain | 100% | 8.0 | 54.9 |
| Novice | RandomBrain | 0% | 12.4 | 0 |
| Aimer | RandomBrain | 0% | stalemate (35.8) | 45.9 |
| Joiner | RandomBrain | 99% | 5.4 | 68.0 |

- The brain kills a player who ignores the lesson in 7.3 rounds against 12.4 for a random brain, and it holds out longer against the right technique (8.0 rounds against 5.4) while costing Ada more HP (54.9 left against 68.0).
- The aimer never wins: without a `JOIN` the spell reaches only the first twin, and the other restores it. That is the lesson, shown mechanically.
- Decision time is about 2 ms. The same seed replays the same battle, and turning steering off changes nothing (both tested).
- Honest limits: a player who has learned `JOIN` wins comfortably, as with the other guardians. The aimer ends in a stalemate rather than a loss. The twins' narrated casts all carry the first twin's name, because they share one caster in the casting contract.

## In the window
`python main.py --start twins` opens the story at the Archive of Twins (intro dialogue, then the battle).
- `engine/twin_scene.py`: the Archive backdrop, the Quill and Ink sprites (drawn in code, like the Knight), a golden chain between them
  (the key that binds them: it goes grey and dashed when one has fallen and flares during a restore), and `TwinScene`,
  a `BattleScene` with two HP panels, a shared MP readout, a bolt and flash for each twin, and the restore beat.
- The orb over each head shows the element dealt this round; it changes when the elements are dealt again. It only shows the
  element, never the weakness: Ada still has to `SELECT` it.
- Each twin has its own steering body, moved by the plan's movement orders (the leader charges, the partner shadows it, the
  living twin walks to the fallen one). Movement is looks only.
- Small edits to existing files: `engine/scenes.py` (a `HOME` entry, `next_scene` returns `TwinScene`, an `archive` backdrop in the
  dialogue scene, and "try again" goes through `next_scene`), `main.py` (`--start twins`), `data/dialogue.json`,
  `assets/audio/sounds.json` (music for `twins`) and `ai/roster.py` (`next_guardian` returns None outside the story).
- Tests: `pytest tests/test_twin_scene.py` (9 tests, headless).

## Tests
`pytest tests/test_twins.py`: 40 tests covering the second body, the win rule, weakness dealing, the
`JOIN` contract, restore, their own queries, perception, the mode machine, goals, steering and whole battles.
