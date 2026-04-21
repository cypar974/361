"""Game engine — the coordinator between input, world, and database.

GameEngine sits between the UI layer (game_window.py, which feeds it
action strings like "MOVE_NORTH" or "INTERACT") and the domain layer
(World, Player, Monster, Chest, Item). It owns the turn loop: one call
to `run_turn` handles player input, advances player state, runs monster
AI, and writes everything back to the SQLite save.

Design patterns in this module:
  - Command pattern: handle_input dispatches on action strings, each of
    which maps to a discrete gameplay command.
  - Facade: the rest of the game interacts with a single GameEngine
    instead of poking at World/Player/DB directly.
  - Resource lock guard: every pickup/use routes through
    world.resource_locks so interleaved operations can't double-award
    or double-consume an item.
"""

import time
from gameplay.world import World
from gameplay.item import Item
from gameplay.chest import Chest
import pygame
import os
import random


class GameEngine:
    """Turn-based coordinator that handles movement, combat, and loot."""


    def __init__(self, db, session_id):
        self.db = db
        self.session_id = session_id
        self.world = World(db, session_id)
        self.world.update_fog_of_war()
        self.show_inventory = False  # toggle flag
        self.selected_index = 0  # cursor position in inventory
        if self.world.player:
            self.world.player.load_inventory(self.db, self.session_id)
            self.world.sync_inventory_resource_locks()  # Sync resource locks after loading inventory
        self.start_time = time.time()
        self.monsters_need_turn = (
            False  # Animation lock: A mark waiting for the monster to act
        )
        # Queue of (name, count) tuples to show as floating pickup text.
        # The UI layer drains this and renders them with a fade.
        self.loot_notifications_queue = []

        self.level_up_sound = pygame.mixer.Sound(
            os.path.join("assets", "music", "level_up.mp3")
        )
        self.level_up_sound.set_volume(0.6)

    def handle_input(self, action):
        player = self.world.player

        if player is None:
            return "NO_PLAYER"
        
        if player.dead:
            if player.hearts <= 0:
                return "GAME_OVER"
            
            else:
                return "TURN_TAKEN"

        # --- Inventory screen controls ---
        if self.show_inventory:
            if action == "INVENTORY":
                self.show_inventory = False
                player.set_anim_state("idle", reset_frame=True)
                return "NO_ACTION"
            if action == "MOVE_NORTH" and self.selected_index > 0:
                self.selected_index -= 1
            elif (
                action == "MOVE_SOUTH"
                and self.selected_index < len(player.inventory) - 1
            ):
                self.selected_index += 1
            elif action == "INTERACT":
                self.use_selected_item()
            elif action == "MOVE_WEST":
                self.drop_selected_item()
            return "NO_ACTION"

        # --- Normal gameplay controls ---
        if action == "INTERACT":
            # Priority 1: open an adjacent chest
            if self.try_open_adjacent_chest():
                return "TURN_TAKEN"
            # Priority 2: pick up items on the player's tile
            picked_up = self.pick_up_ground_items()
            return "TURN_TAKEN" if picked_up else "NO_ACTION"

        move_map = {
            "MOVE_NORTH": (0, -1),
            "MOVE_SOUTH": (0, 1),
            "MOVE_WEST": (-1, 0),
            "MOVE_EAST": (1, 0),
            "MOVE_SW": (-1, 1),
            "MOVE_NE": (1, -1),
        }
        if action in move_map:
            dq, dr = move_map[action]
            player = self.world.player

            if player is None:
                return "NO_PLAYER"

            # if target hex has a monster, then player attacks
            for i in range(1, player.range + 1):
                target_q = player.q + dq * i
                target_r = player.r + dr * i
                monster = self.world.get_monster_at(target_q, target_r)
                # Do not trigger attack for projectile
                if monster is not None and getattr(monster, "is_targetable", True):
                    damage = player.attack_monster(monster)

                    weapon = player.equipment.get("weapon")
                    if weapon and weapon.type == "ranged":
                        arrows = [
                            item for item in player.inventory if item.type == "ammo"
                        ]
                        if len(arrows) > 0:
                            arrow = arrows[0]
                            damage += arrow.damage_bonus
                            player.inventory.remove(arrow)
                            self.db.remove_item(self.session_id, arrow.id, quantity=1)

                    self.db.save_monster(monster)
                    self.db.save_player(self.session_id, player)

                    print(f"Player attacked {monster.name} for {damage} damage")
                    return "TURN_TAKEN"

            # if no monster, then try to move
            moved = self.attempt_move(dq, dr)
            return "TURN_TAKEN" if moved else "NO_ACTION"

        if action == "INVENTORY":
            self.show_inventory = True
            self.selected_index = 0
            if player:
                player.load_inventory(self.db, self.session_id)
                self.world.sync_inventory_resource_locks()  # Sync resource locks when opening inventory
            return "NO_ACTION"

        return "NO_ACTION"

    def use_selected_item(self):
        """Use or equip/unequip the currently selected inventory item."""
        # get the player and check if selected index is valid
        player = self.world.player
        if not player or self.selected_index >= len(player.inventory):
            return False

        # get the item and its resource lock if it has one
        item = player.inventory[self.selected_index]
        resource_id = item.resource_id
        if resource_id is not None:
            # ensure the resource lock exists before trying to acquire it
            self.world.resource_locks.add_resource(resource_id)
            # try to acquire the lock
            if not self.world.resource_locks.acquire(resource_id):
                return False

        used = player.use_item(self.selected_index, self.db, self.session_id)
        if resource_id is not None:
            if used and item.type == "food":
                self.world.resource_locks.consume(resource_id)
            else:
                self.world.resource_locks.release(resource_id)

        if used:
            # Sync resource locks after using item\
            self.world.sync_inventory_resource_locks()

        # If the item was consumed or equipped, we may need to adjust the selected index if it goes out of bounds
        if self.selected_index >= len(player.inventory):
            self.selected_index = max(0, len(player.inventory) - 1)
        return used

    def drop_selected_item(self):
        """Drop one of the selected item from inventory."""
        player = self.world.player
        if not player:
            return
        player.drop_item(self.selected_index, self.db, self.session_id)
        if self.selected_index >= len(player.inventory):
            self.selected_index = max(0, len(player.inventory) - 1)

        # Refresh world state so item appears on ground
        self.world.load_ground_items()
        self.world.sync_inventory_resource_locks()

    def try_open_adjacent_chest(self):
        """Open the first unopened chest adjacent to the player. Returns True
        if a chest was opened (the opening animation started)."""
        player = self.world.player
        if not player:
            return False

        neighbors = [
            (0, -1),
            (0, 1),
            (-1, 0),
            (1, 0),
            (-1, 1),
            (1, -1),
        ]
        for dq, dr in neighbors:
            chest = self.world.get_chest_at(player.q + dq, player.r + dr)
            if chest is not None and not chest.opened:
                chest.open_chest()
                self._award_chest_items(chest)
                return True
        return False

    def _award_chest_items(self, chest):
        """Add each item stored in the chest to the player's inventory."""
        player = self.world.player
        if player is None or not chest.items:
            return

        # Tally items by name so duplicates collapse into "Bread x2"
        counts = {}
        for item in chest.items:
            if getattr(item, "id", None) is None and hasattr(item, "_def_name"):
                item.id = self.db.get_or_create_item(item._def_name)
            if getattr(item, "id", None) is not None:
                self.db.add_item(self.session_id, item.id)
            counts[item.name] = counts.get(item.name, 0) + 1

        # Push one notification per distinct item name, preserving order
        seen = []
        for item in chest.items:
            if item.name not in seen:
                seen.append(item.name)
                self.loot_notifications_queue.append((item.name, counts[item.name]))

        # Empty the chest so items aren't awarded twice
        chest.items = []
        # Persistent state by removing the chest from DB
        if hasattr(self.db, "delete_chest"):
            self.db.delete_chest(self.session_id, chest.q, chest.r)

        # Refresh the player's inventory
        player.load_inventory(self.db, self.session_id)
        self.world.sync_inventory_resource_locks()

    def pick_up_ground_items(self):
        """Pick up all ground items on the player's current tile."""
        player = self.world.player
        
        if not player:
            return False
        
        neighbors = [
            (0, 0),
            (0, -1),
            (0, 1),
            (-1, 0),
            (1, 0),
            (-1, 1),
            (1, -1),
        ]

        for dq, dr in neighbors:
            ground_items = list(self.world.get_ground_items_at(player.q + dq, player.r + dr))
            if not ground_items:
                continue

            picked_up_any = False
            counts = {}  # For notifications: {item_name: count}

            # if any item is successfully picked up add to inventory and remove from ground.
            for item in ground_items:
                resource_id = item.resource_id
                if resource_id is None:
                    continue

                # ensure the resource lock exists before trying to acquire it
                self.world.resource_locks.add_resource(resource_id)
                if not self.world.resource_locks.acquire(resource_id):
                    continue

                try:
                    self.db.add_item(self.session_id, item.id)
                    self.db.remove_ground_item(item.id)
                    self.world.resource_locks.consume(resource_id)

                    # Track for notification
                    counts[item.name] = counts.get(item.name, 0) + 1
                    picked_up_any = True
                except Exception as e:
                    print(f"Error picking up ground item {item.name}: {e}")
                    self.world.resource_locks.release(resource_id)

            # fail if we couldn't pick up any items
            if not picked_up_any:
                return False

            # Add notifications to the queue
            for item_name, count in counts.items():
                self.loot_notifications_queue.append((item_name, count))

            # reload inventory and sync resource locks
            player.load_inventory(self.db, self.session_id)
            self.world.load_ground_items()
            self.world.sync_inventory_resource_locks()
            return True

    def attempt_move(self, dq, dr):
        """Try to move the player by (dq, dr). Returns True if move succeeded, False if blocked."""
        player = self.world.player
        target_q = player.q + dq
        target_r = player.r + dr

        if not self.world.is_passable(target_q, target_r):
            return False

        old_q, old_r = player.q, player.r

        player.move(dq, dr)
        self.world.update_fog_of_war()

        try:
            self.db.save_player(self.session_id, player)
        except Exception:
            # Revert move if DB save fails (e.g. file lock)
            player.q = old_q
            player.r = old_r
            self.world.update_fog_of_war()
            return False

        return True

    def drop_monster_loot(self, monster):
        """Spawn a loot chest at a freshly-killed monster's tile.

        Called once per monster death.
        If the monster's loot roll produces nothing, no chest is spawned
        the flag is still set so we don't re-roll every frame.
        """
        if monster.is_alive():
            return
        if getattr(monster, "death_loot_dropped", False):
            return

        # Saves the monster as defeated in the DB immediately which
        # prevents the reappearing monster bug if the player quits before the next turn
        self.db.save_monster(monster)

        drops = monster.on_death()
        # Strip any Nones that may have slipped through the drop roll
        drops = [d for d in drops if d is not None]

        # Don't spawn an empty chest. Mark loot as handled so we
        # don't keep re-rolling on every frame.
        if not drops:
            monster.death_loot_dropped = True
            return

        # Resolve each item's id upfront so it's ready when the
        # chest is opened.
        for item in drops:
            if getattr(item, "id", None) is None and hasattr(item, "_def_name"):
                try:
                    item.id = self.db.get_or_create_item(item._def_name)
                except Exception:
                    # Definition missing — skip this item but keep the others.
                    item.id = None

        # Filter out anything we couldn't resolve
        drops = [d for d in drops if getattr(d, "id", None) is not None]
        if not drops:
            monster.death_loot_dropped = True
            return

        # Spawn a chest at the monster's tile holding the loot.
        loot_chest = Chest(monster.q, monster.r, "brown_chest", items=drops)
        self.world.chests.append(loot_chest)

        # Persistent state by saving the chest to DB
        if hasattr(self.db, "save_chest"):
            self.db.save_chest(
                self.session_id, monster.q, monster.r, "brown_chest", drops
            )

        monster.death_loot_dropped = True

    def update(self):
        player = self.world.player

        if player is None:
            return "NO_PLAYER"

        if player.dead and player.hearts <= 0:
            return "GAME_OVER"

        if player.hunger > 0:
            player.hunger -= 1

        if player.hunger <= 0:
            player.hunger = 0
            if player.hp > 0:
                player.take_damage(5)

        if player.hp <= 0:
            player.hp = 0
            player.dead = True
            player.hearts -= 1

            if player.hearts <= 0:
                player.hearts = 0
                self.db.save_player(self.session_id, player)
                return "GAME_OVER"
            
            #If still has hearts left
            spawn = self.db.get_spawn_for_level(self.world.current_level)
            if spawn:
                player.q, player.r = spawn
                player.hp = player.max_hp
                player.hunger = player.max_hunger
                player.dead = False
                
                self.db.save_player(self.session_id, player)

                return "RESPAWN"

        self.db.save_player(self.session_id, player)

        # Castle check
        self.world.check_castle_proximity()

        # Check if spawned castles are conquered
        for castle in self.world.castles:
            if (
                castle.level == self.world.current_level
                and castle.is_spawned
                and not castle.is_conquered
            ):
                # Find all monsters for this castle
                alive_castle_monsters = [
                    m
                    for m in self.world.monsters
                    if m.castle_id == castle.id and m.is_alive()
                ]
                if not alive_castle_monsters:
                    # All dead = conquered
                    castle.is_conquered = True
                    self.db.update_session_castle(
                        self.session_id, castle.id, is_conquered=1
                    )
                    print(f"Castle {castle.id} Conquered!")

                    self.spawn_assistant_reward(castle)

        return "UPDATED"

    def spawn_assistant_reward(self, castle):
        """When the castle is conquered, a assistant will be generated beside the castle as a reward"""
        if len(self.world.assistants) >= 2:
            return
        
        spawn_q, spawn_r = castle.q, castle.r
        
        # Find a free space to spawn
        directions = [(1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1)]
        for dq, dr in directions:
            nq, nr = castle.q + dq, castle.r + dr
            if self.world.is_passable(nq, nr):
                spawn_q, spawn_r = nq, nr
                break

        # Randomly choose an assistant
        assistant_pool = ["warrior_assistant", "archer_assistant", "monk_assistant"]
        chosen_name = random.choice(assistant_pool)

        self.db.add_monster(
            chosen_name,
            spawn_q, spawn_r, 
            100, 10, castle.level 
        )
        
        self.world.load_monsters()
                
    def process_monster_turns(self):
        """
        Run one monster turn for all alive monsters after the player takes a turn.
        """
        player = self.world.player
        if not player or player.dead:
            return []

        logs = []

        for monster in self.world.monsters:
            if not monster.is_alive():
                continue

            if monster.level != self.world.current_level:
                continue

            tile = self.world.get_tile(monster.q, monster.r)
            if not tile or not tile.unlocked:
                continue

            result = monster.decide_and_act(self.world, player)
            logs.append(result)

            # Save each monster after it acts
            if hasattr(self.db, "save_monster"):
                self.db.save_monster(monster)

            # Stop early if player died during monster actions
            if player.dead:
                break

        # Save player state too, because monsters may have damaged the player
        self.db.save_player(self.session_id, player)
        return logs

    def run_turn(self, action):
        result = self.handle_input(action)

        if result == "GAME_OVER":
            return "GAME_OVER"

        if result != "TURN_TAKEN":
            return "NO_ACTION"

        self.monsters_need_turn = True

        game_state = self.update()
        if game_state == "GAME_OVER":
            return "GAME_OVER"
        
        if game_state == "RESPAWN":
            return "RESPAWN"

        if self.check_level_completed():
            if self.world.current_level == self.world.get_max_level():
                return "WIN"
            
            unlocked = self.world.unlock_next_level()
            
            if unlocked:
                self.level_up_sound.play()
                self.world.player.increase_player_hp(50)

        self._save_all_monsters()
        return "TURN_DONE"

    def _save_all_monsters(self):
        """Saves the state of every monster in the world to the DB
        every game loop. This ensures that deaths are persistent.
        """
        for monster in self.world.monsters:
            self.db.save_monster(monster)
        for assistant in getattr(self.world, "assistants", []):
            self.db.save_monster(assistant)
            
    def check_level_completed(self):
        current_level_castles = [
            c for c in self.world.castles if c.level == self.world.current_level
        ]

        if current_level_castles:
           return current_level_castles[0].is_conquered
        else:
            # Fallback for levels without castles: kill all wandering monsters (OG way)
            current_level_monsters = [
                m
                for m in self.world.monsters
                if m.level == self.world.current_level and m.is_alive()
            ]
            return len(current_level_monsters) == 0

