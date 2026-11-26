"""Style grammars: each foe writes its intent as SQL

After rendering, the intent is discarded. The query then goes through magic.cast.resolve()
exactly like Ada's, so whatever the brain "wanted", only the executed result can hurt anyone.

A style only translates: it never changes what the brain decided. Rules such as the
Slime's teaching guarantee are decisions, so they live in the brain (ai/fsm.py) and this
module only says when they are due (signature_due).

STATUS: the Slime's sloppy SELECT * and Sir Wherewell's WHERE filters.
"""

from __future__ import annotations

from ai.base import Intent
from magic import guard
from magic.rules import BattleState

SLIME_RUNES = {"WHERE", "LIMIT"}        # the keywords the Slime is able to write
SLIME_SIGNATURE = "LIMIT"               # the rune the Invitation hands to Ada (design doc 3.6)
GUARANTEE_TURN = 2                      # the signature appears by the foe's 2nd turn

SLIME_ATTACK = "SELECT * FROM foe_spells WHERE foe_id = {foe_id}"
SLIME_CAREFUL = SLIME_ATTACK + " LIMIT 2"
# Wobbling and panting are still real queries: SELECT * on tables with no spell in them,
# so they cast nothing. That is how "regain MP" and "skip turn" happen without cheating.
SLIME_LOOKS = {
    "wobble": "SELECT * FROM enemies WHERE id = {foe_id}",
    "exhausted": "SELECT * FROM witch WHERE hp > 0",
    "rest": "SELECT * FROM enemies WHERE id = {foe_id}",   # GuardianBrain's REST fallback
}


def book_uses(state: BattleState, rune: str) -> bool:
    """Has this rune already been printed in the foe's book?"""
    return any(rune in guard.runes_used(guard.parse_one_select(sql)) for sql in state.foe_book)


def signature_due(state: BattleState, turn: int) -> bool:
    """Teaching guarantee: must the Slime write LIMIT this turn? True from its 2nd turn on
    (`turn` counts its own turns from 1) for as long as LIMIT is not in its book."""
    return turn >= GUARANTEE_TURN and not book_uses(state, SLIME_SIGNATURE)


def render_slime(intent: Intent, state: BattleState, turn: int) -> str:
    """Write the Slime's intent as SQL. 'turn' is the Slime's own turn count, starting at 1"""
    foe_id = state.foe_id
    if intent.kind == "scry":
        return SLIME_LOOKS[intent.action].format(foe_id=foe_id)
    if intent.params.get("limit"):
        return SLIME_ATTACK.format(foe_id=foe_id) + f" LIMIT {intent.params['limit']}"
    return SLIME_ATTACK.format(foe_id=foe_id)


# Sir Wherewell

KNIGHT_RUNES = {"WHERE"}                # AND, OR and comparisons belong to the WHERE rune
KNIGHT_SIGNATURE = "WHERE"

# One precise filter per intent: each one matches exactly one row of his book. They are
# kept short on purpose, so every query fits his book in three lines and can be copied as is.
KNIGHT_FILTERS = {
    "strike":    "kind = 'attack' AND power < 20",
    "heavy":     "kind = 'attack' AND power > 20 AND power < 30",
    "finisher":  "kind = 'attack' AND power > 30",
    "relevance": "kind = 'relevance'",
    "guard":     "kind = 'ward'",
    "dispel":    "kind = 'dispel'",
}


def render_knight(intent: Intent, state: BattleState, turn: int) -> str:
    """Sir Wherewell never casts without a filter. WHERE is in every query,
    so his very first cast is the Invitation."""
    foe_id = state.foe_id
    if intent.action not in KNIGHT_FILTERS:      # resting: he studies his own row
        return f"SELECT name, hp, mp FROM enemies WHERE id = {foe_id}"
    return (f"SELECT name FROM foe_spells WHERE foe_id = {foe_id} "
            f"AND {KNIGHT_FILTERS[intent.action]}")


# The Nested Lich

LICH_RUNES = {"WHERE", "SUBQUERY"}      # he writes a WHERE with a query inside it
LICH_SIGNATURE = "SUBQUERY"             # the rune the Invitation hands to Ada

# Every query has another SELECT inside the brackets (a subquery), so his very first cast
# is the Invitation. Each one still returns exactly one row of his book. The battle's
# foe_spells table only holds the guardian of the fight, so no foe_id is needed here (and
# the queries stay short enough for the foe's book on the screen).
LICH_PICKS = {
    # the weakest attack, the strongest attack under 30, the strongest attack of all
    "strike":   "power = (SELECT MIN(power) FROM foe_spells WHERE power > 0)",
    "heavy":    "power = (SELECT MAX(power) FROM foe_spells WHERE power < 30)",
    "finisher": "power = (SELECT MAX(power) FROM foe_spells)",
    # the other spells: look the name up by its kind
    "veil":     "name = (SELECT name FROM foe_spells WHERE kind = 'relevance')",
    "bone":     "name = (SELECT name FROM foe_spells WHERE kind = 'ward')",
    "siphon":   "name = (SELECT name FROM foe_spells WHERE kind = 'heal')",
}


def render_lich(intent: Intent, state: BattleState, turn: int) -> str:
    """The Lich never casts without a subquery. When he rests he only looks at his own row
    (also with a subquery), so even a resting turn teaches SUBQUERY."""
    if intent.action not in LICH_PICKS:
        return (f"SELECT name, hp FROM enemies WHERE id = "
                f"(SELECT MAX(id) FROM enemies WHERE id = {state.foe_id})")
    return "SELECT name FROM foe_spells WHERE " + LICH_PICKS[intent.action]


# ------------------------------------------------------------------ Count Aggregor

COUNT_RUNES = {"WHERE", "GROUP BY", "HAVING", "SUBQUERY", "IS NULL", "DISTINCT"}
COUNT_SIGNATURE = "GROUP BY"
COUNT_ALSO_TEACHES = frozenset({"HAVING", "DISTINCT"})

COUNT_KINDS = {"bolt": "attack", "summon": "summon", "muster": "muster", "rally": "rally",
               "swarm": "swarm", "feed": "feed", "ward": "ward"}
_BATS = "(SELECT COUNT(*) FROM enemies WHERE squad IS NOT NULL)"
COUNT_GATES = {
    "bolt": "COUNT(*) = 1",
    "summon": f"{_BATS} < 12",
    "muster": f"{_BATS} < 12",
    "rally": "(SELECT COUNT(DISTINCT squad) FROM enemies WHERE squad IS NOT NULL) > 1",
    "swarm": f"{_BATS} >= 3",
    "feed": "(SELECT SUM(hp) FROM enemies WHERE squad IS NOT NULL) > 0",
    "ward": "MIN(mp_cost) <= (SELECT mp FROM enemies WHERE id = {foe_id})",
}
COUNT_TALLY = ("SELECT squad, COUNT(*) AS bats, SUM(hp) AS hp FROM enemies "
               "WHERE squad IS NOT NULL GROUP BY squad HAVING COUNT(*) >= 3")


def render_count(intent: Intent, state: BattleState, turn: int) -> str:
    """Every Count query has GROUP BY, and a HAVING that only lets the spell through when it makes sense."""
    foe_id = state.foe_id
    kind = COUNT_KINDS.get(intent.action)
    if kind is None:
        return COUNT_TALLY
    gate = COUNT_GATES[intent.action].format(foe_id=foe_id)
    return (f"SELECT name FROM foe_spells WHERE foe_id = {foe_id} AND kind = '{kind}' "
            f"GROUP BY name HAVING {gate}")


# ------------------------------------------------------------------ NULL

NULL_RUNES = {"WHERE", "LIMIT", "JOIN", "GROUP BY", "HAVING", "DISTINCT", "SUBQUERY",
              "IS NULL", "COALESCE", "ORDER BY"}
NULL_SIGNATURE = "IS NULL"
NULL_ALSO_TEACHES = frozenset({"COALESCE"})
NULL_KINDS = {"strike": "attack", "echo": "echo", "doubt": "doubt", "shift": "shift",
              "fade": "fade", "heal": "heal"}
NULL_OFFENSIVE = {"strike", "echo", "doubt"}
NULL_LOOK = "SELECT name, hp, element, weakness FROM enemies WHERE hp IS NULL"


def null_style(state: BattleState) -> str:
    """The rune Ada uses most (out of the ones NULL can copy)."""
    counts: dict[str, int] = {}
    for cast in state.ada_casts:
        if not cast.scry:
            for rune in cast.runes:
                counts[rune] = counts.get(rune, 0) + 1
    for rune, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        if rune in ("JOIN", "GROUP BY", "LIMIT", "WHERE"):
            return rune
    return "WHERE"


def render_null(intent: Intent, state: BattleState, turn: int) -> str:
    """NULL copies Ada's favourite style, and every query tests for NULL (so it teaches IS NULL)."""
    foe_id = state.foe_id
    kind = NULL_KINDS.get(intent.action)
    if kind is None:
        return NULL_LOOK
    style = null_style(state)
    spell = f"foe_id = {foe_id} AND COALESCE(kind, 'nothing') = '{kind}'"
    if style == "JOIN" and intent.action in NULL_OFFENSIVE:
        return (f"SELECT f.name, w.name FROM foe_spells AS f JOIN witch AS w ON w.hp > 0 "
                f"WHERE f.foe_id = {foe_id} AND COALESCE(f.kind, 'nothing') = '{kind}' "
                f"AND f.power IS NOT NULL")
    if style == "GROUP BY":
        return f"SELECT name FROM foe_spells WHERE {spell} AND power IS NOT NULL GROUP BY name"
    if style == "LIMIT":
        return f"SELECT name FROM foe_spells WHERE {spell} AND mp_cost IS NOT NULL LIMIT 1"
    return (f"SELECT name FROM foe_spells WHERE {spell} "
            f"AND (SELECT hp FROM enemies WHERE id = {foe_id}) IS NULL")
