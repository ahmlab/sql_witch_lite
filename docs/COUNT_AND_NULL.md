# Count Aggregor and NULL (Ifrah Nabi)

Welcome dear witches and grandmaster. In the story Count comes after the Twin Archivists and
NULL is the final boss. This is the order: Slime, Knight, Twins, Count, Lich, NULL. They use
the same turn loop as the other guardians (`ai/guardian.py`). Like the rest of the game they use
**no machine learning**. Every decision is a handwritten rule. `random.Random` is used so that
every fight plays from its seed. To play them use `python main.py --start count` or
`python main.py --start null`. You can press **F1** during the fight to see how it is working.

## Count Aggregor

The Count hides behind squads of Tally Bats. They are rows in the `enemies` table with a `squad`
column. While any squad has 3 or more bats nothing can hurt him. A JOIN of spells with all his
bats gives one row per bat, so the page overflows and Ada wastes mana. The answer is
`GROUP BY e.squad HAVING COUNT(*) >= 3`: one row per squad, and only the squads that are
actually shielding him. Every query the Count writes uses GROUP BY and HAVING, so the player sees
both runes before using them.

Each turn the Count:

1. Perceives both sides' HP and MP and his swarm.
2. Ledger: he counts Ada too as to which runes she uses, how often she is grouping, overflows,
   and how many bats each cast kills. If she groups he goes audited and summons many small
   squads. If she doesn't do so he forms the bats into big squads that overflow her JOINs.
3. Changes stance with a `match`/`case` state machine.
4. Fuzzy logic: we have three fuzzy inputs like swarm few/some/lots, Ada's HP low/ok/high, his HP
   low/ok/high and nine rules like *IF swarm is lots AND Ada is low THEN reckless* give one
   number, for example his aggression.
5. There is an AI director (`ai/director.py`). It multiplies that aggression by its intensity,
   so it increases more when Ada is winning and vice versa when she's struggling.
6. Runs a behaviour tree (`ai/btree.py`) from the root every turn.
7. Every bat is an agent with its own state machine (hover, dive, flee, regroup), and each squad
   flies as a boids flock using separation, alignment and cohesion (`ai/swarm.py`).
8. Barks: he comments on what he noticed, e.g. *"You GROUP BY? Then I split my ranks."*

## NULL, the Voice of Doubt

NULL's hp, element and weakness are NULL in the table, so `=` never matches it and `hp > 0`
filters it out. Its Veil of Doubt only lets a spell through if the query reads `enemies` and uses
`IS NULL` or `COALESCE`. These are its moves:

- Fade to Grey
- Shift of Nothing: it changes its element.
- Whisper of Doubt: it drains Ada's MP.
- Echo of Doubt: it throws back part of her last hit.
- Empty Strike: damage.
- Hollow Mend: it heals.

A player who repeats the same query gets faded out, hence only a player with a diverse moveset is
able to survive. NULL adapts to the player but it also never learns. It reads the casts it
remembers with fixed rules; nothing is trained. Each turn it:

1. Watches: each of Ada's casts becomes a technique signature (its runes, e.g.
   `COALESCE+IS NULL+JOIN+WHERE`) in a fading memory.
2. Is able to read her tell (`ai/patterns.py`). A `match` over her recent casts finds the first
   rule that fits: a streak (the same thing 2, 3 or 4+ times), a swing (A B A B), a cycle
   (A B C A B C), or otherwise her habit. Each rule already has a decided confidence. The
   prediction derived is then sorted into a kind, for instance blind (cannot touch NULL),
   repeat (what last hurt it), fixed or adaptive.
3. Changes stance with `match`/`case` by listening and mirroring.
4. Plans ahead with GOAP. I have used Goal Oriented Action Planning, the technique
   (`ai/goap.py`). The world is a set of true and false facts: her trick is blocked, NULL is
   hidden, Ada is out of MP, Ada is hurt, Ada is down, and so on. Every move is an action with
   preconditions, effects and a cost worked out from this turn.

   ```
   tell: streak 3 -> COALESCE+IS NULL+JOIN+WHERE 75%
   goap: bring her down: fade her trick > wear her down > echo the end
         (cost 4.8, 9 states searched)
   says: "I already know your next COALESCE."
   ```

5. Looks ahead with a Monte Carlo simulation.
6. Chooses on the basis of utility. It mixes the lookahead with a fixed table of which move
   counters which kind of cast.
7. Barks: *"You will COALESCE again. I know it."* or *"...I didn't see that coming."*

## Evaluation

`python -m sim.evaluate --n 300 --plots` plays 300 seeded battles per row between scripted
players and the bosses, through the real game (real SQL, rune checks, the Rule of the Page).
Full tables: `docs/eval/results.md`.

| Boss | Player | Ada wins |
|---|---|---|
| Count | ignores the bats, or JOINs without GROUP BY | 0% |
| Count | GROUP BY without HAVING | 89% |
| Count | GROUP BY + HAVING | 100% |
| NULL | never uses IS NULL | 0% |
| NULL | the same good query every turn | 12% |
| NULL | never the same way twice | 89% |

Each boss beats the player who ignores its lesson and loses to the one who uses it. The 48 tests
in `tests/test_count_and_null.py` check this on fixed seeds.

To check each AI part, I switched parts off one at a time (an ablation):

- Without tell reading, the repetitive player's wins go from 12% to 88%.
- Without the GOAP planner, a player with a diverse moveset never loses (a 100% win rate), and
  ends with 22 more HP.
- Without the lookahead, the player ends up winning 96% instead of 89%.
- Against a Count that picks randomly, almost all the fights end almost twice as fast and Ada
  keeps 24 more HP.
