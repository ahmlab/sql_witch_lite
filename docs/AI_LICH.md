# The Nested Lich: how he thinks

Last fight of the story (after the Asterisk Slime, Sir Wherewell and the Twin Archivists). He teaches **SUBQUERY**:
a `SELECT` inside brackets that runs first and feeds the big query. No machine learning:
every decision is a hand-written rule, the only randomness is the battle's seeded
`random.Random`. Press **F1** in the game (or type `:why` in the terminal) to see his reasoning.

## The idea in one minute

- He hides in layers: a **Veil of Layers** (a Ward of Relevance: only super-effective spells
  pass) and a **Bone Ward** (a flat shield), and he can heal himself with **Life Siphon**.
- At the end of **every round he puts on a new shell**: his element and weakness change
  (Shadow/Light, Frost/Fire, Fire/Tide). What Ada read last round is old news.
- Every query he writes has a **query inside it**, so his first cast is the Invitation that
  teaches SUBQUERY. The same trick helps Ada:

```sql
SELECT name FROM spells
WHERE kind = 'attack'
  AND element = (SELECT weakness FROM enemies WHERE id = 6)
  AND power = (SELECT MAX(power) FROM spells
               WHERE kind = 'attack'
                 AND element = (SELECT weakness FROM enemies WHERE id = 6)
                 AND mp_cost <= (SELECT mp FROM witch))
```

One query that looks at his weakness *and* at her own MP and casts the strongest spell she can
pay for. A query inside a query inside a query: that is why he is "nested".

## Which concepts he uses (and which he does not)

| Requirement | Where | What he does |
|---|---|---|
| **State machine (match/case)** | `LichBrain.next_mode()` in `ai/lich.py` | Stances: lurking, pressing, besieged, desperate, winded. Below 30% HP he is desperate; without MP he is winded; once Ada hits his weakness he is besieged; if she is weak he presses. |
| **Goal-driven behaviour** | `EVALUATORS` and the `_plan_*` functions | Six goals: execute, nest, siphon, press, bone, catch_breath. Each is a plan made of smaller goals; `nest` is a plan **inside** a plan (go home, then `layers` = veil, then Bone Ward). A goal he cannot pay for fails and he replans. |
| **Perception** | `ai/perception.py` (shared) | He sees both HP bars, MP and wards, what he can afford, and remembers Ada's casts: how hard she hits (threat) and whether she hit his weakness (fades after 3 turns). When she has found his weakness the veil is worth less to him (super-effective spells go through it anyway). |
| **Steering behaviours** | `Movement` orders in each plan, run by `ai/steering.py` | He arrives at the front to attack, arrives home to build layers, pursues Ada to finish her, evades when besieged or to heal, wanders (floats) while waiting. |
| Procedural generation | `shift_shell()` | Only a small version: a seeded random new shell every round. |
| Navigation | not used | The battle has no maze or map, so it would be forced. |

## One turn, step by step

1. **Perceive**: `Perception.sense(state)` builds a `Percept` (HP ratios, MP, wards, what he can afford, threat, weakness memory).
2. **Change stance**: `next_mode()` is a `match` on the current stance, with guards on the Percept.
3. **Think**: each evaluator scores its goal, the stance multiplies it (`STANCE_BIAS`), a random factor of 0.85 to 1.15 is applied, and a plan he just used is worth 0.55 times as much if he picks it again in a row. A running plan is kept unless another is 25% better.
4. **Act**: the plan's next subgoal. Moving subgoals only set a `Movement`; an action subgoal gives the `Intent` (for example `heavy`).
5. **Express**: `render_lich()` in `ai/styles.py` writes the intent as SQL, for example:
   `SELECT name FROM foe_spells WHERE power = (SELECT MAX(power) FROM foe_spells WHERE power < 30)`
   which returns exactly one row (Grave Chill). The intent is then thrown away: only the executed query can hurt anyone.
6. **End of round**: `shift_shell()` gives him a new element and weakness and updates the `enemies` table, so queries read the truth.

## Files

| File | What |
|---|---|
| `ai/lich.py` (new) | the brain: stances, goals, plans, `shift_shell()` |
| `ai/styles.py` | `render_lich()` and `LICH_PICKS` (added at the end) |
| `ai/roster.py` | `lich` entry (foe id 6, level 5), costs from `foe_spells`, baseline brain, `ORDER = [slime, knight, twins, lich]`, new optional `round_hook` field |
| `magic/battle.py` | 3 lines: calls the guardian's `round_hook` at the end of a round (only the Lich has one) |
| `engine/scenery.py` | `draw_crypt()` and `draw_lich()` (placeholder art made of shapes) |
| `engine/scenes.py` | crypt backdrop in dialogue, Lich in battle, "A new shell!" beat, `HOME["lich"]` |
| `data/*.csv`, `dialogue.json`, `guide.json`, `sounds.json` | foe row 6, his 6 spells, story lines, SUBQUERY in the guide, music |
| `sim/lich_eval.py`, `tests/test_lich.py` | evaluation and tests |

## Evaluation

`python -m sim.lich_eval` (300 seeded battles per player; the Lich opens every round; Ada is level 5 with 120 HP, 80 MP and 12 MP back each round; the Lich has 620 HP, knowing LIMIT, WHERE, ORDER BY and JOIN, and SUBQUERY after his first cast):

| Player | Ada wins | Rounds | Ada HP left |
|---|---|---|---|
| Blind: `SELECT name FROM spells LIMIT 1` every turn | 0% | 6.6 | 0 |
| Looks at his weakness and types the element by hand (no subquery) | 100% | 10.8 | 58.5 |
| Uses the subquery query above | 100% | 6.9 | 111.8 |

Same players against a `RandomBrain` Lich (any spell he can pay for): blind 0%, by hand 90%, subquery 96%.

What this shows, honestly:
- He beats the player who never reads his weakness and loses to the ones who do.
- A subquery is not *required* to win: the by-hand player also wins. But the subquery player also
  picks the strongest spell it can pay for in the same query, so it wins faster and loses almost no HP.
  Typing last round's element is what fails (the spell bounces off his veil).
- Against a random Lich the good players win slightly less often (93-96%) than against the real one (100%),
  because the real brain spends turns on layers and healing instead of attacking. That is a weakness of this design.

## Limits

- The art is placeholder shapes, like the Slime and the Knight.
- If Ada has not seen his first cast she cannot write SUBQUERY yet (the Invitation comes first), the same as WHERE for the Knight.
- 4 tests in the repo were already failing before this change (`test_beta_feedback` Knight lines, two in `test_brains`, `test_tutorial_scene` intro). They are not about the Lich.

## Help for the player

Both late bosses teach a query the player has to write, so the editor coaches it
(`coached_step` in `engine/textinput.py`). Once the boss's rune is unlocked (JOIN for the twins,
SUBQUERY for the Lich), typing `SELECT` and pressing TAB offers the lesson query one piece at a
time. The Lich query ends with `AND mp_cost <= 15 ORDER BY power DESC LIMIT 1`: without the cost
cap the player picks Judgment Ray (32 MP), runs out of mana and stalls. The F3 guide has the same
queries as examples, and the intro dialogue and the unlock message tell the player about TAB.
Ada's mana regeneration at level 5 is 12 (it was 9); only this fight uses level 5.
