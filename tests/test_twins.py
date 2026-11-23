"""The Twin Archivists: the second body, the restore link, the weakness re-roll, perception,
the mode machine, goals, steering, and whole battles against scripted players."""

import random
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

from ai.archivist_style import render_archivists
from ai.archivists import (ACTION_SPELLS, DEFAULT_COSTS, PairBrain, PairPerception,
                           twin_legal_intents)
from ai.base import Intent, RandomBrain
from ai.pair import FIELD_H, FIELD_W, NATURAL, Pair, attackers_x2
from ai.steering import Movement
from magic import rules
from magic.battle import Battle
from magic.cast import resolve, sync_state
from magic.rules import CastMemory
from sim.twin_eval import JOIN_CHEAP, aimer, fight, joiner, novice

ROOT = Path(__file__).resolve().parent.parent
JOIN = JOIN_CHEAP.format(cost=3)


def twin_battle(seed=1) -> Battle:
    return Battle(seed=seed, guardian="twins")


def after_opening(seed=1) -> Battle:
    battle = twin_battle(seed)
    battle.foe_act()                       # the twins open: Ada reads a JOIN
    return battle


# ------------------------------------------------------------------ the second body

def test_the_second_twin_is_a_real_combatant_with_its_own_hp_and_a_shared_pool():
    battle = twin_battle()
    state = battle.state
    assert state.twin.name == "Archivist Ink" and state.foe.name == "Archivist Quill"
    assert state.twin.hp == state.twin.max_hp == 90
    assert state.twin.mp == 0 and state.foe.mp == 40          # one pool, held by the first twin
    rows = battle.conn.execute("SELECT name, hp, mp FROM enemies ORDER BY id").fetchall()
    assert rows == [("Archivist Quill", 90, 40), ("Archivist Ink", 90, 40)]


def test_other_fights_have_no_twin():
    for key in ("slime", "knight"):
        battle = Battle(seed=2, guardian=key)
        assert battle.state.twin is None and battle.state.pair is None
        battle.foe_act()


def test_the_pair_only_loses_when_both_twins_are_down():
    state = twin_battle().state
    state.foe.hp = 0
    assert rules.winner(state) is None
    state.twin.hp = 0
    assert rules.winner(state) == "ada"
    state.foe.hp = 5
    assert rules.winner(state) is None


# ------------------------------------------------------------------ procedural generation

def test_weaknesses_really_beat_the_element_and_are_always_different():
    for seed in range(60):
        battle = twin_battle(seed)
        state, chart = battle.state, battle.chart
        for _ in range(8):
            for twin in (state.foe, state.twin):
                assert twin.element in NATURAL
                assert chart[(twin.weakness, twin.element)] == 2.0
            assert state.foe.weakness != state.twin.weakness
            state.pair.end_of_round(state, chart)


def test_same_seed_deals_the_same_elements_and_different_seeds_differ():
    def deals(seed):
        battle = twin_battle(seed)
        for _ in range(5):
            battle.state.pair.end_of_round(battle.state, battle.chart)
        return battle.state.pair.history
    assert deals(4) == deals(4)
    assert len({str(deals(s)) for s in range(10)}) > 5


def test_every_round_the_weaknesses_are_dealt_again():
    battle = twin_battle(3)
    dealt = {str(battle.state.pair.history[-1])}
    for _ in range(12):
        battle.state.pair.end_of_round(battle.state, battle.chart)
        dealt.add(str(battle.state.pair.history[-1]))
    assert len(dealt) > 4


def test_dealing_never_touches_the_battles_own_random_generator():
    battle = twin_battle(3)
    assert battle.rng.random() == random.Random(3).random()


def test_the_table_always_shows_this_rounds_weakness():
    battle = twin_battle(5)
    for _ in range(4):
        rows = battle.conn.execute("SELECT name, element, weakness FROM enemies ORDER BY id").fetchall()
        assert rows == [(t.name, t.element, t.weakness) for t in (battle.state.foe, battle.state.twin)]
        battle.state.pair.end_of_round(battle.state, battle.chart)
        battle.state.pair.sync(battle.conn, battle.state)


# ------------------------------------------------------------------ the casting contract

def test_a_join_puts_each_twins_name_in_its_row_and_hits_both():
    battle = after_opening()
    state = battle.state
    report = battle.ada_cast(JOIN)
    hit = {c.target: c for c in report.casts}
    assert set(hit) == {state.foe.name, state.twin.name}
    assert all(c.effective == 2.0 for c in hit.values())          # one cheap spell per twin
    assert state.foe.hp < 90 and state.twin.hp < 90


def test_a_spell_with_no_target_in_the_row_only_reaches_the_first_twin():
    battle = after_opening()
    state = battle.state
    battle.ada_cast("SELECT name FROM spells WHERE kind = 'attack' ORDER BY power DESC LIMIT 1")
    assert state.foe.hp < 90 and state.twin.hp == 90


def test_the_other_twin_stands_back_up_if_only_one_fell():
    battle = after_opening()
    state = battle.state
    state.foe.hp = 5
    state.foe.hp = 0                      # Ada's last query felled Quill alone
    state.twin.hp = 60
    sync_state(battle.conn, state)
    battle.ada_cast("SELECT name FROM enemies")        # free looks keep the turn; spend it
    battle.ada_cast("SELECT name FROM enemies")
    battle.ada_cast("SELECT name FROM enemies")
    battle.ada_cast("SELECT name FROM enemies")
    battle.foe_act()
    assert state.foe.hp >= 60                          # Ink restored him


def test_restore_revives_a_fallen_twin_and_costs_shared_mana():
    battle = twin_battle()
    state = battle.state
    state.twin.hp = 0
    state.foe.mp = 20
    sync_state(battle.conn, state)                       # the tables show Ink fallen
    sql = render_archivists(Intent("restore", "ink", "restore"), state, 1)
    report = resolve(battle.conn, state, sql, "foe", battle.rng, battle.chart)
    assert state.twin.hp == 60 and state.foe.mp == 12
    assert any(e[0] == "restore" and e[5] for e in report.events)


def test_restore_with_no_fallen_twin_casts_nothing():
    battle = twin_battle()
    sql = render_archivists(Intent("restore", "ink", "restore"), battle.state, 1)
    report = resolve(battle.conn, battle.state, sql, "foe", battle.rng, battle.chart)
    assert report.scry and not report.casts


def test_both_falling_in_one_query_ends_the_fight_before_any_restore():
    battle = after_opening()
    state = battle.state
    state.foe.hp, state.twin.hp = 20, 20
    battle.ada_cast(JOIN)
    assert battle.winner == "ada" and not state.foe.alive and not state.twin.alive


def test_one_twin_falling_alone_does_not_end_the_fight():
    battle = after_opening()
    state = battle.state
    state.foe.hp, state.twin.hp = 20, 90
    battle.ada_cast(JOIN)
    assert battle.winner is None and not state.foe.alive and state.twin.alive


# ------------------------------------------------------------------ their own book

def test_every_query_they_write_contains_a_join_and_obeys_their_runes():
    for seed in range(6):
        battle = twin_battle(seed)
        for _ in range(20):
            if battle.whose_turn == "over":
                break
            if battle.whose_turn == "ada":
                battle.ada_cast(joiner(battle))
            else:
                turn = battle.foe_act()
                assert "JOIN" in turn.report.runes and turn.report.runes <= {"WHERE", "JOIN"}


def test_the_first_query_hands_ada_the_join_rune():
    battle = twin_battle()
    assert "JOIN" not in battle.state.ada.runes
    turn = battle.foe_act()
    assert turn.invitation == "JOIN" and "JOIN" in battle.state.ada.runes


def test_they_aim_with_a_join_not_with_a_hardcoded_name():
    state = twin_battle().state
    sql = render_archivists(Intent("volley", "Ada", "attack"), state, 1)
    assert "JOIN witch" in sql and "Index Slash" in sql and "Paper Cut" in sql


# ------------------------------------------------------------------ perception

def memory(turn, targets, damage=40):
    return CastMemory(turn, ("JOIN",), ("Fire",), damage, True, 0, False, tuple(targets))


def sensed(battle, perception=None):
    perception = perception or PairPerception(dict(DEFAULT_COSTS))
    return perception.sense(battle.state), perception


def test_perception_reports_each_twin_the_fallen_one_and_the_lead():
    battle = twin_battle()
    battle.state.twin.hp = 30
    p, _ = sensed(battle)
    assert p.quill_ratio == 1.0 and round(p.ink_ratio, 2) == 0.33
    assert p.lead == "quill" and p.weaker == "ink" and p.down == 0 and p.fallen is None
    battle.state.twin.hp = 0
    p, _ = sensed(battle)
    assert p.down == 1 and p.fallen == "ink" and p.lead == "quill" and p.weaker is None


def test_perception_notices_when_one_query_hit_both_twins_and_forgets():
    battle = twin_battle()
    names = (battle.state.foe.name, battle.state.twin.name)
    p, eyes = sensed(battle)
    assert not p.ada_hits_both and p.fresh_unison == 0
    battle.state.ada_casts.append(memory(1, names))
    p, _ = sensed(battle, eyes)
    assert p.ada_hits_both and p.fresh_unison == 1.0
    assert any("BOTH" in line for line in eyes.log)
    battle.state.turn = 5
    p, _ = sensed(battle, eyes)
    assert p.fresh_unison == 0.0


def test_a_cast_that_hits_only_one_twin_is_not_a_unison_hit():
    battle = twin_battle()
    battle.state.ada_casts.append(memory(1, [battle.state.foe.name]))
    p, _ = sensed(battle)
    assert not p.ada_hits_both


def test_perception_sees_the_shared_pool_and_what_it_buys():
    battle = twin_battle()
    battle.state.foe.mp = 6
    p, _ = sensed(battle)
    assert p.my_mp == 6 and p.can("strike") and not p.can("volley")


# ------------------------------------------------------------------ the mode machine

def mode_for(change) -> str:
    battle = twin_battle()
    brain = PairBrain()
    change(battle.state)
    p, _ = sensed(battle, brain.perception)
    return brain.next_mode(p, random.Random(0))


def test_the_mode_follows_the_pairs_health_losses_and_mana():
    assert mode_for(lambda s: None) == "bonded"
    assert mode_for(lambda s: setattr(s.twin, "hp", 0)) == "bereaved"
    assert mode_for(lambda s: (setattr(s.foe, "hp", 10), setattr(s.twin, "hp", 10))) == "desperate"
    assert mode_for(lambda s: setattr(s.foe, "mp", 2)) == "winded"
    names = lambda s: s.ada_casts.append(memory(1, (s.foe.name, s.twin.name)))
    assert mode_for(names) == "pressed"


# ------------------------------------------------------------------ goal-driven behaviour

def decide(battle, seed=0, brain=None):
    brain = brain or PairBrain()
    intent = brain.decide(battle.state, random.Random(seed))
    return brain, intent


def test_a_fallen_twin_is_restored_nearly_every_time():
    battle = twin_battle()
    battle.state.twin.hp = 0
    picks = Counter(decide(battle, s)[1].action for s in range(30))
    assert picks["restore"] >= 28


def test_without_mana_to_restore_they_do_not_try():
    battle = twin_battle()
    battle.state.twin.hp = 0
    battle.state.foe.mp = 6
    assert decide(battle)[1].action != "restore"


def test_a_wounded_living_twin_is_mended_or_guarded_sometimes():
    battle = twin_battle()
    battle.state.twin.hp = 25
    picks = Counter(decide(battle, s)[1].action for s in range(40))
    assert picks["mend"] + picks["guard"] >= 8


def test_with_no_mana_they_rest_and_regain_it():
    battle = twin_battle()
    battle.state.foe.mp = 0
    brain, intent = decide(battle)
    assert intent.kind == "scry" and brain.explain()["mode"].endswith("winded")


def test_a_low_ada_draws_the_big_spell():
    battle = twin_battle()
    battle.state.ada.hp = 30
    picks = Counter(decide(battle, s)[1].action for s in range(40))
    assert picks["barrage"] >= 10


def test_a_plan_that_became_impossible_fails_and_they_replan_in_the_same_turn():
    battle = twin_battle()
    brain = PairBrain()
    brain.decide(battle.state, random.Random(0))
    battle.state.foe.mp = 3
    intent = brain.decide(battle.state, random.Random(0))
    assert intent.kind == "scry" or intent.action == "rest"


def test_repeating_the_same_plan_every_turn_gets_less_attractive():
    assert PairBrain.repeat_penalty < 1.0


# ------------------------------------------------------------------ steering

def test_the_leader_charges_and_the_partner_shadows_it():
    battle = twin_battle()
    brain, _ = decide(battle)
    assert set(brain.movements) == {"quill", "ink"}
    assert brain.movements["quill"] == Movement("arrive", "front")
    assert brain.movements["ink"] == Movement("pursue", "partner")


def test_the_living_twin_walks_to_the_fallen_one_which_stays_put():
    battle = twin_battle()
    battle.state.twin.hp = 0
    brain, intent = decide(battle)
    assert intent.action == "restore"
    assert brain.movements["quill"] == Movement("arrive", "partner")
    assert brain.movements["ink"] == Movement("hold")


def test_the_bodies_walk_to_their_posts_stay_on_the_stage_and_never_overlap():
    battle = twin_battle()
    pair = battle.state.pair
    orders = {"quill": Movement("arrive", "front"), "ink": Movement("pursue", "partner")}
    for _ in range(4):
        pair.obey(orders)
    q, i = pair.bodies["quill"].position, pair.bodies["ink"].position
    assert (q - pair.places("quill")["front"].position).length() < 8
    assert (q - i).length() > 5
    for body in pair.bodies.values():
        assert 0 <= body.position.x <= FIELD_W and 0 <= body.position.y <= FIELD_H


def test_steering_never_changes_a_battle():
    def outcome(steer):
        battle = twin_battle(4)
        if not steer:
            battle.state.pair.obey = lambda movements: None
        for _ in range(60):
            if battle.whose_turn == "over":
                break
            battle.ada_cast(joiner(battle)) if battle.whose_turn == "ada" else battle.foe_act()
        return battle.winner, battle.state.turn, battle.state.ada.hp
    assert outcome(True) == outcome(False)


def test_the_terminal_stage_marks_a_fallen_twin():
    battle = twin_battle()
    battle.state.twin.hp = 0
    assert "x" in battle.state.pair.render(battle.state)[0]


# ------------------------------------------------------------------ whole battles

def test_the_pair_beats_players_who_never_use_join_and_loses_to_one_who_does():
    assert all(not fight(s, novice, max_rounds=30)["win"] for s in range(1, 9))
    assert all(not fight(s, aimer, max_rounds=30)["win"] for s in range(1, 9))
    assert all(fight(s, joiner)["win"] for s in range(1, 9))


def test_the_same_seed_replays_the_same_battle_and_different_seeds_differ():
    def log(seed):
        battle = twin_battle(seed)
        for _ in range(40):
            if battle.whose_turn == "over":
                break
            battle.ada_cast(joiner(battle)) if battle.whose_turn == "ada" else battle.foe_act()
        return battle.conn.execute("SELECT turn, caster, sql FROM query_log").fetchall()
    assert log(3) == log(3)
    assert len({tuple(log(s)) for s in range(1, 8)}) > 1


def test_the_brain_prolongs_the_fight_and_hurts_more_than_a_random_brain():
    smart = [fight(s, joiner) for s in range(1, 41)]
    dumb = [fight(s, joiner, lambda: RandomBrain(twin_legal_intents)) for s in range(1, 41)]
    mean = lambda runs, key: sum(r[key] for r in runs) / len(runs)
    assert mean(smart, "rounds") > mean(dumb, "rounds")
    assert mean(smart, "ada_hp") < mean(dumb, "ada_hp")


def test_every_action_has_a_cost_in_the_roster():
    from ai.roster import GUARDIANS
    brain = GUARDIANS["twins"].make_brain(twin_battle().conn)
    assert set(brain.perception.costs) == set(ACTION_SPELLS)


def test_the_terminal_can_fight_the_twins():
    code = ("import sim.play_cli as c; lines = iter(['SELECT * FROM enemies', ':map', ':why', ':quit']);"
            "c.main(['--seed', '2', '--foe', 'twins'], read=lambda p: next(lines), out=print)")
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True,
                         text=True).stdout
    assert "Archive of Twins" in out and "JOIN unlocked" in out
    assert "goals:" in out and "twins:" in out and "A Ada" in out
