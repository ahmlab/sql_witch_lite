"""The guardians of this build, in the order Ada meets them 

Each Guardian bundles what a battle needs: which foe row, Ada's level for the fight, the
brain, the SQL style, the runes the guardian can write and the one it teaches.
A guardian whose spells are missing from foe_spells fails when its brain is built, with
the missing names in the error, instead of misbehaving mid-battle.

STATUS: the Asterisk Slime, Sir Wherewell, the Nested Lich and the tutorial's Training Dummy.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from typing import Callable

from ai.base import RandomBrain
from ai.archivist_style import TWIN_RUNES, TWIN_SIGNATURE, render_archivists
from ai.archivists import ACTION_SPELLS as TWIN_ACTIONS, PairBrain
from ai.dummy import DummyBrain, render_dummy
from ai.fsm import SlimeBrain, slime_legal_intents
from ai.knight import ACTION_SPELLS, KnightBrain, knight_legal_intents
from ai.lich import (ACTION_SPELLS as LICH_SPELLS, LichBrain, lich_legal_intents,
                     shift_shell)
from ai.pair import make_pair
from ai.styles import (KNIGHT_RUNES, KNIGHT_SIGNATURE, LICH_RUNES, LICH_SIGNATURE,
                       SLIME_RUNES, SLIME_SIGNATURE, render_knight, render_lich,
                       render_slime)

SLIME_ID, KNIGHT_ID, LICH_ID = 1, 2, 6      # 4 and 5 are the Twin Archivists


@dataclass(frozen=True)
class Guardian:
    key: str
    foe_id: int
    level: int                                   # Ada's level in this fight (data/levels.csv)
    runes: frozenset[str]                        # what the guardian can write
    signature: str                               # the rune the Invitation hands to Ada
    ada_runes: frozenset[str]                    # what Ada already knows when it starts
    style: Callable
    make_brain: Callable                         # (sqlite connection) -> brain
    # Optional: something that happens at the end of every round (the Lich changes shell).
    # It is called with (battle state, sqlite connection, the battle's random generator).
    round_hook: Callable | None = None
    world: Callable | None = None                # (seed) -> a world of its own, e.g. the Twins' second body
    extra_foe_ids: tuple = ()                    # more foe rows that join the fight (the second twin)


def _slime_costs(conn, foe_id: int = SLIME_ID) -> dict[str, int]:
    cheapest = conn.execute("SELECT MIN(mp_cost) FROM foe_spells WHERE foe_id = ?",
                            (foe_id,)).fetchone()[0]
    if cheapest is None:
        raise ValueError(f"the Slime (foe_id {foe_id}) has no spells in foe_spells")
    return {"splat": cheapest, "careful": cheapest}


def _knight_costs(conn, foe_id: int = KNIGHT_ID) -> dict[str, int]:
    costs, missing = {}, []
    for action, spell in ACTION_SPELLS.items():
        row = conn.execute("SELECT mp_cost FROM foe_spells WHERE foe_id = ? AND name = ?",
                           (foe_id, spell)).fetchone()
        if row is None or row[0] is None:
            missing.append(spell)
        else:
            costs[action] = row[0]
    if missing:
        raise ValueError(f"Sir Wherewell (foe_id {foe_id}) is missing spells in foe_spells: "
                         f"{', '.join(missing)}")
    return costs


def _lich_costs(conn, foe_id: int = LICH_ID) -> dict[str, int]:
    costs, missing = {}, []
    for action, spell in LICH_SPELLS.items():
        row = conn.execute("SELECT mp_cost FROM foe_spells WHERE foe_id = ? AND name = ?",
                           (foe_id, spell)).fetchone()
        if row is None or row[0] is None:
            missing.append(spell)
        else:
            costs[action] = row[0]
    if missing:
        raise ValueError(f"the Nested Lich (foe_id {foe_id}) is missing spells in foe_spells: "
                         f"{', '.join(missing)}")
    return costs


def _slime_brain(conn) -> SlimeBrain:
    return SlimeBrain(_slime_costs(conn))


def _pair_brain(conn):
    # An action's cost is the sum of the spells it casts (a volley is two rows of one query).
    costs = {}
    for action, spells in TWIN_ACTIONS.items():
        rows = [conn.execute("SELECT mp_cost FROM foe_spells WHERE foe_id = 4 AND name = ?",
                             (spell,)).fetchone() for spell in spells]
        if all(rows):
            costs[action] = sum(row[0] for row in rows)
    return PairBrain(costs)


def _knight_brain(conn) -> KnightBrain:
    return KnightBrain(_knight_costs(conn))


def _lich_brain(conn) -> LichBrain:
    return LichBrain(_lich_costs(conn))


def baseline_brain(key: str, conn) -> RandomBrain:
    """The RandomBrain baseline for a guardian, with the same MP rule and real costs as its
    real brain, so the comparison is fair."""
    match key:
        case "slime":
            return RandomBrain(partial(slime_legal_intents, costs=_slime_costs(conn)))
        case "knight":
            return RandomBrain(partial(knight_legal_intents, costs=_knight_costs(conn)))
        case "lich":
            return RandomBrain(partial(lich_legal_intents, costs=_lich_costs(conn)))
        case _:
            raise ValueError(f"no baseline for guardian {key!r}")


GUARDIANS = {
    "slime": Guardian("slime", SLIME_ID, 1, frozenset(SLIME_RUNES), SLIME_SIGNATURE,
                      frozenset(), render_slime, _slime_brain),
    "knight": Guardian("knight", KNIGHT_ID, 2, frozenset(KNIGHT_RUNES), KNIGHT_SIGNATURE,
                       frozenset({"LIMIT"}), render_knight, _knight_brain),
    # The Twin Archivists: Ada arrives at level 4 knowing LIMIT, WHERE and ORDER BY, and learns
    # JOIN from their first query.
    "twins": Guardian("twins", 4, 4, frozenset(TWIN_RUNES), TWIN_SIGNATURE,
                      frozenset({"LIMIT", "WHERE", "ORDER BY"}), render_archivists,
                      _pair_brain, world=make_pair, extra_foe_ids=(5,)),
    # The Nested Lich is the last fight: Ada is level 5 and already knows JOIN from the twins.
    "lich": Guardian("lich", LICH_ID, 5, frozenset(LICH_RUNES), LICH_SIGNATURE,
                     frozenset({"LIMIT", "WHERE", "ORDER BY", "JOIN"}), render_lich, _lich_brain,
                     round_hook=shift_shell),
    # The tutorial
    "dummy": Guardian("dummy", 3, 1, frozenset(), "", frozenset(), render_dummy,
                      lambda conn: DummyBrain()),
}
ORDER = ["slime", "knight", "twins", "lich"]                 # the story's fights; the dummy is not one of them


def next_guardian(key: str) -> str | None:
    if key not in ORDER:                       # a guardian outside the story ends the build
        return None
    i = ORDER.index(key)
    return ORDER[i + 1] if i + 1 < len(ORDER) else None
