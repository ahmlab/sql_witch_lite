"""The Twin Archivists' voice: every query they write contains a JOIN (design doc 5.6).

A JOIN is how a query names its target: the row it returns holds a spell AND the combatant to
cast it at. So their very first query is the Invitation that teaches Ada the rune JOIN, and
Ada's counter-play is the same trick: JOIN spells to enemies on the weakness column and every
row arrives with its own target.
After rendering, the intent is discarded; only the executed result can hurt anyone.
Never imports pygame.

STATUS: attack, restore, mend, guard and rest queries, all with JOIN.
"""

from __future__ import annotations

from ai.archivists import ACTION_SPELLS
from ai.base import Intent
from magic.rules import BattleState

TWIN_RUNES = {"WHERE", "JOIN"}          # the keywords the twins can write
TWIN_SIGNATURE = "JOIN"                 # the rune the Invitation hands to Ada


def _twin_name(state: BattleState, who: str) -> str:
    return state.foe.name if who == "quill" else state.twin.name


def render_archivists(intent: Intent, state: BattleState, turn: int) -> str:
    """Write the pair's joint intent as one query. `turn` is their own turn count."""
    foe_id = state.foe_id
    if intent.kind == "scry":
        # Resting is still a real JOIN: read our own rows beside Ada's, cast nothing.
        return (f"SELECT e.name, e.hp, w.name FROM enemies AS e JOIN witch AS w ON w.hp > 0 "
                f"WHERE e.id IN ({foe_id}, {foe_id + 1})")
    if intent.action in ("strike", "volley", "barrage"):
        spells = ", ".join(f"'{s}'" for s in ACTION_SPELLS[intent.action])
        return (f"SELECT f.name, w.name FROM foe_spells AS f JOIN witch AS w ON w.hp > 0 "
                f"WHERE f.foe_id = {foe_id} AND f.name IN ({spells})")
    if intent.action == "restore":
        # They JOIN to find each other: the fallen twin's name lands in the row.
        return (f"SELECT f.name, e.name FROM foe_spells AS f JOIN enemies AS e ON e.hp = 0 "
                f"WHERE f.foe_id = {foe_id} AND f.kind = 'restore'")
    kind = "restore" if intent.action == "mend" else "ward"
    name = _twin_name(state, intent.target or "quill")
    return (f"SELECT f.name, e.name FROM foe_spells AS f JOIN enemies AS e ON e.name = '{name}' "
            f"WHERE f.foe_id = {foe_id} AND f.kind = '{kind}'")
