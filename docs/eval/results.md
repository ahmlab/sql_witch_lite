# Evaluation: Count Aggregor and NULL (300 seeded battles per row)

## Count Aggregor (behaviour tree + fuzzy logic)

| Guardian | Player | Ada wins | Ada loses | Rounds | Ada HP left | Move entropy (bits) | Distinct openings | ms/turn |
|---|---|---|---|---|---|---|---|---|
| count | brute | 0% | 100% | 5.1 | 0 | 1.53 | 27 | 0.65 |
| count | joiner | 0% | 100% | 5.1 | 0 | 0.72 | 1 | 0.57 |
| count | grouper | 89% | 2% | 9.9 | 62 | 2.72 | 11 | 0.55 |
| count | expert | 100% | 0% | 10.2 | 63 | 2.65 | 17 | 0.56 |

Moves against the expert: summon 30%, bolt 22%, feed 13%, muster 12%, roll_call 10%, rally 9%, ward 3%, swarm 2%

## NULL (tell reading + GOAP planner + Monte Carlo lookahead, no learning)

| Guardian | Player | Ada wins | Ada loses | Rounds | Ada HP left | Move entropy (bits) | Distinct openings | ms/turn | accuracy |
|---|---|---|---|---|---|---|---|---|---|
| null | blind | 0% | 100% | 7.2 | 0 | 0.99 | 1 | 0.70 | 100% |
| null | repetitive | 12% | 26% | 20.6 | 42 | 1.65 | 4 | 0.85 | 49% |
| null | alternating | 88% | 12% | 7.7 | 48 | 1.95 | 4 | 0.78 | 34% |
| null | varied | 89% | 11% | 7.6 | 50 | 1.98 | 5 | 0.71 | 18% |

`accuracy`: how often NULL's top prediction of Ada's next technique was right.

## Ablations

The same players against weaker versions of each brain. A real brain should beat the random baseline, and NULL should be stronger with each of its parts than without it.

| Guardian | Player | Ada wins | Ada loses | Rounds | Ada HP left | Move entropy (bits) | Distinct openings | ms/turn | accuracy |
|---|---|---|---|---|---|---|---|---|---|
| count | expert | 100% | 0% | 10.2 | 63 | 2.65 | 17 | 0.56 |  |
| count (random baseline) | expert | 100% | 0% | 5.6 | 85 | 3.17 | 292 | 0.38 |  |
| count | grouper | 89% | 2% | 9.9 | 62 | 2.72 | 11 | 0.55 |  |
| count (random baseline) | grouper | 99% | 0% | 5.8 | 86 | 3.17 | 295 | 0.36 |  |
| null | repetitive | 12% | 26% | 20.6 | 42 | 1.65 | 4 | 0.85 | 49% |
| null (random baseline) | repetitive | 52% | 3% | 14.6 | 68 | 2.81 | 282 | 0.36 |  |
| null (no tell reading) | repetitive | 88% | 12% | 7.7 | 49 | 1.95 | 4 | 0.73 | 0% |
| null | varied | 89% | 11% | 7.6 | 50 | 1.98 | 5 | 0.75 | 18% |
| null (no GOAP planner) | varied | 100% | 0% | 6.4 | 72 | 1.82 | 13 | 0.63 | 20% |
| null (no lookahead) | varied | 96% | 4% | 8.4 | 51 | 1.88 | 5 | 0.56 | 19% |

- NULL prediction accuracy by guess vs repetitive: 1: 100%, 2: 100%, 3: 96%, 4: 90%, 5: 7%, 6: 7%, 7: 20%, 8: 9%, 9: 14%, 10: 56%
- NULL prediction accuracy by guess vs alternating: 1: 0%, 2: 0%, 3: 89%, 4: 52%, 5: 50%, 6: 11%, 7: 18%, 8: 22%, 9: 0%, 10: 0%
- NULL prediction accuracy by guess vs varied: 1: 19%, 2: 16%, 3: 19%, 4: 16%, 5: 26%, 6: 10%, 7: 14%, 8: 12%, 9: 0%, 10: 0%
