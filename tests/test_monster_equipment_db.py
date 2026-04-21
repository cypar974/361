from pathlib import Path
from database.db_manager import DatabaseManager
from gameplay.monster import Monster
from gameplay.item import Item


def _make_db(tmp_path, monkeypatch):
    """Returns a DatabaseManager with schema initialized."""
    project_root = Path(__file__).parent.parent
    monkeypatch.chdir(project_root)
    db = DatabaseManager(db_file=str(tmp_path / "test_monster.db"))
    return db


def _insert_item(
    db,
    name="Goblin Blade",
    item_type="weapon",
    slot="weapon",
    base_damage=5,
    defense=0,
    durability=100,
    max_durability=100,
):
    """Insert an item into the items table and return its id."""
    db.cursor.execute(
        """INSERT INTO items (name, item_type, slot, base_damage, defense,
           durability, max_durability)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (name, item_type, slot, base_damage, defense, durability, max_durability),
    )
    db.conn.commit()
    return db.cursor.lastrowid


def _insert_monster(
    db,
    name="Goblin",
    q=5,
    r=7,
    health=30,
    damage=8,
    weapon_id=None,
    head_id=None,
    chest_id=None,
    legs_id=None,
):
    """Insert a monster row and return its id."""
    db.cursor.execute(
        """INSERT INTO monsters (name, current_q, current_r, health, damage,
           weapon_item_id, head_item_id, chest_item_id, legs_item_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (name, q, r, health, damage, weapon_id, head_id, chest_id, legs_id),
    )
    db.conn.commit()
    return db.cursor.lastrowid

# DB layer: load_monsters

def test_load_monsters_no_equipment(tmp_path, monkeypatch):
    """Monster with no equipment loads correctly."""
    db = _make_db(tmp_path, monkeypatch)
    _insert_monster(db, name="Goblin", q=3, r=4, health=30, damage=8)

    monsters = db.load_monsters()
    assert len(monsters) == 1
    m = monsters[0]
    assert m["name"] == "Goblin"
    assert m["current_q"] == 3
    assert m["current_r"] == 4
    assert m["health"] == 30
    assert m["weapon_item"] is None
    assert m["head_item"] is None
    assert m["chest_item"] is None
    assert m["legs_item"] is None
    db.close()


def test_load_monsters_with_weapon(tmp_path, monkeypatch):
    """Monster with a weapon should have weapon_item populated."""
    db = _make_db(tmp_path, monkeypatch)
    sword_id = _insert_item(
        db, name="Goblin Blade", item_type="weapon", slot="weapon", base_damage=5
    )
    _insert_monster(db, name="Goblin", weapon_id=sword_id)

    monsters = db.load_monsters()
    assert len(monsters) == 1
    weapon = monsters[0]["weapon_item"]
    assert weapon is not None
    assert weapon["name"] == "Goblin Blade"
    assert weapon["base_damage"] == 5
    assert weapon["slot"] == "weapon"
    db.close()


def test_load_monsters_with_full_equipment(tmp_path, monkeypatch):
    """Monster with weapon and head armor slots filled."""
    db = _make_db(tmp_path, monkeypatch)
    sword_id = _insert_item(db, name="Blade", slot="weapon", base_damage=7)
    helm_id = _insert_item(db, name="Helm", item_type="armor", slot="head", defense=5)
    _insert_monster(db, name="Knight", weapon_id=sword_id, head_id=helm_id)

    monsters = db.load_monsters()
    m = monsters[0]
    assert m["weapon_item"]["name"] == "Blade"
    assert m["head_item"]["name"] == "Helm"
    db.close()


def test_load_monsters_skips_defeated(tmp_path, monkeypatch):
    """Defeated monsters should not be loaded."""
    db = _make_db(tmp_path, monkeypatch)
    _insert_monster(db, name="Alive Goblin")
    mid = _insert_monster(db, name="Dead Goblin")
    db.cursor.execute("UPDATE monsters SET is_defeated=1 WHERE id=?", (mid,))
    db.conn.commit()

    monsters = db.load_monsters()
    assert len(monsters) == 1
    assert monsters[0]["name"] == "Alive Goblin"
    db.close()

# DB layer: save_monster_equipment

def test_save_monster_equipment(tmp_path, monkeypatch):
    """Saving equipment should persist item IDs to the monster row."""
    db = _make_db(tmp_path, monkeypatch)
    sword_id = _insert_item(db, name="Blade", slot="weapon", base_damage=5)
    helm_id = _insert_item(db, name="Helm", item_type="armor", slot="head", defense=3)
    mid = _insert_monster(db, name="Goblin")

    # Build equipment dict with Item objects. save_monster_equipment reads
    # the weapon/head/chest/legs keys off the dict.
    sword = Item(
        {
            "id": sword_id,
            "name": "Blade",
            "item_type": "weapon",
            "slot": "weapon",
            "base_damage": 5,
        }
    )
    helm = Item(
        {
            "id": helm_id,
            "name": "Helm",
            "item_type": "armor",
            "slot": "head",
            "defense": 3,
        }
    )

    equipment = {"weapon": sword, "head": helm, "chest": None, "legs": None}
    db.save_monster_equipment(mid, equipment)

    # Reload and verify
    monsters = db.load_monsters()
    m = monsters[0]
    assert m["weapon_item"]["name"] == "Blade"
    assert m["head_item"]["name"] == "Helm"
    db.close()


def test_save_monster_clears_equipment(tmp_path, monkeypatch):
    """Saving empty equipment should clear the columns."""
    db = _make_db(tmp_path, monkeypatch)
    sword_id = _insert_item(db, name="Blade", slot="weapon", base_damage=5)
    mid = _insert_monster(db, name="Goblin", weapon_id=sword_id)

    # Save with all slots empty
    equipment = {"weapon": None, "head": None, "chest": None, "legs": None}
    db.save_monster_equipment(mid, equipment)

    monsters = db.load_monsters()
    assert monsters[0]["weapon_item"] is None
    db.close()


def test_save_monster_full(tmp_path, monkeypatch):
    """save_monster() should persist position, health, defeated, and equipment."""
    db = _make_db(tmp_path, monkeypatch)
    sword_id = _insert_item(db, name="Blade", slot="weapon", base_damage=5)
    mid = _insert_monster(db, name="Goblin", q=1, r=2, health=30, damage=8)

    # Create a Monster object, move it, equip it
    monster = Monster(
        {
            "id": mid,
            "current_q": 1,
            "current_r": 2,
            "name": "Goblin",
            "health": 30,
            "damage": 8,
        }
    )
    monster.q = 3
    monster.r = 4
    monster.hp = 20
    sword = Item(
        {
            "id": sword_id,
            "name": "Blade",
            "item_type": "weapon",
            "slot": "weapon",
            "base_damage": 5,
            "durability": 100,
            "max_durability": 100,
        }
    )
    monster.equip(sword)

    db.save_monster(monster)

    # Reload and verify all fields
    monsters = db.load_monsters()
    m = monsters[0]
    assert m["current_q"] == 3
    assert m["current_r"] == 4
    assert m["current_hp"] == 20
    assert m["weapon_item"]["name"] == "Blade"
    db.close()


def test_world_monster_no_equipment(tmp_path, monkeypatch):
    """A monster with no gear should load fine with empty slots."""
    db = _make_db(tmp_path, monkeypatch)
    db.cursor.execute(
        "INSERT INTO map_tiles (q, r, tile_type, is_spawn) VALUES (0, 0, 'grass', 1)"
    )
    db.conn.commit()
    sid = db.create_session(1)
    _insert_monster(db, name="Bare Goblin", q=1, r=1, health=20, damage=5)

    from gameplay.world import World

    world = World(db, sid)

    assert len(world.monsters) == 1
    goblin = world.monsters[0]
    assert goblin.damage == 5
    assert goblin.total_defense == 0
    assert all(v is None for v in goblin.equipment.values())
    db.close()
