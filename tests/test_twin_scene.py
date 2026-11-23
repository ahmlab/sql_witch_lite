import pytest

pygame = pytest.importorskip("pygame")

import main
from ai.roster import next_guardian
from engine import render
from engine.scenes import DialogueScene, Game, ResultScene, TitleScene, next_scene
from engine.twin_scene import TwinScene, draw_archive, draw_key_chain, draw_twin
from magic.cast import sync_state

JOIN = ("SELECT s.name, e.name FROM spells AS s JOIN enemies AS e ON s.element = e.weakness "
        "WHERE s.kind = 'attack' AND s.mp_cost <= 3")


@pytest.fixture(autouse=True)
def pygame_up():
    pygame.init()
    pygame.display.set_mode((320, 180))
    yield
    pygame.quit()


def key(game, k, mod=0):
    game.handle(pygame.event.Event(pygame.KEYDOWN, key=k, mod=mod))


def run(game, ms):
    for _ in range(ms // 16):
        game.update(16)
        game.draw()


def cast(game, sql):
    for char in sql:
        game.handle(pygame.event.Event(pygame.TEXTINPUT, text=char))
    key(game, pygame.K_RETURN, pygame.KMOD_LCTRL)


def until_input(game, limit_ms=90_000):
    for _ in range(limit_ms // 100):
        if not isinstance(game.scene, TwinScene) or game.scene.phase == "input":
            return
        run(game, 100)


@pytest.fixture
def twin_game():
    canvas = pygame.Surface((320, 180))
    game = Game(canvas, 7, start="twins")
    game.switch(TwinScene(game, "twins"))
    until_input(game)
    return game


def test_the_story_can_start_at_the_twins_and_leads_to_their_scene():
    game = Game(pygame.Surface((320, 180)), 7, start="twins")
    run(game, 200)
    key(game, pygame.K_RETURN)
    assert isinstance(game.scene, DialogueScene) and game.scene.guardian == "twins"
    assert isinstance(next_scene(game, "twins"), TwinScene)


def test_the_launcher_accepts_start_twins():
    assert main.parse_args(["--start", "twins"]).start == "twins"
    assert main.run(3, scale=1, max_frames=5, start="twins") == 0


def test_a_guardian_outside_the_story_has_no_next_one_and_the_twins_lead_to_the_lich():
    assert next_guardian("dummy") is None and next_guardian("twins") == "lich"


def test_the_scene_has_two_foes_each_with_its_own_bar(twin_game):
    scene = twin_game.scene
    state = scene.battle.state
    assert scene.bars["foe"][0] == state.foe.hp and scene.bars["twin"][0] == state.twin.hp
    assert set(scene.bodies) == {"quill", "ink"}


def test_one_join_hits_both_twins_on_screen(twin_game):
    scene = twin_game.scene
    cast(twin_game, JOIN)
    run(twin_game, 2500)
    state = scene.battle.state
    assert state.foe.hp < 90 and state.twin.hp < 90
    assert scene.bars["foe"][0] < 90 and scene.bars["twin"][0] < 90


def test_a_fallen_twin_is_restored_with_a_beat(twin_game):
    scene = twin_game.scene
    state = scene.battle.state
    state.twin.hp = 0
    sync_state(scene.battle.conn, state)
    scene.shown["twin"][0] = 0
    scene.bars["twin"][0] = 0
    cast(twin_game, "SELECT name FROM spells WHERE name = 'Mend'")
    seen = []
    for _ in range(400):
        run(twin_game, 50)
        if scene.beat is not None:
            seen.append(scene.beat.text)
    assert any("gets back up" in text for text in seen)
    assert state.twin.hp > 0


def test_every_drawing_function_runs_in_every_state():
    canvas = pygame.Surface((320, 180))
    for who in ("quill", "ink"):
        for flash in (False, True):
            for fainted in (False, True):
                for element in list(render.ELEMENT_COLOURS):
                    draw_twin(canvas, (100, 40), 500, flash, fainted, who, flash, element)
    for linked in (True, False):
        for pulse in (0, 500):
            draw_key_chain(canvas, (200, 40), (240, 50), 300, linked, pulse)
    draw_archive(canvas, 1234)


def test_winning_and_losing_end_in_the_result_scene_without_crashing(twin_game):
    scene = twin_game.scene
    state = scene.battle.state
    state.foe.hp, state.twin.hp = 20, 20
    cast(twin_game, JOIN)
    for _ in range(300):
        run(twin_game, 100)
        if isinstance(twin_game.scene, ResultScene):
            break
        if twin_game.scene.phase == "end":
            continue
    assert isinstance(twin_game.scene, ResultScene) and twin_game.scene.won
    assert twin_game.scene.next == "lich"
    key(twin_game, pygame.K_RETURN)          # on to the last guardian, the Lich
    assert isinstance(twin_game.scene, DialogueScene)


def test_trying_again_after_a_defeat_returns_to_the_twins_scene():
    game = Game(pygame.Surface((320, 180)), 7, start="twins")
    scene = TwinScene(game, "twins")
    game.switch(scene)
    scene.battle.state.ada.hp = 0
    scene.battle._advance()
    from engine.scenes import ResultScene as Result
    game.switch(Result(game, scene.battle))
    key(game, pygame.K_RETURN)
    assert isinstance(game.scene, TwinScene)
