from __future__ import annotations

import random
from collections import Counter

from ai.barks import Bark, Barker
from ai.base import Intent
from ai.director import Director
from ai.goals import AtomicGoal, CompositeGoal, Context, Evaluator
from ai.guardian import REST, GuardianBrain
from ai.perception import summary
from ai.goap import Act, Plan, plan
from ai.patterns import read_tells, signature, unsure
from ai.steering import Movement

NULL_ID = 20
VEIL = frozenset({"IS NULL", "COALESCE"})
KINDS = ("blind", "repeat", "fixed", "adaptive")
MOVES = ("strike", "echo", "doubt", "shift", "fade")

ACTION_SPELLS = {
    "strike": "Empty Strike", "echo": "Echo of Doubt", "doubt": "Whisper of Doubt",
    "shift": "Shift of Nothing", "fade": "Fade to Grey", "heal": "Hollow Mend",
}
DEFAULT_COSTS = {"strike": 5, "echo": 7, "doubt": 5, "shift": 6, "fade": 6, "heal": 9}
NULL_INTENTS = {
    "strike": Intent("strike", "Ada", "attack"),
    "echo": Intent("echo", "Ada", "echo"),
    "doubt": Intent("doubt", "Ada", "doubt"),
    "shift": Intent("shift", None, "shift"),
    "fade": Intent("fade", None, "fade"),
    "heal": Intent("heal", None, "heal"),
    "rest": Intent("rest", None, "scry"),
}

COUNTER = {
    "strike": {"blind": 0.67, "repeat": 0.5, "fixed": 0.5, "adaptive": 0.5},
    "echo": {"blind": 0.5, "repeat": 0.6, "fixed": 0.6, "adaptive": 0.6},
    "doubt": {"blind": 0.6, "repeat": 0.5, "fixed": 0.5, "adaptive": 0.6},
    "shift": {"blind": 0.25, "repeat": 0.5, "fixed": 0.8, "adaptive": 0.25},
    "fade": {"blind": 0.25, "repeat": 0.83, "fixed": 0.5, "adaptive": 0.5},
}
KNOWN = ["LIMIT+WHERE", "IS NULL+JOIN+WHERE", "COALESCE+IS NULL+JOIN+WHERE"]

MODE_BIAS = {
    "listening":   {"doubt": 1.5, "strike": 0.7, "fade": 0.6, "shift": 0.6},
    "mirroring":   {"fade": 1.3, "shift": 1.3, "echo": 1.1},
    "doubting":    {},
    "hunting":     {"strike": 1.4, "echo": 1.3, "fade": 0.7, "shift": 0.7},
    "unravelling": {"heal": 1.5, "fade": 1.2, "doubt": 1.1},
}
MOVEMENT = {
    "strike": Movement("pursue", "ada"), "echo": Movement("arrive", "front"),
    "doubt": Movement("arrive", "front"), "shift": Movement("evade", "ada"),
    "fade": Movement("evade", "ada"), "heal": Movement("arrive", "home"),
    "rest": Movement("wander", "home"),
}

LISTEN_UNTIL = 2
CONFIDENT = 0.5
GUESS_HIT = 60.0
STARVE_MP = 16
SIMS = 24
FADE_TURNS = 3
SIM_WEIGHT = 0.55
PLAN_PULL = 0.6
EXPOSED = 1.5
LOADED = 40
STRIKE_POWER, ECHO_SHARE, ECHO_CAP, DRAIN, MEND = 34, 0.6, 45, 20, 25

TELL_WORDS = ["COALESCE", "IS NULL", "GROUP BY", "DISTINCT", "JOIN", "LIMIT", "WHERE"]

NULL_BARKS = [
    Bark("unravel", lambda i: i["my_hp"] < 0.3,
         ("I... have a value?", "Stop giving me a value!"), 7),
    Bark("predict", lambda i: i["mode"] == "mirroring" and i["word"] and i["move"] in ("fade", "shift", "doubt"),
         ("You will {word} again. I know it.", "{word}, {word}, {word}. Predictable.",
          "I already know your next {word}."), 6),
    Bark("plan", lambda i: i["steps"] >= 3 and i["move"] == i["first"],
         ("Three moves ahead of you, witch.", "{plan_words}. Then you fall.",
          "I've already planned your ending."), 5),
    Bark("called it", lambda i: i["right"] is True and i["hits"] >= 2,
         ("I knew you'd do that.", "Called it. {hits} out of {guesses}.", "You're so easy to read."), 5),
    Bark("blind", lambda i: i["blind"] >= 0.5,
         ("You still can't see me, can you?", "= NULL is never true, Ada.",
          "Look at the void. IS it there?"), 5),
    Bark("surprised", lambda i: i["right"] is False and i["guesses"] >= 3,
         ("...I didn't see that coming.", "You changed. Interesting.", "Unpredictable. I hate that."), 4),
    Bark("hunting", lambda i: i["ada_hp"] < 0.35,
         ("Your queries were always pointless.", "Nobody reads your dashboards."), 3),
    Bark("listening", lambda i: i["mode"] == "listening",
         ("Show me how you cast, Ada.", "I'm listening. Go on, cast."), 2),
    Bark("move", lambda i: True,
         ("Nothing hits harder than nothing.", "Are you sure you have the mana?",
          "Your own spell, Ada. Feel it.", "I've been watching since the Glade."), 1),
]


def null_legal_intents(state):
    return list(NULL_INTENTS.values())


def classify(token, last_hit):
    runes = set(token.split("+"))
    if not VEIL & runes:
        return "blind"
    if last_hit is not None and token == last_hit:
        return "repeat"
    if "COALESCE" in runes:
        return "adaptive"
    return "fixed"


def make_plan(move):
    return CompositeGoal(move, [
        AtomicGoal("drift", movement=MOVEMENT[move]),
        AtomicGoal(move, NULL_INTENTS[move], MOVEMENT[move],
                   requires=lambda p, m=move: m == "rest" or p.can(m)),
    ])


class NullBrain(GuardianBrain):
    technique = "tell reading + GOAP planner + Monte Carlo lookahead"
    start_mode = "listening"
    repeat_penalty = 0.8

    def __init__(self, costs=None, reading=True, planner=True, lookahead=True):
        self.utility = {}
        evaluators = [Evaluator(m, self.desire(m), lambda p, m=m: make_plan(m))
                      for m in (*MOVES, "heal")]
        evaluators.append(Evaluator("rest", lambda p, mode: 0.02, lambda p: make_plan("rest")))
        super().__init__(costs or dict(DEFAULT_COSTS), evaluators)
        self.reading = reading
        self.planner = planner
        self.lookahead_on = lookahead
        self.old_history = []
        self.history = []
        self.seen = 0
        self.avg_hit = GUESS_HIT
        self.prediction = {}
        self.rule = "no tells yet"
        self.kind_odds = {}
        self.top_guess = None
        self.sure = 0.0
        self.last_hit = None
        self.hits = 0
        self.guesses = 0
        self.guess_log = []
        self.harmless = 0.0
        self.free_block = False
        self.sim_scores = {}
        self.goap = Plan()
        self.facts = {}
        self.last_right = None
        self.turns = 0
        self.director = Director()
        self.barker = Barker(NULL_BARKS)
        self.says = None

    def observe_run(self, history):
        self.old_history += [h if isinstance(h, str) else signature(h) for h in history]

    def desire(self, move):
        return lambda p, mode: self.utility.get(move, 0.0)


    def watch(self, state):
        start = self.seen
        self.seen = len(state.ada_casts)
        notes = []
        for cast in state.ada_casts[start:]:
            if cast.scry:
                continue
            token = signature(cast.runes)
            if self.top_guess is not None:
                self.guesses += 1
                right = token == self.top_guess
                self.last_right = right
                self.hits += right
                self.guess_log.append({"turn": cast.turn, "predicted": self.top_guess,
                                       "actual": token, "correct": right,
                                       "p_actual": round(self.prediction.get(token, 0.0), 3)})
                notes.append(f"guessed {self.top_guess}, she cast {token}"
                             f" ({'right' if right else 'wrong'})")
                self.top_guess = None
            if cast.damage > 0:
                self.avg_hit = 0.7 * self.avg_hit + 0.3 * cast.damage
            self.history.append(token)
        return notes

    def predict(self, state):
        vocab = sorted(set(self.history) | set(self.old_history) | set(KNOWN))
        if self.reading:
            self.prediction, self.rule, guess = read_tells(self.history, vocab, self.old_history)
        else:
            self.prediction = {t: 1 / len(vocab) for t in vocab}
            self.rule, guess = "not reading", None
        self.top_guess = guess
        self.sure = self.prediction.get(guess, 0.0) if guess else 0.0
        self.last_hit = find_last_hit(state.ada_casts)
        odds = Counter()
        for token, chance in self.prediction.items():
            odds[classify(token, self.last_hit)] += chance
        self.kind_odds = {k: round(odds.get(k, 0.0), 3) for k in KINDS}

    def is_faded(self, state):
        fade = state.foe.status.get("fade")
        return fade is not None and self.last_hit == "+".join(fade)


    def world(self, p, state):
        real = [c for c in state.ada_casts if not c.scry]
        return {
            "read": self.sure >= CONFIDENT,
            "marked": self.last_hit is not None,
            "blocked": self.is_faded(state),
            "hidden": "shifted" in state.foe.status,
            "dry": p.ada_mp <= STARVE_MP,
            "hurt": p.ada_hp_ratio < 0.5,
            "down": False,
            "safe": p.my_hp_ratio >= 0.45,
            "loaded": bool(real) and real[-1].damage >= LOADED,
        }

    def actions(self, p, state):
        odds = self.kind_odds
        ada = state.ada
        half = ada.max_hp * 0.5
        to_hurt = max(1.0, (ada.hp - half) / STRIKE_POWER)
        to_down = max(1.0, min(ada.hp, half) / STRIKE_POWER)
        echo_down = max(1.0, min(ada.hp, half) / ECHO_CAP)
        open_to = EXPOSED * (1 - odds.get("blind", 0.0))
        fade_cover = odds.get("repeat", 0.0)
        shift_cover = 0.75 * odds.get("fixed", 0.0)

        def danger(w):
            cover = max(fade_cover if w.get("blocked") else 0.0,
                        shift_cover if w.get("hidden") else 0.0)
            return 1.0 + open_to * (1 - cover)

        def heals(w):
            return 1.0 if w.get("dry") else 1.4

        acts = [
            Act("fade her trick", "fade", (("read", True), ("marked", True), ("blocked", False)),
                (("blocked", True),), lambda w: 1 + 3 * (1 - odds.get("repeat", 0.0))),
            Act("shift away", "shift", (("hidden", False),), (("hidden", True),),
                lambda w: 1 + 3 * (1 - odds.get("fixed", 0.0))),
            Act("drain her", "doubt", (("dry", False),), (("dry", True),),
                lambda w: 1 + max(0, p.ada_mp - STARVE_MP) / DRAIN),
            Act("wear her down", "strike", (("hurt", False),), (("hurt", True),),
                lambda w: to_hurt * danger(w)),
            Act("turn her spell", "echo", (("loaded", True), ("hurt", False)),
                (("hurt", True), ("loaded", False)), lambda w: danger(w)),
            Act("finish her", "strike", (("hurt", True),), (("down", True),),
                lambda w: to_down * danger(w) * heals(w)),
            Act("echo the end", "echo", (("loaded", True), ("hurt", True)),
                (("down", True), ("loaded", False)), lambda w: echo_down * danger(w) * heals(w)),
            Act("mend", "heal", (("safe", False),), (("safe", True),),
                lambda w: self.avg_hit / MEND),
        ]
        return [a for a in acts if p.can(a.move)]

    def goals(self, p):
        down = ("bring her down", {"down": True})
        match self.mode:
            case "listening":
                return [("drain her first", {"dry": True}), down]
            case "unravelling" if p.ada_hp_ratio >= 0.5:
                return [("survive", {"safe": True}), down]
            case _:
                return [down]

    def think_ahead(self, p, state):
        self.facts = self.world(p, state)
        if not self.planner:
            self.goap = Plan(goal="planner off")
            return self.goap
        acts = self.actions(p, state)
        tried = 0
        for name, goal in self.goals(p):
            found = plan(self.facts, goal, acts, name)
            tried += found.searched
            if found.found and found.steps:
                found.searched = tried
                self.goap = found
                return found
        self.goap = Plan(searched=tried, goal="nothing to plan")
        return self.goap


    def lookahead(self, p, state, rng):
        sim = random.Random(rng.random())
        kinds = list(self.kind_odds)
        weights = [self.kind_odds[k] for k in kinds]
        if sum(weights) <= 0:
            weights = [1] * len(kinds)
        ada, me = state.ada, state.foe
        real = [c for c in state.ada_casts if not c.scry]
        last_damage = real[-1].damage if real else 0
        faded = self.is_faded(state)
        values = {}
        for move in (*MOVES, "heal"):
            if move != "heal" and not p.can(move):
                continue
            total = 0.0
            for _ in range(SIMS):
                kind = sim.choices(kinds, weights)[0]
                roll = sim.uniform(0.85, 1.0) * (1.5 if sim.random() < 1 / 16 else 1.0)
                dealt = 0.0
                if move == "strike":
                    dealt = STRIKE_POWER * roll
                elif move == "echo":
                    dealt = min(ECHO_CAP, ECHO_SHARE * last_damage) * roll
                taken = self.avg_hit * sim.uniform(0.85, 1.0)
                saved_later = 0.0
                match kind:
                    case "blind":
                        taken = 0
                    case "repeat" if faded:
                        taken = 0
                    case "repeat" if move == "fade":
                        saved_later = taken * FADE_TURNS * self.kind_odds.get("repeat", 0)
                        taken = 0
                    case "fixed" if move == "shift":
                        taken *= 0.25
                if move == "doubt" and p.ada_mp - DRAIN < 12:
                    taken *= 0.5
                if move == "heal":
                    taken -= MEND
                score = dealt / ada.max_hp - taken / me.max_hp + saved_later / me.max_hp
                if dealt >= ada.hp:
                    score += 1.0
                if taken >= me.hp:
                    score -= 1.0
                total += score
            values[move] = round(total / SIMS, 3)
        self.sim_scores = values
        return values


    def score_moves(self, p, mode, state, rng):
        bias = MODE_BIAS.get(mode, {})
        sims = self.lookahead(p, state, rng) if self.lookahead_on else {}
        goap = self.think_ahead(p, state)
        u = {}
        for move in MOVES:
            belief = sum(odds * COUNTER[move][kind] for kind, odds in self.kind_odds.items())
            if self.lookahead_on:
                model = min(1.0, max(0.0, 0.5 + 2 * sims.get(move, -0.25)))
                value = SIM_WEIGHT * model + (1 - SIM_WEIGHT) * belief
            else:
                value = belief
            if goap.first == move:
                value += PLAN_PULL * self.director.intensity
            u[move] = value * bias.get(move, 1.0)

        self.harmless = round(self.kind_odds.get("blind", 0.0)
                              + (self.kind_odds.get("repeat", 0.0) if self.is_faded(state) else 0.0), 3)
        if not self.lookahead_on:
            u["strike"] += 0.7 * self.harmless
        if self.last_hit is None or self.is_faded(state):
            u["fade"] = 0.0
        if "shifted" in state.foe.status:
            u["shift"] *= 0.3
        if p.ada_mp < 6:
            u["doubt"] *= 0.3
        elif p.ada_hp_ratio < 0.5 and p.ada_mp <= STARVE_MP:
            u["doubt"] += 0.9
        real = [c for c in state.ada_casts if not c.scry]
        u["echo"] *= min(1.0, (real[-1].damage if real else 0) / 40) or 0.1
        if p.ada_hp_ratio < 0.35:
            u["strike"] += 0.4 * self.director.intensity
            u["echo"] += 0.2 * self.director.intensity
        heal = 1.6 * (1 - p.my_hp_ratio) ** 2 * bias.get("heal", 1.0) if p.my_hp_ratio < 0.6 else 0.0
        u["heal"] = heal
        self.utility = {m: round(max(0.0, v), 3) for m, v in u.items()}

    def next_mode(self, p, rng):
        sure = max(self.kind_odds.values(), default=0.0)
        match self.mode:
            case _ if p.my_hp_ratio < 0.3:
                return "unravelling"
            case _ if len(self.history) + len(self.old_history) < LISTEN_UNTIL:
                return "listening"
            case _ if p.ada_hp_ratio < 0.35:
                return "hunting"
            case _ if sure >= CONFIDENT:
                return "mirroring"
            case _:
                return "doubting"

    def idle_movement(self):
        match self.mode:
            case "hunting":
                return Movement("pursue", "ada")
            case "unravelling":
                return Movement("evade", "ada")
            case _:
                return Movement("wander", "home")

    def decide(self, state, rng):
        self.turns += 1
        notes = self.watch(state)
        self.predict(state)
        p = self.percept = self.perception.sense(state)
        old_mode = self.mode
        self.mode = self.next_mode(p, rng)
        self.director.update(p.ada_hp_ratio, p.my_hp_ratio)
        self.score_moves(p, self.mode, state, rng)
        ctx = Context(p, rng)
        intent = self.think.think(ctx, self.mode) or REST
        self.movement = ctx.movement or self.idle_movement()
        self.free_block = self.harmless >= 0.8 and intent.action != "fade"
        word = next((w for w in TELL_WORDS if self.top_guess and w in self.top_guess.split("+")), "")
        moves = [s.move for s in self.goap.steps]
        info = {"mode": self.mode, "move": intent.action, "word": word, "right": self.last_right,
                "hits": self.hits, "guesses": self.guesses, "blind": self.kind_odds.get("blind", 0),
                "my_hp": p.my_hp_ratio, "ada_hp": p.ada_hp_ratio, "steps": len(moves),
                "first": self.goap.first, "plan_words": ", then ".join(moves[:2]).capitalize()}
        self.says = self.barker.speak(info, self.turns, rng)
        self.last_right = None
        top = sorted(self.prediction.items(), key=lambda kv: -kv[1])[:3]
        rate = f"{self.hits}/{self.guesses}" if self.guesses else "no guesses checked yet"
        self._last = {
            "technique": self.technique,
            "mode": f"{old_mode} -> {self.mode}",
            "tell": f"{self.rule} -> {self.top_guess} {self.sure:.0%}",
            "goap": self.goap.line(),
            "intent": intent.action,
            "says": self.says or "",
            "utilities": ", ".join(f"{m} {v:.2f}" for m, v in
                                   sorted(self.utility.items(), key=lambda kv: -kv[1])),
            "lookahead": ", ".join(f"{m} {v:+.2f}" for m, v in
                                   sorted(self.sim_scores.items(), key=lambda kv: -kv[1])),
            "facts": ", ".join(k for k, v in self.facts.items() if v) or "none",
            "predicts": ", ".join(f"{t} {q:.0%}" for t, q in top),
            "kinds": ", ".join(f"{k} {q:.0%}" for k, q in self.kind_odds.items()),
            "hit rate": rate,
            "harmless": f"P(her next cast can't touch me) = {self.harmless:.0%}",
            "watched": "; ".join(notes) or "nothing new",
            "sees": summary(p),
            "uncertainty": f"{unsure(self.prediction):.2f} bits",
            "plan": self.think.describe(),
            "steps": " / ".join(ctx.trace),
            "movement": f"{self.movement.behaviour} {self.movement.target}",
            "director": self.director.line(),
        }
        return intent


def find_last_hit(casts):
    for cast in reversed(casts):
        if not cast.scry and cast.damage > 0:
            return signature(cast.runes)
    return None
