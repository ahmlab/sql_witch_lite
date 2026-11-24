import sys
from dataclasses import fields
from magic.battle import Battle
from pathlib import Path

root = Path(__file__).resolve().parent
while not (root / "magic").is_dir() and root != root.parent:
    root = root.parent
sys.path.insert(0, str(root))

b = Battle(seed=42, guardian="knight")          # or slime up to you
b.foe_act()                                     
b.ada_cast("SELECT name FROM spells WHERE element = 'Fire' LIMIT 1")
b.foe_act()                                     

p = b.brain.percept                             
for f in fields(p):
    print(f"{f.name:18} {getattr(p, f.name)}")

print("\nexplain():")
for k, v in b.brain.explain().items():
    print(f"{k:18} {v}")