"""The autocomplete walks the player through each late boss's lesson query."""

from engine.textinput import QueryEditor, coached_step

LICH_RUNES = {"WHERE", "ORDER BY", "LIMIT", "JOIN", "SUBQUERY"}


def walk(coach, runes, start="SELECT "):
    text = start
    for _ in range(30):
        step = coached_step(text, runes, coach)
        if step is None or not step[0]:
            return text, step
        text += step[0] + " "
    raise AssertionError("never finished")


def test_lich_query_is_offered_piece_by_piece_and_ends_with_cast():
    text, last = walk("lich", LICH_RUNES)
    assert "element = (SELECT weakness FROM enemies WHERE id = 6)" in text
    assert text.endswith("ORDER BY power DESC LIMIT 1 ")
    assert last == ("", "CTRL+ENTER casts")


def test_twins_query_uses_join():
    text, last = walk("twins", LICH_RUNES)
    assert "JOIN enemies AS e ON s.element = e.weakness" in text
    assert last[1] == "CTRL+ENTER casts"


def test_no_help_before_the_rune_is_unlocked():
    assert coached_step("SELECT ", {"WHERE", "LIMIT"}, "lich") is None
    assert coached_step("SELECT ", {"WHERE", "LIMIT"}, "twins") is None


def test_free_looks_get_the_usual_help():
    assert coached_step("SELECT * ", LICH_RUNES, "lich") is None
    assert coached_step("SELECT ", LICH_RUNES, None) is None


def test_lowercase_typing_gets_lowercase_help():
    assert coached_step("select name from spells where kind = 'attack' ", LICH_RUNES,
                        "lich")[0] == "and element ="


def test_the_editor_uses_it_when_coached_and_not_otherwise():
    editor = QueryEditor(unlocked=LICH_RUNES)
    editor.coach = "lich"
    editor.set_text("SELECT name FROM spells ")
    assert editor.suggestion().strip() == "WHERE kind = 'attack'"
    editor.coach = None
    assert editor.suggestion().strip().startswith("WHERE element")
