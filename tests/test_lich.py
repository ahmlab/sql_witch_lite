"""Tests for the Nested Lich (ai/lich.py, render_lich in ai/styles.py, shell shifting)."""

import random

import pytest

from ai import steering
from ai.lich import (DEFAULT_COSTS, LICH_INTENTS, SHELLS, LichBrain, lich_legal_intents,
                     shift_shell)
from ai.perception import Perception
from ai.roster import GUARDIANS, ORDER, baseline_brain, next_guardian
from ai.styles import LICH_RUNES, LICH_SIGNATURE, render_lich
from magic import guard
from magic.battle import Battle
from magic.cast import load_state, resolve
from magic.db import build_db
from magic.rules import CastMemory


def lich_state(**foe):
    conn = build_db(level=5, foe_ids=[6])
    state = load_state(conn, foe_id=6, seed=1)
    state.ada.runes = {"LIMIT", "WHERE", "SUBQUERY"}
    state.foe.runes = set(LICH_RUNES)
    for name, value in foe.items():
        setattr(state.foe, name, value)
    return conn, state


# ------------------------------------------------------------------ the story order

def test_the_story_order_is_slime_knight_twins_lich():
    assert ORDER == ["slime", "knight", "twins", "lich"]
    assert next_guardian("slime") == "knight"
    assert next_guardian("knight") == "twins"
    assert next_guardian("twins") == "lich"
    assert next_guardian("lich") is None


def test_the_lich_teaches_subquery_and_ada_arrives_knowing_the_older_runes():
    lich = GUARDIANS["lich"]
    assert lich.signature == "SUBQUERY" and lich.foe_id == 6 and lich.level == 5
    assert lich.ada_runes == {"LIMIT", "WHERE", "ORDER BY", "JOIN"}


# ------------------------------------------------------------------ his queries

@pytest.mark.parametrize("action", list(LICH_INTENTS))
def test_every_lich_query_has_a_subquery_and_passes_the_rune_gate(action):
    conn, state = lich_state()
    sql = render_lich(LICH_INTENTS[action], state, 1)
    assert "SUBQUERY" in guard.inspect(sql, LICH_RUNES)


@pytest.mark.parametrize("action", [a for a in LICH_INTENTS if a != "rest"])
def test_each_spell_query_returns_exactly_the_spell_it_means(action):
    conn, state = lich_state()
    sql = render_lich(LICH_INTENTS[action], state, 1)
    rows = conn.execute(sql).fetchall()
    from ai.lich import ACTION_SPELLS
    assert rows == [(ACTION_SPELLS[action],)]


def test_resting_casts_nothing():
    conn, state = lich_state()
    report = resolve(conn, state, render_lich(LICH_INTENTS["rest"], state, 1), "foe",
                     random.Random(1))
    assert report.casts == [] and report.scry


def test_his_first_query_is_the_invitation():
    battle = Battle(seed=1, guardian="lich")
    assert "SUBQUERY" not in battle.state.ada.runes and battle.whose_turn == "foe"
    turn = battle.foe_act()
    assert turn.invitation == "SUBQUERY" and "SUBQUERY" in battle.state.ada.runes


def test_only_the_lich_is_in_the_world():
    battle = Battle(seed=1, guardian="lich")
    assert battle.conn.execute("SELECT name FROM enemies").fetchall() == [("Nested Lich",)]
    assert {r[0] for r in battle.conn.execute("SELECT DISTINCT foe_id FROM foe_spells")} == {6}


# ------------------------------------------------------------------ the shells

def test_shells_only_use_pairs_that_the_type_chart_agrees_with():
    conn = build_db(level=5, foe_ids=[6])
    for element, weakness in SHELLS:
        row = conn.execute("SELECT multiplier FROM type_chart WHERE attack = ? AND defend = ?",
                           (weakness, element)).fetchone()
        assert row == (2.0,)


def test_the_shell_changes_at_the_end_of_every_round_and_the_table_agrees():
    battle = Battle(seed=2, guardian="lich")
    seen = [battle.state.foe.element]
    for _ in range(6):
        battle.foe_act()
        battle.ada_cast("SELECT name FROM spells LIMIT 1")
        assert battle.state.foe.element != seen[-1]
        row = battle.conn.execute("SELECT element, weakness FROM enemies").fetchone()
        assert row == (battle.state.foe.element, battle.state.foe.weakness)
        seen.append(battle.state.foe.element)


def test_shift_shell_never_repeats_the_same_element():
    conn, state = lich_state()
    rng = random.Random(0)
    for _ in range(30):
        before = state.foe.element
        shift_shell(state, conn, rng)
        assert state.foe.element != before


def test_a_subquery_always_finds_the_current_weakness():
    battle = Battle(seed=4, guardian="lich")
    battle.state.ada.runes.add("SUBQUERY")
    sql = "SELECT name FROM spells WHERE element = (SELECT weakness FROM enemies WHERE id = 6)"
    for _ in range(5):
        battle.foe_act()
        battle.ada_cast("SELECT * FROM enemies")                # a look does not end the turn
        rows = battle.conn.execute(sql).fetchall()
        weakness = battle.state.foe.weakness
        wanted = battle.conn.execute("SELECT name FROM spells WHERE element = ?",
                                     (weakness,)).fetchall()
        assert rows == wanted
        battle.ada_cast("SELECT name FROM spells LIMIT 1")


# ------------------------------------------------------------------ perception, goals, steering

def test_he_builds_his_layers_first_veil_then_bone_ward():
    conn, state = lich_state()
    brain = LichBrain(DEFAULT_COSTS)
    first = brain.decide(state, random.Random(1))
    assert first.action == "veil"
    assert brain.movement == steering.Movement("arrive", "home")


def test_he_will_not_cast_what_he_cannot_pay_for():
    for seed in range(20):
        conn, state = lich_state(mp=2)
        brain = LichBrain(DEFAULT_COSTS)
        assert brain.decide(state, random.Random(seed)).action == "rest"


def test_he_finishes_a_weak_ada():
    conn, state = lich_state(relevance=True, ward=30)
    state.ada.hp = 20
    brain = LichBrain(DEFAULT_COSTS)
    actions = {brain.decide(state, random.Random(s)).action for s in range(10)}
    assert "finisher" in actions


def test_he_heals_when_he_is_hurt():
    conn, state = lich_state(relevance=True, ward=30, hp=200)
    brain = LichBrain(DEFAULT_COSTS)
    actions = {brain.decide(state, random.Random(s)).action for s in range(15)}
    assert "siphon" in actions


def test_he_becomes_besieged_when_ada_finds_his_weakness_then_keeps_his_distance():
    conn, state = lich_state(relevance=True)
    brain = LichBrain(DEFAULT_COSTS)
    state.ada_casts.append(CastMemory(1, ("WHERE",), ("Light",), 80, True, 0, False))
    brain.decide(state, random.Random(1))
    assert brain.mode == "besieged"
    assert brain.idle_movement() == steering.Movement("evade", "ada")


def test_the_lich_only_returns_legal_intents_and_the_baseline_too():
    conn, state = lich_state(mp=7)
    legal = {i.action for i in lich_legal_intents(state)}
    assert legal == {"rest", "strike", "heavy", "veil", "bone"}
    baseline = baseline_brain("lich", conn)
    for seed in range(20):
        assert baseline.decide(state, random.Random(seed)).action in legal


def test_perception_knows_what_he_can_afford():
    conn, state = lich_state(mp=5)
    p = Perception(DEFAULT_COSTS).sense(state)
    assert p.affordable == {"strike", "bone"}


# ------------------------------------------------------------------ whole fights

def fight(bot, seed):
    battle = Battle(seed=seed, guardian="lich")
    for _ in range(400):
        if battle.whose_turn == "over":
            break
        if battle.whose_turn == "ada":
            battle.ada_cast(bot(battle))
        else:
            battle.foe_act()
    return battle


def blind(battle):
    return "SELECT name FROM spells LIMIT 1"


def subquery_player(battle):
    ada = battle.state.ada
    if ada.hp_ratio < 0.4 and ada.mp >= 6:
        return "SELECT name FROM spells WHERE name = 'Mend'"
    weak = "(SELECT weakness FROM enemies WHERE id = 6)"
    return ("SELECT name FROM spells WHERE kind = 'attack' AND element = " + weak +
            " AND power = (SELECT MAX(power) FROM spells WHERE kind = 'attack' AND element = " +
            weak + " AND mp_cost <= (SELECT mp FROM witch))")


def test_the_lich_beats_a_player_who_never_uses_his_lesson_and_loses_to_one_who_does():
    assert all(fight(blind, seed).winner == "foe" for seed in range(8))
    assert all(fight(subquery_player, seed).winner == "ada" for seed in range(8))


def test_the_same_seed_replays_the_same_lich_battle():
    a, b = fight(subquery_player, 5), fight(subquery_player, 5)
    assert a.state.foe_book == b.state.foe_book and a.state.ada.hp == b.state.ada.hp


def test_the_terminal_can_fight_the_lich():
    from sim import play_cli
    lines = iter(["SELECT * FROM enemies", ":why", ":quit"])
    out = []
    play_cli.main(["--seed", "2", "--foe", "lich"], read=lambda p: next(lines), out=out.append)
    text = "\n".join(out)
    assert "NESTED LICH" in text and "SUBQUERY" in text


# ------------------------------------------------------------------ the window

def test_a_lich_battle_plays_to_its_result_screen():
    pygame = pytest.importorskip("pygame")
    pygame.init()
    pygame.display.set_mode((320, 180))
    from engine.scenes import BattleScene, Game, ResultScene
    game = Game(pygame.Surface((320, 180)), seed=3, start="lich")
    game.handle(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, mod=0))
    game.handle(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0))
    scene = game.scene
    assert isinstance(scene, BattleScene) and scene.key == "lich"
    canvas = pygame.Surface((320, 180))
    for _ in range(60 * 200):
        game.update(16)
        if not isinstance(game.scene, BattleScene):
            break
        game.scene.draw(canvas)
        if game.scene.phase == "input":
            for char in subquery_player(game.scene.battle):
                game.handle(pygame.event.Event(pygame.TEXTINPUT, text=char))
            game.handle(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN,
                                           mod=pygame.KMOD_LCTRL))
    game.update(16)
    assert isinstance(game.scene, ResultScene) and game.scene.won
    assert game.scene.next is None                          # the Lich is the last fight


def test_winning_against_the_twins_leads_to_the_lich():
    pygame = pytest.importorskip("pygame")
    pygame.init()
    pygame.display.set_mode((320, 180))
    from engine.scenes import DialogueScene, Game, ResultScene
    game = Game(pygame.Surface((320, 180)), seed=3, start="twins")
    battle = Battle(seed=1, guardian="twins")
    battle.winner = "ada"
    result = ResultScene(game, battle)
    assert result.next == "lich"
    game.scene = result
    game.handle(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, mod=0))
    assert isinstance(game.scene, DialogueScene) and game.scene.backdrop == "crypt"


def test_the_whole_story_runs_in_order_slime_knight_twins_lich_then_the_end():
    pygame = pytest.importorskip("pygame")
    pygame.init()
    pygame.display.set_mode((320, 180))
    from engine.scenes import Game, ResultScene
    game = Game(pygame.Surface((320, 180)), seed=3, start="slime")
    after = []
    for key in ORDER:
        battle = Battle(seed=1, guardian=key)
        battle.winner = "ada"
        after.append(ResultScene(game, battle).next)
    assert after == ["knight", "twins", "lich", None]
