import sqlite3
import os
import json


class DatabaseManager:
    def __init__(self, db_file="game_data.db"):
        self.db_file = db_file
        self.conn = sqlite3.connect(db_file)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()
        self._check_schema()

    def _check_schema(self):
        """Ensures the database has the required tables."""
        self.cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='game_sessions'"
        )
        if not self.cursor.fetchone():
            print("Database tables missing. Initializing from database.sql...")
            if os.path.exists("database.sql"):
                with open("database.sql", "r") as f:
                    sql_script = f.read()
                try:
                    self.cursor.executescript(sql_script)
                    self.conn.commit()
                    print("Database initialized successfully.")
                except sqlite3.Error as e:
                    print(f"Error initializing database: {e}")
            else:
                print("Error: database.sql not found. Cannot initialize database.")

    def close(self):
        self.conn.close()

# Session management

    def get_session(self, slot_id):
        self.cursor.execute(
            "SELECT * FROM game_sessions WHERE slot_number = ?", (slot_id,)
        )
        row = self.cursor.fetchone()
        return dict(row) if row else None

    def create_session(self, slot_id, char_type="warrior"):
        """Creates or resets a game session at the given slot."""
        existing = self.get_session(slot_id)

        if existing:
            sid = existing["id"]
            # Clear old session data
            self.cursor.execute(
                "DELETE FROM session_world_state WHERE session_id=?", (sid,)
            )
            self.cursor.execute("DELETE FROM player_state WHERE session_id=?", (sid,))
            self.cursor.execute("DELETE FROM inventory WHERE session_id=?", (sid,))
            self.cursor.execute(
                "UPDATE game_sessions SET character_type=?, created_at=CURRENT_TIMESTAMP WHERE id=?",
                (char_type, sid),
            )
            session_id = sid
        else:
            self.cursor.execute(
                "INSERT INTO game_sessions (slot_number, character_type) VALUES (?, ?)",
                (slot_id, char_type),
            )
            session_id = self.cursor.lastrowid

        # Initialize Player State

        default_texture = None
        player_def_dir = "assets/definitions/player"
        if os.path.exists(player_def_dir):
            for f in os.listdir(player_def_dir):
                if f.endswith(".json"):
                    try:
                        with open(os.path.join(player_def_dir, f), "r") as jf:
                            data = json.load(jf)
                            if "animations" in data and "idle" in data["animations"]:
                                default_texture = data["animations"]["idle"].get(
                                    "texture"
                                )
                            if not default_texture:
                                default_texture = data.get("texture_file")

                            if default_texture:
                                break  # Found a valid definition
                    except Exception as e:
                        print(f"Error reading player def {f}: {e}")

        # Fetch the designated spawn tile from the map + make sure initial spawn is at level 1
        self.cursor.execute("SELECT q, r FROM map_tiles WHERE is_spawn = 1 AND level = 1 LIMIT 1")
        spawn_tile = self.cursor.fetchone()
        if spawn_tile:
            start_q, start_r = spawn_tile["q"], spawn_tile["r"]
        else:
            start_q, start_r = 0, 0
            # Ensure 0,0 exists to prevent Foreign Key IntegrityErrors if no spawn was set
            self.cursor.execute("INSERT OR REPLACE INTO map_tiles (q, r, tile_type) VALUES (0, 0, 'grass')")

        self.cursor.execute(
            """INSERT INTO player_state (session_id, current_q, current_r, health, max_health, texture_file) 
               VALUES (?, ?, ?, 100, 100, ?)""",
            (session_id, start_q, start_r, default_texture),
        )
        self.initialize_level_unlocks(session_id)
        self.conn.commit()
        return session_id
    
    def initialize_level_unlocks(self, session_id):
        self.cursor.execute(
            """
            INSERT OR REPLACE INTO session_world_state (session_id, tile_id, is_unlocked, is_discovered, is_conquered)
            SELECT ?, id,
                CASE WHEN level = 1 THEN 1 ELSE 0 END,
                0,
                0
            FROM map_tiles
            """,
            (session_id,),
        )
        self.conn.commit()

# World state

    def load_world_state(self, session_id):
        """Returns all tiles with discovery status for the session."""
        query = """
        SELECT m.*, s.is_discovered, s.is_unlocked, s.is_conquered
        FROM map_tiles m
        LEFT JOIN session_world_state s ON m.id = s.tile_id AND s.session_id = ?
        """
        self.cursor.execute(query, (session_id,))
        return [dict(row) for row in self.cursor.fetchall()]

    def load_world_level(self, session_id, level):
        query = """
        SELECT m.*, s.is_discovered, s.is_unlocked, s.is_conquered
        FROM map_tiles m
        LEFT JOIN session_world_state s 
            ON m.id = s.tile_id AND s.session_id = ?
        WHERE m.level = ?
        """
        self.cursor.execute(query, (session_id, level))
        return [dict(row) for row in self.cursor.fetchall()]

    def update_discovery(self, session_id, tile_id):
        self.cursor.execute(
            """
            INSERT INTO session_world_state (session_id, tile_id, is_discovered)
            VALUES (?, ?, 1)
            ON CONFLICT(session_id, tile_id) DO UPDATE SET is_discovered=1
            """,
            (session_id, tile_id),
        )
        self.conn.commit()

    def unlock_level(self, session_id, level):
        self.cursor.execute("""
            INSERT INTO session_world_state (session_id, tile_id, is_unlocked)
            SELECT ?, id, 1
            FROM map_tiles
            WHERE level = ?
            ON CONFLICT(session_id, tile_id)
            DO UPDATE SET is_unlocked = 1
        """, (session_id, level))
        self.conn.commit()

    

# Player state

    def save_player(self, session_id, player):
        """Saves player position, health, hunger, xp, and hearts."""
        self.cursor.execute(
            """
            UPDATE player_state 
            SET current_q=?, current_r=?, health=?, hunger=?, experience=?, hearts=?
            WHERE session_id=?
            """,
            (
                player.q, 
                player.r, 
                player.hp, 
                player.hunger, 
                player.xp, 
                getattr(player, "hearts", 3), 
                session_id
            ),
        )
        self.conn.commit()

    def update_player_skin(self, session_id, skin_name):
        """Updates the player's texture_file (skin) in the database."""
        self.cursor.execute(
            "UPDATE player_state SET texture_file=? WHERE session_id=?",
            (skin_name, session_id),
        )
        self.conn.commit()

    def get_player_state(self, session_id):
        self.cursor.execute(
            "SELECT * FROM player_state WHERE session_id=?", (session_id,)
        )
        row = self.cursor.fetchone()
        if not row:
            return None
            
        p_data = dict(row)
        
        # Determine definition file based on texture_file (skin_name)
        skin_name = p_data.get("texture_file") or "archer" # We default to archer if no skin is selected (for demo purposes)
        # Standardize skin_name to filename format if needed
        if not skin_name.lower().endswith(".json"):
            skin_name = f"{skin_name.lower()}.json"
            
        def_path = os.path.join("assets", "definitions", "player", skin_name)
        
        player_def = {}
        if not os.path.exists(def_path):
            print(f"Warning: Could not find definition {def_path}, falling back to archer.json.")
            def_path = os.path.join("assets", "definitions", "player", "archer.json")

        if os.path.exists(def_path):
            try:
                with open(def_path, "r") as f:
                    player_def = json.load(f)
            except Exception as e:
                print(f"Error loading player definition {def_path}: {e}")
        else:
            print(f"Warning: Could not find fallback definition archer.json.")

        return {**player_def, **p_data}
    
    #get spawn tile for when player dies
    def get_spawn_for_level(self, level):
        self.cursor.execute("SELECT q, r FROM map_tiles WHERE is_spawn=1 AND level=?", (level,))
        row = self.cursor.fetchone()
        return (row["q"], row["r"]) if row else None

    """
    Inventory
    """

    def get_or_create_item(self, item_name):
        """Finds an item by name/filename in the DB, or creates it from its JSON definition."""
        name = item_name.replace(".json", "").replace("_", " ").title()

        self.cursor.execute("SELECT id FROM items WHERE name=?", (name,))
        row = self.cursor.fetchone()
        if row: return row["id"]
        
        # Load from json
        filename = item_name if item_name.endswith(".json") else f"{item_name}.json"
        path = os.path.join("assets", "definitions", "items", filename)
        
        with open(path, "r") as f:
            data = json.load(f)
            
            # Use JSON name if provided, otherwise stick with our formatted name
            final_name = data.get("name", name).replace(".json", "").replace("_", " ").title()

            self.cursor.execute(
                """INSERT INTO items (name, description, item_type, slot, weight, 
                   base_damage, defense, max_durability, durability, healing_amount, 
                   hunger_restore, texture_file, power_bonus, range)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    final_name,
                    data.get("description", ""),
                    data.get("item_type", "misc"),
                    data.get("slot"),
                    data.get("weight", 0),
                    data.get("base_damage", 0),
                    data.get("defense", 0),
                    data.get("max_durability", 0),
                    data.get("durability", data.get("max_durability", 0)),
                    data.get("healing_amount", 0),
                    data.get("hunger_restore", 0),
                    data.get("texture_file"),
                    data.get("power_bonus", 0),
                    data.get("range", 0)
                )
            )
        self.conn.commit()
        return self.cursor.lastrowid

    def get_item_by_id(self, item_id):
        """Returns the full data for a specific item as a dictionary."""
        self.cursor.execute("SELECT * FROM items WHERE id=?", (item_id,))
        row = self.cursor.fetchone()
        return dict(row) if row else None

    def load_inventory(self, session_id):
        """Returns all items in the player's inventory for this session."""
        query = """
        SELECT i.*, inv.id AS inventory_entry_id, inv.quantity, inv.is_equipped
        FROM inventory inv
        JOIN items i ON inv.item_id = i.id
        WHERE inv.session_id = ?
        """
        self.cursor.execute(query, (session_id,))
        return [dict(row) for row in self.cursor.fetchall()]

    def load_ground_items(self, session_id):
        """Returns all items placed on the ground in the world for this session."""
        query = """
        SELECT i.*, m.q, m.r
        FROM items i
        JOIN map_tiles m ON i.tile = m.id
        """
        
        self.cursor.execute(query)
        return [dict(row) for row in self.cursor.fetchall()]

    def add_item(self, session_id, item_id, quantity=1):
        """Adds an item to inventory. Stacks if already owned (except for equipment)."""
        # Check if the item is equippable (weapons/armor don't stack)
        self.cursor.execute("SELECT slot FROM items WHERE id=?", (item_id,))
        item_row = self.cursor.fetchone()
        is_equipment = item_row and item_row["slot"] in ("weapon", "armor")

        if not is_equipment:
            self.cursor.execute(
                "SELECT id, quantity FROM inventory WHERE session_id=? AND item_id=?",
                (session_id, item_id),
            )
            existing = self.cursor.fetchone()
            if existing:
                self.cursor.execute(
                    "UPDATE inventory SET quantity=? WHERE id=?",
                    (existing["quantity"] + quantity, existing["id"]),
                )
                
                self.conn.commit()
                return

        # Not found or is equipment: insert as new row
        self.cursor.execute(
            "INSERT INTO inventory (session_id, item_id, quantity) VALUES (?, ?, ?)",
            (session_id, item_id, quantity),
        )
        self.conn.commit()

    def remove_ground_item(self, item_id):
        """Remove an item from the ground by clearing its tile reference."""
        self.cursor.execute("UPDATE items SET tile=NULL WHERE id=?", (item_id,))
        self.conn.commit()

    def add_ground_item(self, item_id, q, r):
        """Place an item on the ground at specific q, r (editor)"""
        self.cursor.execute(
            "UPDATE items SET tile = (SELECT id FROM map_tiles WHERE q=? AND r=?) WHERE id=?",
            (q, r, item_id),
        )
        self.conn.commit()

    def remove_item(self, session_id, item_id, quantity=1):
        """Removes quantity of an item. Deletes row if quantity hits 0."""
        self.cursor.execute(
            "SELECT id, quantity FROM inventory WHERE session_id=? AND item_id=?",
            (session_id, item_id),
        )
        existing = self.cursor.fetchone()
        if not existing:
            return
        new_qty = existing["quantity"] - quantity
        if new_qty <= 0:
            self.cursor.execute("DELETE FROM inventory WHERE id=?", (existing["id"],))
        else:
            self.cursor.execute(
                "UPDATE inventory SET quantity=? WHERE id=?",
                (new_qty, existing["id"]),
            )
        self.conn.commit()

    def toggle_equip(self, session_id, item_id):
        """Toggles is_equipped for an equippable item.
        When equipping, unequips any other item in the same slot first."""
        self.cursor.execute(
            "SELECT inv.id, inv.is_equipped, i.slot FROM inventory inv "
            "JOIN items i ON inv.item_id = i.id "
            "WHERE inv.session_id=? AND inv.item_id=?",
            (session_id, item_id),
        )
        row = self.cursor.fetchone()
        if not row:
            return

        if row["is_equipped"]:
            # Unequip
            self.cursor.execute(
                "UPDATE inventory SET is_equipped=0 WHERE id=?", (row["id"],)
            )
        else:
            # Unequip any other item in the same slot first
            slot = row["slot"]
            if slot:
                self.cursor.execute(
                    "UPDATE inventory SET is_equipped=0 "
                    "WHERE session_id=? AND is_equipped=1 AND item_id IN "
                    "(SELECT id FROM items WHERE slot=?)",
                    (session_id, slot),
                )
            # Equip this item
            self.cursor.execute(
                "UPDATE inventory SET is_equipped=1 WHERE id=?", (row["id"],)
            )
        self.conn.commit()

    def get_equipped_items(self, session_id):
        """Returns all currently equipped items for the session."""
        query = """
        SELECT i.*, inv.is_equipped
        FROM inventory inv
        JOIN items i ON inv.item_id = i.id
        WHERE inv.session_id = ? AND inv.is_equipped = 1
        """
        self.cursor.execute(query, (session_id,))
        return [dict(row) for row in self.cursor.fetchall()]


# Chests

    def load_chests(self, session_id):
        """Returns all persistent chests for the session."""
        self.cursor.execute(
            "SELECT * FROM session_chests WHERE session_id = ?", (session_id,)
        )
        rows = self.cursor.fetchall()
        results = []
        for row in rows:
            d = dict(row)
            if d.get("items_json"):
                try:
                    d["items"] = json.loads(d["items_json"])
                except Exception:
                    d["items"] = []
            else:
                d["items"] = []
            results.append(d)
        return results

    def save_chest(self, session_id, q, r, chest_type, items):
        """Persists a chest and its contents to the session state.
        
        items: list of Item objects (we extract their relevant data).
        """
        # Convert items to a list of dicts for serialization
        item_list = []
        for item in items:
            item_list.append({
                "id": item.id,
                "name": item.name,
                "item_type": item.type,
                "texture_file": item.texture,
                "base_damage": item.damage_bonus,
                "defense": item.defense,
                "healing_amount": item.healing_amount,
                "hunger_restore": item.hunger_restore,
                "durability": item.durability,
                "max_durability": item.max_durability,
                "range": item.range
            })
        
        items_json = json.dumps(item_list)
        
        self.cursor.execute(
            """INSERT INTO session_chests (session_id, q, r, chest_type, items_json)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(session_id, q, r) DO UPDATE SET
               chest_type=excluded.chest_type, items_json=excluded.items_json""",
            (session_id, q, r, chest_type, items_json)
        )
        self.conn.commit()

    def delete_chest(self, session_id, q, r):
        """Removes a chest from persistent state."""
        self.cursor.execute(
            "DELETE FROM session_chests WHERE session_id=? AND q=? AND r=?",
            (session_id, q, r)
        )
        self.conn.commit()


# Monsters

    def load_monsters(self, session_id=None):
        """Loads all alive monsters, merging their DB state with JSON definitions."""
        query = """
        SELECT m.*,
               wi.id AS wi_id, wi.name AS wi_name, wi.item_type AS wi_item_type, wi.slot AS wi_slot, 
               wi.base_damage AS wi_base_damage, wi.defense AS wi_defense, wi.durability AS wi_durability, 
               wi.max_durability AS wi_max_durability, wi.range AS wi_range,
               hi.id AS hi_id, hi.name AS hi_name, hi.item_type AS hi_item_type, hi.slot AS hi_slot,
               hi.base_damage AS hi_base_damage, hi.defense AS hi_defense, hi.durability AS hi_durability,
               hi.max_durability AS hi_max_durability, hi.range AS hi_range,
               ci.id AS ci_id, ci.name AS ci_name, ci.item_type AS ci_item_type, ci.slot AS ci_slot,
               ci.base_damage AS ci_base_damage, ci.defense AS ci_defense, ci.durability AS ci_durability,
               ci.max_durability AS ci_max_durability, ci.range AS ci_range,
               li.id AS li_id, li.name AS li_name, li.item_type AS li_item_type, li.slot AS li_slot,
               li.base_damage AS li_base_damage, li.defense AS li_defense, li.durability AS li_durability,
               li.max_durability AS li_max_durability, li.range AS li_range
        FROM monsters m
        LEFT JOIN items wi ON m.weapon_item_id = wi.id
        LEFT JOIN items hi ON m.head_item_id = hi.id
        LEFT JOIN items ci ON m.chest_item_id = ci.id
        LEFT JOIN items li ON m.legs_item_id = li.id
        WHERE m.is_defeated = 0
        """
        self.cursor.execute(query)
        results = []

        monster_def_dir = os.path.join("assets", "definitions", "monsters")

        for db_record in self.cursor.fetchall():
            row = dict(db_record)
            
            # Load JSON definition if it exists
            definition = {}
            name = row.get("name")
            if name:
                path = os.path.join(monster_def_dir, name)
                if os.path.exists(path):
                    with open(path, "r") as f:
                        definition = json.load(f)

            equipment = {}
            for col_prefix, slot_key in [("wi", "weapon"), ("hi", "head"), ("ci", "chest"), ("li", "legs")]:
                if row.get(f"{col_prefix}_id"):
                    equipment[f"{slot_key}_item"] = {
                        "id": row[f"{col_prefix}_id"],
                        "name": row[f"{col_prefix}_name"],
                        "item_type": row[f"{col_prefix}_item_type"],
                        "slot": row[f"{slot_key}_slot"],
                        "base_damage": row[f"{col_prefix}_base_damage"],
                        "defense": row[f"{col_prefix}_defense"],
                        "durability": row[f"{col_prefix}_durability"],
                        "max_durability": row[f"{col_prefix}_max_durability"],
                        "range": row[f"{col_prefix}_range"],
                    }
                else:
                    equipment[f"{slot_key}_item"] = None

            # Combine: Default -> JSON -> DB row -> equipment
            monster_config = {**definition, **row, **equipment}

            # Ensure minimal stats
            monster_config["health"] = row.get("health") or definition.get("default_health", 50)
            monster_config["current_hp"] = row.get("current_hp") if row.get("current_hp") is not None else monster_config["health"]
            monster_config["damage"] = row.get("damage") or definition.get("default_damage", 10)

            results.append(monster_config)

        return results

    def save_monster_equipment(self, monster_id, equipment):
        """Persist a monster's equipment slots to DB.

        equipment: dict like {"weapon": Item|None, "head": Item|None, ...}
        """
        weapon_id = equipment.get("weapon").id if equipment.get("weapon") else None
        head_id = equipment.get("head").id if equipment.get("head") else None
        chest_id = equipment.get("chest").id if equipment.get("chest") else None
        legs_id = equipment.get("legs").id if equipment.get("legs") else None

        self.cursor.execute(
            """UPDATE monsters
               SET weapon_item_id=?, head_item_id=?, chest_item_id=?, legs_item_id=?
               WHERE id=?""",
            (weapon_id, head_id, chest_id, legs_id, monster_id),
        )
        self.conn.commit()

    def save_monster(self, monster):
        """Save monster position, health, defeated status, and equipment."""
        self.cursor.execute(
            """UPDATE monsters
               SET current_q=?, current_r=?, current_hp=?, is_defeated=?
               WHERE id=?""",
            (monster.q, monster.r, monster.hp, int(monster.dead), monster.id),
        )
        self.save_monster_equipment(monster.id, monster.equipment)
        self.conn.commit()

    def get_monster_at(self, q, r):
        """Get a single monster attributes by q, r coordinates."""
        query = "SELECT * FROM monsters WHERE current_q = ? AND current_r = ?"
        self.cursor.execute(query, (q, r))
        row = self.cursor.fetchone()
        return dict(row) if row else None

    def add_monster(self, name, q, r, hp, dmg, level):
        """Insert a new monster into the DB (Editor)"""
        self.cursor.execute(
            """INSERT INTO monsters (name, current_q, current_r, health, current_hp, damage, level, is_defeated)
               VALUES (?, ?, ?, ?, ?, ?, ?, 0)""",
            (name, q, r, hp, hp, dmg, level),
        )
        self.conn.commit()

    def update_monster_stats(self, q, r, hp, dmg):
        """Updates health and damage of a monster at a q/r"""
        self.cursor.execute(
            "UPDATE monsters SET health = ?, damage = ? WHERE current_q = ? AND current_r = ?",
            (hp, dmg, q, r),
        )
        self.conn.commit()

    def update_monster_level(self, q, r, level):
        """Update a monster's level"""
        self.cursor.execute(
            "UPDATE monsters SET level = ? WHERE current_q = ? AND current_r = ?",
            (level, q, r),
        )
        self.conn.commit()

    def delete_monster(self, q, r):
        """Remove a monster from the DB (Editor."""
        self.cursor.execute("DELETE FROM monsters WHERE current_q = ? AND current_r = ?", (q, r))
        self.conn.commit()


# Map management

    def get_tile(self, q, r):
        self.cursor.execute("SELECT * FROM map_tiles WHERE q=? AND r=?", (q, r))
        row = self.cursor.fetchone()
        return dict(row) if row else None

    def get_all_tiles(self):
        self.cursor.execute("SELECT * FROM map_tiles")
        return [dict(row) for row in self.cursor.fetchall()]

    def save_tile(self, data):
        """
        data: dict containing tile attributes
        """
        if data.get("is_spawn"):
            lvl = data.get("level", 1)
            self.cursor.execute("UPDATE map_tiles SET is_spawn = 0 WHERE level = ?", (lvl,))

        self.cursor.execute(
            """
            INSERT INTO map_tiles (q, r, tile_type, level, texture_file, prop_texture_file, prop_scale, prop_x_shift, prop_y_shift, is_spawn, is_permanently_passable)
            VALUES (:q, :r, :tile_type, :level, :texture_file, :prop_texture_file, :prop_scale, :prop_x_shift, :prop_y_shift, :is_spawn, :is_permanently_passable)
            ON CONFLICT(q,r) DO UPDATE SET
                tile_type=excluded.tile_type, level=excluded.level, texture_file=excluded.texture_file,
                prop_texture_file=excluded.prop_texture_file, 
                prop_scale=excluded.prop_scale, prop_x_shift=excluded.prop_x_shift, prop_y_shift=excluded.prop_y_shift,
                is_spawn=excluded.is_spawn, is_permanently_passable=excluded.is_permanently_passable
            """,
            data,
        )
        self.conn.commit()

    def delete_tile(self, q, r):
        self.cursor.execute("DELETE FROM map_tiles WHERE q=? AND r=?", (q, r))
        self.conn.commit()


# Castle management

    def get_map_castles(self):
        self.cursor.execute("SELECT * FROM map_castles")
        return [dict(row) for row in self.cursor.fetchall()]

    def get_castle_spawns(self, castle_id=None):
        if castle_id is not None:
            self.cursor.execute("SELECT * FROM map_castle_spawns WHERE castle_id=?", (castle_id,))
        else:
            self.cursor.execute("SELECT * FROM map_castle_spawns")
        return [dict(row) for row in self.cursor.fetchall()]

    def add_map_castle(self, q, r, level, asset_file=None):
        self.cursor.execute(
            "INSERT INTO map_castles (q, r, level, asset_file) VALUES (?, ?, ?, ?)",
            (q, r, level, asset_file)
        )
        self.conn.commit()
        return self.cursor.lastrowid

    def add_castle_spawn(self, castle_id, q, r, monster_name, health, damage):
        self.cursor.execute(
            """INSERT INTO map_castle_spawns (castle_id, q, r, monster_name, health, damage)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (castle_id, q, r, monster_name, health, damage)
        )
        self.conn.commit()

    def delete_map_castle(self, q, r):
        # We find the castle by q, r and delete it. CASCADE will delete its spawns.
        self.cursor.execute("DELETE FROM map_castles WHERE q=? AND r=?", (q, r))
        self.conn.commit()

    def delete_castle_spawn(self, q, r):
        self.cursor.execute("DELETE FROM map_castle_spawns WHERE q=? AND r=?", (q, r))
        self.conn.commit()

    def get_session_castles(self, session_id):
        self.cursor.execute("SELECT * FROM session_castles WHERE session_id=?", (session_id,))
        return [dict(row) for row in self.cursor.fetchall()]

    def update_session_castle(self, session_id, castle_id, is_spawned=None, is_conquered=None):
        # Fetch existing or create new
        self.cursor.execute("SELECT * FROM session_castles WHERE session_id=? AND castle_id=?", (session_id, castle_id))
        row = self.cursor.fetchone()
        
        if not row:
            # Insert first
            self.cursor.execute(
                "INSERT INTO session_castles (session_id, castle_id, is_spawned, is_conquered) VALUES (?, ?, ?, ?)",
                (session_id, castle_id, 0, 0)
            )
            row = {"is_spawned": 0, "is_conquered": 0}
        
        new_spawn_flag = is_spawned if is_spawned is not None else row["is_spawned"]
        new_conquest_flag = is_conquered if is_conquered is not None else row["is_conquered"]
        
        self.cursor.execute(
            "UPDATE session_castles SET is_spawned=?, is_conquered=? WHERE session_id=? AND castle_id=?",
            (int(new_spawn_flag), int(new_conquest_flag), session_id, castle_id)
        )
        self.conn.commit()
