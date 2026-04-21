from gameplay.player import Player
from gameplay.item import Item

test_data = {
    "current_q": 1,
    "current_r": 2,
    "texture_file": "player.png",
    "health": 20,
    "max_health": 150,
    "hunger": 50,
    "max_hunger": 150,
    "experience": 200,
    "hearts": 0,
}


def test_player_initialization():
    player = Player(test_data)
    assert player.q == 1
    assert player.r == 2
    # texture is now loaded from animations, not texture_file
    assert player.hp == 20
    assert player.max_hp == 150
    assert player.hunger == 50
    assert player.max_hunger == 150
    assert player.xp == 200


def test_player_take_damage():
    player = Player(test_data)
    # base_defense is 5, so damage must exceed it to deal more than 1
    player.take_damage(15)  # max(1, 15-5) = 10
    assert player.hp == 10
    assert not player.dead

    player.take_damage(15)  # max(1, 15-5) = 10
    assert player.hp == 0
    assert player.dead


def test_player_move_updates_position():
    player = Player(test_data)
    player.move(2, 3)
    # move updates logical position immediately
    assert player.q == 3
    assert player.r == 5
    # hunger is drained by engine, not by player.move
    assert player.hunger == 50


# Equipment system tests


def test_player_equip_weapon_increases_damage():
    player = Player({"current_q": 0, "current_r": 0, "health": 100, "max_health": 100})
    assert player.total_damage == 5  # base damage

    sword = Item({
        "id": 1, "name": "Sword", "item_type": "weapon",
        "slot": "weapon", "base_damage": 10,
    })
    player.equip(sword)
    assert player.total_damage == 15  # 5 base + 10 weapon
    assert player.equipment["weapon"] is sword


def test_player_unequip_weapon_reverts_damage():
    player = Player({"current_q": 0, "current_r": 0, "health": 100, "max_health": 100})
    sword = Item({
        "id": 1, "name": "Sword", "item_type": "weapon",
        "slot": "weapon", "base_damage": 10,
    })
    player.equip(sword)
    assert player.total_damage == 15  # 5 base + 10 weapon

    removed = player.unequip("weapon")
    assert removed is sword
    assert player.total_damage == 5  # back to base
    assert player.equipment["weapon"] is None


def test_player_equip_armor_increases_defense():
    player = Player({"current_q": 0, "current_r": 0, "health": 100, "max_health": 100})
    assert player.total_defense == 5  # base defense

    armor = Item({
        "id": 2, "name": "Iron Armor", "item_type": "armor",
        "slot": "armor", "defense": 12,
    })
    player.equip(armor)
    assert player.total_defense == 17  # 5 base + 12
    assert player.equipment["armor"] is armor


def test_player_defense_reduces_damage():
    player = Player({"current_q": 0, "current_r": 0, "health": 100, "max_health": 100})
    armor = Item({
        "id": 3, "name": "Iron Armor", "item_type": "armor",
        "slot": "armor", "defense": 8,
    })
    player.equip(armor)

    reduced = player.take_damage(23)  # max(1, 23-13) = 10, total_defense = 5+8 = 13
    assert reduced == 10
    assert player.hp == 90


def test_player_defense_minimum_1_damage():
    player = Player({"current_q": 0, "current_r": 0, "health": 100, "max_health": 100})
    armor = Item({
        "id": 3, "name": "Iron Armor", "item_type": "armor",
        "slot": "armor", "defense": 50,
    })
    player.equip(armor)

    reduced = player.take_damage(5)
    assert reduced == 1  # minimum 1
    assert player.hp == 99


def test_player_equip_replaces_old_item():
    player = Player({"current_q": 0, "current_r": 0, "health": 100, "max_health": 100})
    sword1 = Item({
        "id": 1, "name": "Wood Sword", "item_type": "weapon",
        "slot": "weapon", "base_damage": 3,
    })
    sword2 = Item({
        "id": 2, "name": "Iron Sword", "item_type": "weapon",
        "slot": "weapon", "base_damage": 10,
    })
    player.equip(sword1)
    assert player.total_damage == 8  # 5 base + 3

    old = player.equip(sword2)
    assert old is sword1
    assert player.total_damage == 15  # 5 base + 10


def test_player_broken_weapon_gives_no_bonus():
    player = Player({"current_q": 0, "current_r": 0, "health": 100, "max_health": 100})
    sword = Item({
        "id": 1, "name": "Worn Sword", "item_type": "weapon",
        "slot": "weapon", "base_damage": 10, "durability": 1, "max_durability": 50,
    })
    player.equip(sword)
    assert player.total_damage == 15  # 5 base + 10 weapon

    sword.degrade(1)  # durability -> 0
    assert sword.is_broken()
    assert player.total_damage == 5  # broken weapon gives no bonus, back to base


def test_non_equippable_item_returns_none():
    player = Player({"current_q": 0, "current_r": 0, "health": 100, "max_health": 100})
    bread = Item({"id": 1, "name": "Bread", "item_type": "food"})
    result = player.equip(bread)
    assert result is None
    assert all(v is None for v in player.equipment.values())
