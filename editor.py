import tkinter as tk
from tkinter import ttk, filedialog, messagebox, Canvas, simpledialog
import sqlite3
import shutil
import os
import json
import math
from PIL import Image, ImageTk




class Config:
    GAME_SCALE = 3
    BASE_HEX_RADIUS = 16
    HEX_SIZE = BASE_HEX_RADIUS * GAME_SCALE  # 48 pixels
    HEX_ASPECT_RATIO = 0.87
    CALIB_OFFSET_Y = 16 * GAME_SCALE
    GRID_RANGE = 50
    MAP_WIDTH = 7000
    MAP_HEIGHT = 7000
    CENTER_X = MAP_WIDTH // 2
    CENTER_Y = MAP_HEIGHT // 2
    ASSET_DIR = "assets"
    DIRS = {
        "tile": "assets/definitions/tiles",
        "prop": "assets/definitions/props",
        "monster": "assets/definitions/monsters",
        "player": "assets/definitions/player",
        "item": "assets/definitions/items",
    }
    # Constants for Keys
    KEY_SCALE = 1.75
    KEY_X_OFFSET = 0
    KEY_Y_OFFSET = -25


for d in Config.DIRS.values():
    os.makedirs(d, exist_ok=True)
if not os.path.exists(Config.ASSET_DIR):
    os.makedirs(Config.ASSET_DIR)


class HexEngine:
    @staticmethod
    def hex_to_pixel(q, r):
        size = Config.HEX_SIZE
        x = size * (3 / 2 * q)
        y = size * math.sqrt(3) * (r + q / 2)
        return x, y * Config.HEX_ASPECT_RATIO

    @staticmethod
    def pixel_to_hex(px, py):
        x = px
        y = py / Config.HEX_ASPECT_RATIO
        size = Config.HEX_SIZE
        q = (2.0 / 3 * x) / size
        r = (-1.0 / 3 * x + math.sqrt(3) / 3 * y) / size
        return HexEngine.cube_round(q, r, -q - r)

    @staticmethod
    def cube_round(frac_q, frac_r, frac_s):
        q, r, s = round(frac_q), round(frac_r), round(frac_s)
        q_diff, r_diff, s_diff = abs(q - frac_q), abs(r - frac_r), abs(s - frac_s)
        if q_diff > r_diff and q_diff > s_diff:
            q = -r - s
        elif r_diff > s_diff:
            r = -q - s
        else:
            s = -q - r
        return int(q), int(r)

    @staticmethod
    def get_hex_polygon(cx, cy):
        points = []
        for i in range(6):
            angle_rad = math.radians(60 * i)
            vx = Config.HEX_SIZE * math.cos(angle_rad)
            vy = Config.HEX_SIZE * math.sin(angle_rad)
            points.append(cx + vx)
            points.append(cy + (vy * Config.HEX_ASPECT_RATIO))
        return points


class DatabaseManager:
    def __init__(self, db_file="game_data.db"):
        self.conn = sqlite3.connect(db_file)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()
        self.cursor.execute("PRAGMA foreign_keys = ON")
        self._init_schema()

    def _init_schema(self):
        if os.path.exists("database.sql"):
            with open("database.sql", "r") as f:
                sql_script = f.read()
            try:
                self.cursor.executescript(sql_script)
                self.conn.commit()
            except sqlite3.Error as e:
                print(f"Error initializing database from sql: {e}")
                
        # Migration: Ensure asset_file exists in map_castles
        try:
            self.cursor.execute("ALTER TABLE map_castles ADD COLUMN asset_file TEXT")
            self.conn.commit()
        except sqlite3.OperationalError:
            pass # Already exists

        try:
            self.cursor.execute("ALTER TABLE monsters ADD COLUMN current_hp INTEGER")
            self.conn.commit()
            self.cursor.execute("UPDATE monsters SET current_hp = health WHERE current_hp IS NULL")
            self.conn.commit()
        except sqlite3.OperationalError:
            pass  # column already exists

        try:
            self.cursor.execute("ALTER TABLE monsters ADD COLUMN level INTEGER DEFAULT 1")
            self.conn.commit()
        except sqlite3.OperationalError:
            pass  # column already exists

    def get_tile(self, q, r):
        self.cursor.execute("SELECT * FROM map_tiles WHERE q=? AND r=?", (q, r))
        row = self.cursor.fetchone()
        return dict(row) if row else None

    def get_all_tiles(self):
        self.cursor.execute("SELECT * FROM map_tiles")
        return [dict(row) for row in self.cursor.fetchall()]

    def clear_spawn_points(self): # One spawn per level? For now assume global spawn
        pass 
        # self.cursor.execute("UPDATE map_tiles SET is_spawn = 0")
        # self.conn.commit()

    def save_tile(self, data):
        if data.get("is_spawn"):
            lvl = data.get("level", 1)
            self.cursor.execute("UPDATE map_tiles SET is_spawn = 0 WHERE level = ?", (lvl,))
        
        self.cursor.execute(
            """
            INSERT INTO map_tiles (q, r, tile_type, texture_file, prop_texture_file, prop_scale, prop_x_shift, prop_y_shift, is_spawn, level, is_permanently_passable)
            VALUES (:q, :r, :tile_type, :texture_file, :prop_texture_file, :prop_scale, :prop_x_shift, :prop_y_shift, :is_spawn, :level, :is_permanently_passable)
            ON CONFLICT(q,r) DO UPDATE SET
                tile_type=excluded.tile_type, texture_file=excluded.texture_file,
                prop_texture_file=excluded.prop_texture_file, 
                prop_scale=excluded.prop_scale, prop_x_shift=excluded.prop_x_shift, prop_y_shift=excluded.prop_y_shift,
                is_spawn=excluded.is_spawn,
                level=excluded.level,
                is_permanently_passable=excluded.is_permanently_passable
        """,
            data,
        )
        self.conn.commit()

    def delete_tile(self, q, r):
        self.cursor.execute("DELETE FROM map_tiles WHERE q=? AND r=?", (q, r))
        self.conn.commit()

    # --- Monster Methods ---
    def get_all_monsters(self):
        self.cursor.execute("SELECT * FROM monsters")
        return [dict(row) for row in self.cursor.fetchall()]

    def get_monster_at(self, q, r):
        self.cursor.execute("SELECT * FROM monsters WHERE current_q=? AND current_r=?", (q, r))
        row = self.cursor.fetchone()
        return dict(row) if row else None

    def add_monster(self, name, q, r, hp, damage, level=1):
        self.cursor.execute(
            "INSERT INTO monsters (name, current_q, current_r, health, current_hp, damage, level) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (name, q, r, hp, hp, damage, level)
        )
        self.conn.commit()

    def update_monster_stats(self, q, r, health, damage):
        self.cursor.execute(
            "UPDATE monsters SET health=?, current_hp=?, damage=? WHERE current_q=? AND current_r=?",
            (health, health, damage, q, r)
        )
        self.conn.commit()

    # used for auto upodate on level change of tile
    def update_monster_level(self, q, r, level):
        self.cursor.execute("UPDATE monsters SET level=? WHERE current_q=? AND current_r=?", (level, q, r))
        self.conn.commit()

    def delete_monsters_at(self, q, r):
        self.cursor.execute("DELETE FROM monsters WHERE current_q=? AND current_r=?", (q, r))
        self.conn.commit()

    # --- Item Methods ---
    def get_all_ground_items(self):
        """Returns all items currently placed on a map tile."""
        query = """
        SELECT i.*, m.q, m.r
        FROM items i
        JOIN map_tiles m ON i.tile = m.id
        """
        self.cursor.execute(query)
        return [dict(row) for row in self.cursor.fetchall()]

    def add_item_to_map(self, name, q, r, item_data):
        """Adds a copy of an item to the map at q, r."""
        # Find tile_id
        self.cursor.execute("SELECT id FROM map_tiles WHERE q=? AND r=?", (q, r))
        tile_row = self.cursor.fetchone()
        if not tile_row:
            return False
        
        tile_id = tile_row["id"]
        
        # Insert a new item instance for the map
        # Copy definition and set tile
        cols = ["name", "description", "item_type", "slot", "weight", 
                "base_damage", "defense", "max_durability", "durability", 
                "healing_amount", "hunger_restore", "texture_file", "power_bonus"]
        
        placeholders = ", ".join(["?" for _ in cols])
        placeholders += ", ?" # for tile
        
        sql = f"INSERT INTO items ({', '.join(cols)}, tile) VALUES ({placeholders})"
        
        vals = [item_data.get(c) for c in cols]
        vals.append(tile_id)
        
        self.cursor.execute(sql, vals)
        self.conn.commit()
        return True

    def delete_items_at(self, q, r):
        """Removes items from a map tile by setting their tile to NULL."""
        self.cursor.execute(
            "UPDATE items SET tile = NULL WHERE tile = (SELECT id FROM map_tiles WHERE q=? AND r=?)",
            (q, r)
        )
        self.conn.commit()

    # =========================
    # Castle Management
    # =========================

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
        self.cursor.execute("DELETE FROM map_castles WHERE q=? AND r=?", (q, r))
        self.conn.commit()

    def update_castle_level(self, q, r, level):
        self.cursor.execute("UPDATE map_castles SET level=? WHERE q=? AND r=?", (level, q, r))
        self.conn.commit()

    def get_missing_castle_levels(self):
        # All non-zero levels on map
        self.cursor.execute("SELECT DISTINCT level FROM map_tiles WHERE level > 0")
        map_lvls = {row["level"] for row in self.cursor.fetchall()}
        
        # All levels with castles
        self.cursor.execute("SELECT DISTINCT level FROM map_castles")
        castle_lvls = {row["level"] for row in self.cursor.fetchall()}
        
        return sorted(list(map_lvls - castle_lvls))

    def delete_castle_spawn(self, q, r):
        self.cursor.execute("DELETE FROM map_castle_spawns WHERE q=? AND r=?", (q, r))
        self.conn.commit()

    def close(self):
        self.conn.close()


class AssetManager:
    def __init__(self):
        self.image_cache = {}
        self.anim_frame_cache = {}
        self.texture_layout_map = {}
        self.castle_assets = set()
        self.refresh_layouts()

    def refresh_layouts(self):
        self.texture_layout_map = {}
        for category in ["tile", "prop"]:
            folder = Config.DIRS.get(category)
            if not os.path.exists(folder):
                continue
            for fname in os.listdir(folder):
                if not fname.endswith(".json"):
                    continue
                path = os.path.join(folder, fname)
                try:
                    with open(path, "r") as f:
                        data = json.load(f)
                        tex = data.get("texture_file")
                        if not tex and "animations" in data:
                            tex = data["animations"].get("idle", {}).get("texture")
                        if tex:
                            s = data.get("prop_scale") or data.get("scale", 1.0)
                            x = data.get("prop_x_shift") or data.get("x_shift", 0)
                            y = data.get("prop_y_shift") or data.get("prop_shift") or data.get("y_shift", 0)
                            star_y = data.get("star_y_offset", 50.0)
                            self.texture_layout_map[tex] = (float(s), int(x), int(y), float(star_y))
                            if data.get("is_castle") or "castle" in fname.lower():
                                self.castle_assets.add(tex)
                except Exception as e:
                    print(f"Error reading {fname}: {e}")

    def get_asset_layout(self, texture_file):
        if not texture_file:
            return 1.0, 0, 0, 50.0
        if texture_file in self.texture_layout_map:
            return self.texture_layout_map[texture_file]
        return 1.0, 0, 0, 50.0

    def get_tk_image(self, filename, scale=1.0):
        if not filename:
            return None
        path = os.path.join(Config.ASSET_DIR, filename)
        if not os.path.exists(path):
            return None
        target_w = max(1, int(Config.HEX_SIZE * scale))
        key = (path, target_w)
        if key in self.image_cache:
            return self.image_cache[key]
        try:
            pil = Image.open(path)
            w_pct = target_w / float(pil.size[0])
            h_size = int((float(pil.size[1]) * float(w_pct)))
            pil = pil.resize((target_w, h_size), Image.Resampling.NEAREST)
            tk_img = ImageTk.PhotoImage(pil)
            self.image_cache[key] = tk_img
            return tk_img
        except Exception as e:
            return None

    def get_anim_frame(self, filename, frame_index, fw, fh, count, scale=1.0):
        """
        Extracts a specific frame from a sprite sheet with caching.
        """
        if not filename:
            return None
        
        # Cache check
        key = (filename, frame_index, fw, fh, count, scale)
        if key in self.anim_frame_cache:
            return self.anim_frame_cache[key]
            
        path = os.path.join(Config.ASSET_DIR, filename)
        if not os.path.exists(path):
            return None

        try:
            pil = Image.open(path)
            safe_idx = frame_index % max(1, count)
            x = safe_idx * fw
            y = 0
            if x + fw > pil.width:
                x = 0

            crop = pil.crop((x, y, x + fw, y + fh))
            target_w = int(fw * scale)
            target_h = int(fh * scale)
            crop = crop.resize((target_w, target_h), Image.Resampling.NEAREST)

            tk_img = ImageTk.PhotoImage(crop)
            self.anim_frame_cache[key] = tk_img
            return tk_img
        except Exception as e:
            print(f"Anim Error: {e}")
            return None

    def load_json(self, category, name):
        folder = Config.DIRS.get(category)
        path = os.path.join(folder, name)
        if os.path.exists(path):
            with open(path, "r") as f:
                return json.load(f)
        return {}

    def save_json(self, category, name, data):
        folder = Config.DIRS.get(category)
        if not name.endswith(".json"):
            name += ".json"
        path = os.path.join(folder, name)
        with open(path, "w") as f:
            json.dump(data, f, indent=4)
        self.refresh_layouts()
        return path

    def list_assets(self, category):
        folder = Config.DIRS.get(category)
        if not os.path.exists(folder): return []
        return sorted([f for f in os.listdir(folder) if f.endswith(".json")])

    def list_castles(self):
        folder = Config.DIRS.get("prop")
        if not os.path.exists(folder): return []
        results = []
        for f in os.listdir(folder):
            if not f.endswith(".json"): continue
            if "castle" in f.lower():
                results.append(f)
                continue
            try:
                with open(os.path.join(folder, f), "r") as jf:
                    if json.load(jf).get("is_castle"):
                        results.append(f)
            except: pass
        return sorted(list(set(results)))


    def load_item_categories(self):
        path = os.path.join(Config.DIRS["item"], "item_categories.json")
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    data = json.load(f)
                    migrated = False
                    for k, v in data.items():
                        if isinstance(v, list):
                            data[k] = {"slot": "general", "props": v}
                            migrated = True
                    if migrated:
                        self.save_item_categories(data)
                    return data
            except Exception as e:
                pass
        
        return {}

    def save_item_categories(self, categories):
        os.makedirs(Config.DIRS["item"], exist_ok=True)
        path = os.path.join(Config.DIRS["item"], "item_categories.json")
        with open(path, "w") as f:
            json.dump(categories, f, indent=4)
        
        md_path = "ITEM_CATEGORIES.md"
        with open(md_path, "w") as f:
            f.write("# Item Categories Documentation\n\n")
            f.write("This file is auto-generated by the Hex Editor. It describes the available item categories and their configurable properties.\n\n")
            for cat, cdata in categories.items():
                f.write(f"## {cat.capitalize()}\n")
                slot = cdata.get("slot", "general") if isinstance(cdata, dict) else "general"
                f.write(f"**Slot:** `{slot}`\n\n")
                props = cdata.get("props", []) if isinstance(cdata, dict) else cdata
                if not props:
                    f.write("- *(No optional properties)*\n")
                for p in props:
                    f.write(f"- {p}\n")
                f.write("\n")


class Renderer:
    def __init__(self, asset_mgr):
        self.am = asset_mgr

    def render_hex_at_pixel(self, canvas, cx, cy, tile_data, selected=False, view_mode="Standard", zoom=1.0, skip_castles=False):
        poly = HexEngine.get_hex_polygon(cx, cy)
        fill = ""
        t_type = tile_data.get("tile_type")
        if t_type == "water":
            fill = "#283b45"
        elif t_type == "stone":
            fill = "#383838"
        elif t_type == "grass":
            fill = "#2e3b28"

        if fill:
            canvas.create_polygon(poly, fill=fill, outline="", tags="hex_fill")
        tex = tile_data.get("texture_file")
        if tex:
            t_scale = tile_data.get("tile_scale")
            t_x_shift = tile_data.get("tile_x_shift")
            t_y_shift = tile_data.get("tile_y_shift")
            if t_scale is None:
                t_scale, t_x_shift, t_y_shift, _ = self.am.get_asset_layout(tex)
            
            # Scale shifts by zoom
            s_x = (t_x_shift or 0) * zoom
            s_y = (t_y_shift or 0) * zoom
            
            img = self.am.get_tk_image(tex, scale=t_scale)
            if img:
                canvas.create_image(
                    cx + s_x, cy - Config.CALIB_OFFSET_Y - s_y, image=img, tags="hex_art"
                )
        p_tex = tile_data.get("prop_texture_file")
        if p_tex:
            if skip_castles and p_tex in self.am.castle_assets:
                # Skip rendering (handled in second pass)
                pass
            else:
                p_scale = tile_data.get("prop_scale", 1.0)
                p_x_shift = tile_data.get("prop_x_shift", 0)
                p_y_shift = tile_data.get("prop_y_shift", 0)
                
                # Scale shifts by zoom
                ps_x = (p_x_shift or 0) * zoom
                ps_y = (p_y_shift or 0) * zoom
                
                img = self.am.get_tk_image(p_tex, scale=p_scale)
                if img:
                    canvas.create_image(
                        cx + ps_x, cy - Config.CALIB_OFFSET_Y - ps_y, image=img, tags="hex_prop"
                    )
        outline = "red" if selected else "#555"
        width = 2 if selected else 1
        if tile_data.get("is_spawn") and view_mode != "Spawns":
            # Scale indicator size by zoom
            rad = 5 * zoom
            canvas.create_oval(
                cx - rad, cy - rad, cx + rad, cy + rad, fill="#00FF00", outline="black"
            )
            canvas.create_text(
                cx, cy + (15 * zoom), text=f"Lvl {tile_data.get('level', 1)}", fill="white", font=("Arial", int(8 * zoom), "bold")
            )
            outline = "#00FF00"
            width = 3

        canvas.create_polygon(
            poly, fill="", outline=outline, width=width, tags="hex_grid"
        )


class MapTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.selected_q = 0
        self.selected_r = 0
        self.view_mode = tk.StringVar(value="Standard")
        self.var_paint_mode = tk.BooleanVar(value=False)
        self.var_paint_delete = tk.BooleanVar(value=False)
        self.brush_size = tk.IntVar(value=1)

        self.tile_cache = {}
        self.monster_cache = []
        self.item_cache = []
        self.castle_cache = []
        self.castle_spawn_cache = []
        self.selected_castle_id = None
        self._setup_ui()
        self._bind_events()
        self.zoom_level = 1.0  # Base scale
        self.anim_tick = 0
        
        self.refresh_cache()

        self.after(100, self._center_view)
        self._animate()

    def _animate(self):
        self.anim_tick += 1
        # Only force re-render if animations are active (zoom >= 60%)
        if self.zoom_level >= 0.6:
            self.render()
        self.after(250, self._animate) # 250ms for a steady idle pace

    def refresh_cache(self):
        """Rebuild the local data cache from the database."""
        self.tile_cache = {(t["q"], t["r"]): t for t in self.app.db.get_all_tiles()}
        self.monster_cache = self.app.db.get_all_monsters()
        self.item_cache = self.app.db.get_all_ground_items()
        self.castle_cache = self.app.db.get_map_castles()
        self.castle_spawn_cache = self.app.db.get_castle_spawns()

    def _center_view(self):
        self.update_idletasks()
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w <= 1 or h <= 1:
            self.after(50, self._center_view)
            return
        self.canvas.xview_moveto((Config.CENTER_X - w / 2) / float(Config.MAP_WIDTH))
        self.canvas.yview_moveto((Config.CENTER_Y - h / 2) / float(Config.MAP_HEIGHT))

    def _setup_ui(self):
        self.paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        self.paned.pack(fill="both", expand=True)

        c_frame = ttk.Frame(self.paned)
        self.paned.add(c_frame, weight=3)

        self.canvas = Canvas(
            c_frame,
            bg="#202020",
            scrollregion=(0, 0, Config.MAP_WIDTH, Config.MAP_HEIGHT),
        )
        
        # Wrap scroll commands to trigger re-render for culling
        def on_vscroll(*args):
            self.canvas.yview(*args)
            self.render()
        def on_hscroll(*args):
            self.canvas.xview(*args)
            self.render()

        vbar = ttk.Scrollbar(c_frame, orient=tk.VERTICAL, command=on_vscroll)
        hbar = ttk.Scrollbar(c_frame, orient=tk.HORIZONTAL, command=on_hscroll)
        self.canvas.configure(yscrollcommand=vbar.set, xscrollcommand=hbar.set)
        vbar.pack(side=tk.RIGHT, fill=tk.Y)
        hbar.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas.pack(side=tk.LEFT, fill="both", expand=True)

        # --- Sidebar ---
        self.sidebar = ttk.Frame(self.paned, padding=10)
        self.paned.add(self.sidebar, weight=1)
        
        # View Mode Selector
        view_frame = ttk.LabelFrame(self.sidebar, text="View Mode", padding=5)
        view_frame.pack(fill="x", pady=(0, 10))
        modes = ["Standard", "Levels", "Collision", "Spawns", "Monsters", "Items", "Castles"]
        for m in modes:
            ttk.Radiobutton(view_frame, text=m, variable=self.view_mode, value=m, command=self._on_view_mode_change).pack(anchor="w")

        # Level View Filter
        self.var_level_view = tk.IntVar(value=0)
        filter_frame = ttk.LabelFrame(self.sidebar, text="Level View Filter", padding=5)
        filter_frame.pack(fill="x", pady=(0, 10))
        
        def on_view_scale(val):
            self.var_level_view.set(round(float(val)))
            self.render()
            
        ttk.Scale(filter_frame, from_=0, to=10, variable=self.var_level_view, orient=tk.HORIZONTAL, command=on_view_scale).pack(fill="x")
        
        self.lbl_level_view = ttk.Label(filter_frame, text="All Levels")
        self.lbl_level_view.pack()
        
        def update_lbl(*args):
            v = self.var_level_view.get()
            self.lbl_level_view.config(text="All Levels" if v == 0 else f"Level {v}")
            
        self.var_level_view.trace_add("write", update_lbl)

        # Dynamic Inspector Area
        self.inspector_area = ttk.Frame(self.sidebar)
        self.inspector_area.pack(fill="both", expand=True)
        
        self._build_standard_inspector() # Default

    def _on_view_mode_change(self):
        for widget in self.inspector_area.winfo_children():
            widget.destroy()
        
        mode = self.view_mode.get()
        if mode == "Standard":
            self._build_standard_inspector()
        elif mode == "Levels":
            self._build_level_inspector()
        elif mode == "Collision":
            self._build_collision_inspector()
        elif mode == "Spawns":
            self._build_spawn_inspector()
        elif mode == "Monsters":
            self._build_monster_inspector()
        elif mode == "Items":
            self._build_item_inspector()
        elif mode == "Castles":
            self._build_castle_inspector()
        
        self.render()

    def _on_paint_mode_toggle(self):
        if self.var_paint_mode.get():
            self._reset_brush()
            if hasattr(self, "btn_reset_brush"):
                self.btn_reset_brush.pack(side=tk.TOP, fill="x", padx=5, pady=(0, 5))
        else:
            if hasattr(self, "btn_reset_brush"):
                self.btn_reset_brush.pack_forget()

    def _reset_brush(self):
        self.selected_q = None
        self.selected_r = None
        if hasattr(self, 'var_q'):
            self.var_q.set("")
            self.var_r.set("")
        if hasattr(self, 'var_tile'):
            self.var_tile.set("")
        if hasattr(self, 'var_prop'):
            self.var_prop.set("")
        if hasattr(self, 'cb_tiles'):
            self.cb_tiles.set("")
        if hasattr(self, 'cb_props'):
            self.cb_props.set("")
        self.render()

    def _build_standard_inspector(self):
        frame = self.inspector_area
        
        # Paint Mode & Coords
        paint_frame = ttk.LabelFrame(frame, text="Editor Mode", padding=5)
        paint_frame.pack(fill="x", pady=(0, 10))
        ttk.Checkbutton(paint_frame, text="PAINT MODE (On/Off)", variable=self.var_paint_mode, command=self._on_paint_mode_toggle).pack(side=tk.TOP, anchor="w", pady=2)
        self.btn_reset_brush = ttk.Button(paint_frame, text="Reset Brush", command=self._reset_brush)
        
        self.var_q = tk.StringVar(value="0")
        self.var_r = tk.StringVar(value="0")
        
        coord_frame = ttk.Frame(frame)
        coord_frame.pack(fill="x", pady=5)
        ttk.Label(coord_frame, text="Q:").pack(side=tk.LEFT)
        ttk.Label(coord_frame, textvariable=self.var_q, width=5).pack(side=tk.LEFT)
        ttk.Label(coord_frame, text=" R:").pack(side=tk.LEFT)
        ttk.Label(coord_frame, textvariable=self.var_r, width=5).pack(side=tk.LEFT)

        # Tile Logic
        self.var_tile = tk.StringVar()
        self.var_prop = tk.StringVar()
        self.var_prop_scale = tk.DoubleVar(value=1.0)
        self.var_prop_x_shift = tk.IntVar(value=0)
        self.var_prop_shift = tk.IntVar(value=0)
        # self.var_is_spawn = tk.BooleanVar(value=False) # Moved to Spawn View

        ttk.Separator(frame).pack(fill="x", pady=10)
        ttk.Label(frame, text="Terrain (Base)", font=("Bold", 10)).pack(anchor="w")
        self.cb_tiles = ttk.Combobox(frame, state="readonly", values=self.app.asset_mgr.list_assets("tile"))
        self.cb_tiles.pack(fill="x")
        self.cb_tiles.bind("<<ComboboxSelected>>", self._on_tile_preset_select)
        
        ttk.Separator(frame).pack(fill="x", pady=10)
        ttk.Label(frame, text="Prop (Overlay)", font=("Bold", 10)).pack(anchor="w")
        self.cb_props = ttk.Combobox(frame, state="readonly", values=self.app.asset_mgr.list_assets("prop"))
        self.cb_props.pack(fill="x")
        self.cb_props.bind("<<ComboboxSelected>>", self._on_prop_preset_select)
        
        ttk.Button(frame, text="Clear Prop", command=self._clear_prop).pack(fill="x", pady=5)
        ttk.Button(frame, text="DELETE TILE", command=self._delete_tile).pack(fill="x", pady=20)
        
        ttk.Separator(frame).pack(fill="x", pady=5)
        ttk.Checkbutton(frame, text="PAINT DELETE MODE", variable=self.var_paint_delete).pack(pady=10)

    def _build_level_inspector(self):
        frame = self.inspector_area
        ttk.Label(frame, text="Level Editor", font=("Bold", 12)).pack(pady=10)
        ttk.Label(frame, text="Click or Drag to set level").pack()
        
        self.var_level_paint = tk.IntVar(value=1)
        def on_paint_scale(val):
            self.var_level_paint.set(round(float(val)))
            
        ttk.Label(frame, text="Target Level:").pack(anchor="w", pady=(10,0))
        ttk.Scale(frame, from_=1, to=10, variable=self.var_level_paint, orient=tk.HORIZONTAL, command=on_paint_scale).pack(fill="x")
        ttk.Label(frame, textvariable=self.var_level_paint).pack()
        
    def _build_collision_inspector(self):
        frame = self.inspector_area
        ttk.Label(frame, text="Collision Editor", font=("Bold", 12)).pack(pady=10)
        
        self.var_collision_mode = tk.StringVar(value="cursor")
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill="x", pady=2)
        
        ttk.Radiobutton(btn_frame, text="🖱️ Cursor", variable=self.var_collision_mode, value="cursor", style="Toolbutton").pack(side=tk.LEFT, fill="x", expand=True, padx=1)
        ttk.Radiobutton(btn_frame, text="Pass", variable=self.var_collision_mode, value="passable", style="Toolbutton").pack(side=tk.LEFT, fill="x", expand=True, padx=1)
        ttk.Radiobutton(btn_frame, text="Block", variable=self.var_collision_mode, value="unpassable", style="Toolbutton").pack(side=tk.LEFT, fill="x", expand=True, padx=1)

    def _build_spawn_inspector(self):
        frame = self.inspector_area
        ttk.Label(frame, text="Spawn Editor", font=("Bold", 12)).pack(pady=10)
        
        ttk.Button(frame, text="Set spawn for this level", command=self._set_spawn_click).pack(fill="x", pady=5)
        ttk.Button(frame, text="Remove spawn", command=self._remove_spawn_click).pack(fill="x", pady=5)
        
        self.var_spawn_show_levels = tk.BooleanVar(value=False)
        ttk.Checkbutton(frame, text="Show Levels Overlay", variable=self.var_spawn_show_levels, command=self.render).pack(pady=10)

    def _set_spawn_click(self):
        q, r = self.selected_q, self.selected_r
        data = self.app.db.get_tile(q, r)
        if data:
            if not data.get("is_permanently_passable", 1) or data.get("prop_texture_file"):
                self.app.show_toast("Cannot place a spawn point onto a prop or an impassable tile.")
                return
        self._update_tile_safe(q, r, {"is_spawn": 1})
        self.render()

    def _remove_spawn_click(self):
        self._update_tile_safe(self.selected_q, self.selected_r, {"is_spawn": 0})
        self.render()

    def _build_monster_inspector(self):
        frame = self.inspector_area
        ttk.Label(frame, text="Monster Spawner", font=("Bold", 12)).pack(pady=10)
        
        ttk.Label(frame, text="Select Monster:").pack(anchor="w")
        self.cb_monsters = ttk.Combobox(frame, state="readonly", values=self.app.asset_mgr.list_assets("monster"))
        self.cb_monsters.pack(fill="x")
        if self.cb_monsters["values"]:
            self.cb_monsters.current(0)
            
        ttk.Label(frame, text="Left Click: Place/Select").pack(pady=(20,0))
        ttk.Label(frame, text="Right Click: Remove").pack()
        
        ttk.Separator(frame).pack(fill="x", pady=10)
        ttk.Label(frame, text="Selected Monster Stats", font=("Bold", 10)).pack(anchor="w")
        
        self.var_monster_health = tk.IntVar(value=50)
        self.var_monster_damage = tk.IntVar(value=10)
        
        v_frame = ttk.Frame(frame)
        v_frame.pack(fill="x", pady=5)
        
        ttk.Label(v_frame, text="Health:").grid(row=0, column=0, sticky="w")
        ttk.Entry(v_frame, textvariable=self.var_monster_health, width=8).grid(row=0, column=1, padx=5)
        
        ttk.Label(v_frame, text="Damage:").grid(row=1, column=0, sticky="w")
        ttk.Entry(v_frame, textvariable=self.var_monster_damage, width=8).grid(row=1, column=1, padx=5, pady=5)
        
        self.btn_update_monster = ttk.Button(frame, text="Update Stats", command=self._update_selected_monster_stats, state="disabled")
        self.btn_update_monster.pack(fill="x", pady=5)

    def _build_item_inspector(self):
        """UI for placing items on the ground."""
        frame = self.inspector_area
        ttk.Label(frame, text="Item Placer", font=("Bold", 12)).pack(pady=10)
        
        ttk.Label(frame, text="Select Item:").pack(anchor="w")
        self.cb_items = ttk.Combobox(frame, state="readonly", values=self.app.asset_mgr.list_assets("item"))
        self.cb_items.pack(fill="x")
        if self.cb_items["values"]:
            self.cb_items.current(0)
            
        ttk.Label(frame, text="Left Click: Place Item").pack(pady=(20,0))
        ttk.Label(frame, text="Right Click: Clear Items").pack()
        
        ttk.Separator(frame).pack(fill="x", pady=20)
        
        # Selection info
        self.lbl_item_info = ttk.Label(frame, text="Select a tile to see its items", wraplength=180)
        self.lbl_item_info.pack(fill="x")

    def _build_castle_inspector(self):
        frame = self.inspector_area
        ttk.Label(frame, text="Castle Designer", font=("Bold", 12)).pack(pady=10)
        
        self.var_castle_mode = tk.StringVar(value="select")
        
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill="x", pady=5)
        ttk.Radiobutton(btn_frame, text="castle selector", variable=self.var_castle_mode, value="select", style="Toolbutton").pack(side=tk.LEFT, fill="x", expand=True)
        ttk.Radiobutton(btn_frame, text="Place/Delete Castle", variable=self.var_castle_mode, value="center", style="Toolbutton").pack(side=tk.LEFT, fill="x", expand=True)
        ttk.Radiobutton(btn_frame, text="Monster spawn Selector", variable=self.var_castle_mode, value="spawn", style="Toolbutton").pack(side=tk.LEFT, fill="x", expand=True)
        
        # 1. Select Mode Container
        self.f_castle_id = ttk.Frame(frame)
        ttk.Label(self_f_castle_id := self.f_castle_id, text="Selected Castle ID:").pack(anchor="w", pady=(10,0))
        self.lbl_sel_castle = ttk.Label(self_f_castle_id, text="None")
        self.lbl_sel_castle.pack(anchor="w")
        
        # 2. Center Mode Container
        self.f_castle_asset = ttk.Frame(frame)
        ttk.Label(self_f_castle_asset := self.f_castle_asset, text="Select Castle Asset:").pack(anchor="w", pady=(10,0))
        self.cb_castle_assets = ttk.Combobox(self_f_castle_asset, state="readonly", values=self.app.asset_mgr.list_castles())
        self.cb_castle_assets.pack(fill="x")
        if self.cb_castle_assets["values"]:
            self.cb_castle_assets.current(0)
            
        # 3. Spawn Mode Container
        self.f_castle_spawn = ttk.Frame(frame)
        ttk.Label(self_f_castle_spawn := self.f_castle_spawn, text="For Spawns: Select Monster").pack(anchor="w")
        self.cb_castle_monsters = ttk.Combobox(self_f_castle_spawn, state="readonly", values=self.app.asset_mgr.list_assets("monster"))
        self.cb_castle_monsters.pack(fill="x")
        if self.cb_castle_monsters["values"]:
            self.cb_castle_monsters.current(0)
            
        v_frame = ttk.Frame(self_f_castle_spawn)
        v_frame.pack(fill="x", pady=5)
        
        self.var_castle_monster_hp = tk.IntVar(value=50)
        self.var_castle_monster_dmg = tk.IntVar(value=10)
        ttk.Label(v_frame, text="Health:").grid(row=0, column=0, sticky="w")
        ttk.Entry(v_frame, textvariable=self.var_castle_monster_hp, width=8).grid(row=0, column=1, padx=5)
        ttk.Label(v_frame, text="Damage:").grid(row=1, column=0, sticky="w")
        ttk.Entry(v_frame, textvariable=self.var_castle_monster_dmg, width=8).grid(row=1, column=1, padx=5, pady=5)
        
        # Global Footer
        self.lbl_castle_hint = ttk.Label(frame, text="Right Click: Delete Castle/Spawn", wraplength=180)
        self.lbl_castle_hint.pack(pady=10)
        
        self.var_castle_mode.trace_add("write", lambda *a: self._refresh_castle_ui())
        self._refresh_castle_ui()

    def _refresh_castle_ui(self):
        mode = self.var_castle_mode.get()
        # Hide all
        for f in [self.f_castle_id, self.f_castle_asset, self.f_castle_spawn]:
            f.pack_forget()
        
        self.lbl_castle_hint.pack_forget()

        # Show targeted
        if mode == "select":
            self.f_castle_id.pack(fill="x")
        elif mode == "center":
            self.f_castle_asset.pack(fill="x")
        elif mode == "spawn":
            self.f_castle_spawn.pack(fill="x")
            
        self.lbl_castle_hint.pack(pady=10)

    def _update_selected_monster_stats(self):
        hp = self.var_monster_health.get()
        dmg = self.var_monster_damage.get()
        self.app.db.update_monster_stats(self.selected_q, self.selected_r, hp, dmg)
        self.refresh_cache()
        self.render()
        self.app.show_toast(f"Updated monster at ({self.selected_q},{self.selected_r})")
        
    def _bind_events(self):
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<B1-Motion>", self._on_click)
        self.canvas.bind("<Button-3>", self._on_right_click)
        self.canvas.bind("<Enter>", lambda e: self.canvas.focus_set())
        self.canvas.bind("<MouseWheel>", self._on_mousewheel_v)
        self.canvas.bind("<Shift-MouseWheel>", self._on_mousewheel_h)
        self.canvas.bind("<Control-MouseWheel>", self._on_zoom)

    def _on_mousewheel_v(self, event):
        delta = event.delta
        units = int(-1 * (delta / 120))
        if units == 0 and delta != 0:
            units = -1 if delta > 0 else 1
        self.canvas.yview_scroll(units, "units")
        self.render()

    def _on_mousewheel_h(self, event):
        delta = event.delta
        units = int(-1 * (delta / 120))
        if units == 0 and delta != 0:
            units = -1 if delta > 0 else 1
        self.canvas.xview_scroll(units, "units")
        self.render()

    def _on_zoom(self, event):
        """Handle zooming (pinch gesture or Ctrl+MouseWheel)."""
        # Zoom factor per scroll tick
        factor = 1.1 if event.delta > 0 else 0.9

        # Apply zoom limits (10% to 300% of base)
        # Base HEX_RADIUS is 16, BASE_HEX_SIZE before zoom was 48 (16 * 3)
        new_zoom = self.zoom_level * factor
        if new_zoom < 0.1: new_zoom = 0.1
        if new_zoom > 5.0: new_zoom = 5.0

        self.zoom_level = new_zoom

        # Update global config for HexEngine and Renderer
        # Original GAME_SCALE was 3
        current_scale = 3.0 * self.zoom_level
        Config.HEX_SIZE = Config.BASE_HEX_RADIUS * current_scale
        Config.CALIB_OFFSET_Y = 16 * current_scale

        # Re-render map with new scale
        self.render()
        if hasattr(self, 'lbl_zoom'):
            self.lbl_zoom.config(text=f"Zoom: {int(self.zoom_level * 100)}%")
        self.app.show_toast(f"Zoom: {int(self.zoom_level * 100)}%")

    def refresh_libraries(self):
        if hasattr(self, 'cb_tiles') and self.cb_tiles.winfo_exists():
            self.cb_tiles["values"] = self.app.asset_mgr.list_assets("tile")
        if hasattr(self, 'cb_props') and self.cb_props.winfo_exists():
            all_props = self.app.asset_mgr.list_assets("prop")
            castles = self.app.asset_mgr.list_castles()
            props_only = [p for p in all_props if p not in castles]
            self.cb_props["values"] = props_only

    def render(self):
        self.canvas.delete("all")
        
        # 1. Get visible viewport in canvas coordinates
        x0 = self.canvas.canvasx(0)
        y0 = self.canvas.canvasy(0)
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        
        # Fallback for initial render before window is mapped
        if w <= 1: w = 800
        if h <= 1: h = 600
        
        x1 = x0 + w
        y1 = y0 + h
        
        cx, cy = Config.CENTER_X, Config.CENTER_Y
        
        # 2. Convert viewport corners to hex coordinates to find the visible range
        # Padding (2 hexes) to avoid popping
        padding = 2
        
        # Local pixel coords relative to map center
        # hex_q, hex_r = pixel_to_hex(px, py) where px = x - cx
        q0, r0 = HexEngine.pixel_to_hex(x0 - cx, y0 - cy)
        q1, r1 = HexEngine.pixel_to_hex(x1 - cx, y0 - cy)
        q2, r2 = HexEngine.pixel_to_hex(x0 - cx, y1 - cy)
        q3, r3 = HexEngine.pixel_to_hex(x1 - cx, y1 - cy)
        
        q_min = min(q0, q1, q2, q3) - padding
        q_max = max(q0, q1, q2, q3) + padding
        r_min = min(r0, r1, r2, r3) - padding
        r_max = max(r0, r1, r2, r3) + padding
        
        # Use Cached Data
        db_tiles = self.tile_cache
        monsters = self.monster_cache
        
        mode = self.view_mode.get()

        render_list = []
        # Respect global GRID_RANGE but limit to visible bounds
        g_range = Config.GRID_RANGE
        
        q_start = max(-g_range, q_min)
        q_end = min(g_range, q_max)
        r_start_global = -g_range
        r_end_global = g_range

        for q in range(q_start, q_end + 1):
            # For each q, compute the valid r range in a large hexagon
            # abs(q + r) <= g_range  =>  -g_range - q <= r <= g_range - q
            r_hex_min = -g_range - q
            r_hex_max = g_range - q
            
            # Intersection of hex range and visible r range
            curr_r_start = max(r_hex_min, r_min)
            curr_r_end = min(r_hex_max, r_max)
            
            for r_idx in range(curr_r_start, curr_r_end + 1):
                px, py = HexEngine.hex_to_pixel(q, r_idx)
                draw_x, draw_y = cx + px, cy + py
                
                tile_data = db_tiles.get((q, r_idx), {})
                
                # Apply level view filter
                view_lvl = getattr(self, "var_level_view", None) and self.var_level_view.get()
                if view_lvl and view_lvl > 0 and tile_data.get("level", 1) != view_lvl:
                    continue

                render_list.append((q, r_idx, draw_x, draw_y, tile_data))

        render_list.sort(key=lambda x: x[3])
        
        for q, r_idx, x, y, data in render_list:
            is_selected = q == self.selected_q and r_idx == self.selected_r
            
            # Base Render (Now skipping castles for second pass)
            self.app.renderer.render_hex_at_pixel(self.canvas, x, y, data, is_selected, mode, zoom=self.zoom_level, skip_castles=True)
            
            poly = HexEngine.get_hex_polygon(x, y)

            # OVERLAYS
            if not data:
                continue

            if mode == "Levels":
                lvl = data.get("level", 1)
                # Color map based on level
                colors = ["#444", "#336699", "#669933", "#ddaa33", "#993333", "#552255"] # Gray, Blue, Green, Yellow, Red, Purple
                c_idx = min(lvl, len(colors)-1)
                c = colors[c_idx]
                if lvl > 0:
                    self.canvas.create_polygon(poly, fill=c, stipple="gray50", outline="")
                    self.canvas.create_text(x, y, text=str(lvl), fill="white", font=("Bold", int(14 * self.zoom_level)))

            elif mode == "Collision":
                passable = data.get("is_permanently_passable", 1)
                color = "#00FF00" if passable else "#FF0000"
                self.canvas.create_polygon(poly, fill=color, stipple="gray12", outline="")

            elif mode == "Spawns":
                if getattr(self, "var_spawn_show_levels", None) and self.var_spawn_show_levels.get():
                    lvl = data.get("level", 1)
                    colors = ["#444", "#336699", "#669933", "#ddaa33", "#993333", "#552255"]
                    c_idx = min(lvl, len(colors)-1)
                    c = colors[c_idx]
                    if lvl > 0:
                        self.canvas.create_polygon(poly, fill=c, stipple="gray50", outline="")
                        self.canvas.create_text(x, y, text=str(lvl), fill="white", font=("Bold", int(14 * self.zoom_level)))

                if data.get("is_spawn"):
                    rad = 10 * self.zoom_level
                    self.canvas.create_oval(x-rad, y-rad, x+rad, y+rad, fill="cyan", outline="white", width=2)
                    self.canvas.create_text(x, y+(20*self.zoom_level), text=f"Lvl {data.get('level',1)}", fill="white")
                    
                if not data.get("is_permanently_passable", 1):
                    self.canvas.create_polygon(poly, fill="#FF0000", stipple="gray25", outline="")

        # Monster Render (On top)
        if mode != "Collision":
            view_lvl = getattr(self, "var_level_view", None) and self.var_level_view.get()
            for m in monsters:
                mq, mr = m["current_q"], m["current_r"]
                
                # CULLING: Only render if within visible hex bounds
                if not (q_min <= mq <= q_max and r_min <= mr <= r_max):
                    continue

                # Filter by level if active
                if view_lvl and view_lvl > 0:
                    t_data = db_tiles.get((mq, mr), {})
                    if t_data.get("level", 1) != view_lvl:
                        continue

                px, py = HexEngine.hex_to_pixel(mq, mr)
                mx, my = cx + px, cy + py
                
                if mode == "Monsters":
                    # Simple purple circle for clarity in monster view
                    rad = 10 * self.zoom_level
                    self.canvas.create_oval(mx-rad, my-rad, mx+rad, my+rad, fill="purple", outline="white", width=2)
                    self.canvas.create_text(mx, my-(15*self.zoom_level), text=m["name"], fill="white", font=("Arial", int(8*self.zoom_level)))
                elif mode in ["Standard", "Levels", "Spawns"]:
                    # Real idle texture
                    m_data = self.app.asset_mgr.load_json("monster", m["name"])
                    if m_data:
                        anim_idle = m_data.get("animations", {}).get("idle", {})
                        tex = anim_idle.get("texture")
                        fw = anim_idle.get("fw", 32)
                        fh = anim_idle.get("fh", 32)
                        count = anim_idle.get("count", 1)
                        
                        # SCALE MONSTER BY ZOOM
                        base_scale = m_data.get("scale", 1.0)
                        scale = base_scale * self.zoom_level
                        
                        # Scale shifts by zoom
                        sx_m = m_data.get("x_shift", 0) * self.zoom_level
                        sy_m = m_data.get("y_shift", 0) * self.zoom_level
                        
                        if not tex:
                            continue

                        # Optimize: Only animate if zoom is >= 60%
                        frame_idx = self.anim_tick if self.zoom_level >= 0.6 else 0
                        
                        img = self.app.asset_mgr.get_anim_frame(tex, frame_idx, fw, fh, count, scale)
                        if img:
                            self.canvas.create_image(
                                mx + sx_m, 
                                my - Config.CALIB_OFFSET_Y - sy_m, 
                                image=img, 
                                tags="monster_art"
                            )

            # --- Ground Item Render ---
            for item in self.item_cache:
                iq, ir = item["q"], item["r"]
                
                # CULLING
                if not (q_min <= iq <= q_max and r_min <= ir <= r_max):
                    continue

                # Filter by level if active
                if view_lvl and view_lvl > 0:
                    t_data = db_tiles.get((iq, ir), {})
                    if t_data.get("level", 1) != view_lvl:
                        continue

                px, py = HexEngine.hex_to_pixel(iq, ir)
                ix, iy = cx + px, cy + py

                if mode == "Items":
                    # Distinct yellow marker in Items view
                    rad = 8 * self.zoom_level
                    self.canvas.create_polygon(
                        ix, iy-rad, ix+rad, iy, ix, iy+rad, ix-rad, iy,
                        fill="gold", outline="white", width=1
                    )
                    self.canvas.create_text(ix, iy-(12*self.zoom_level), text=item["name"], fill="white", font=("Arial", int(7*self.zoom_level)))
                elif mode in ["Standard", "Levels", "Spawns"]:
                    # Draw item icon if zoomed in
                    if self.zoom_level >= 0.5:
                        tex = item.get("texture_file")
                        if tex:
                            # Usually items are small, let's scale them slightly
                            scale = 0.8 * self.zoom_level 
                            img = self.app.asset_mgr.get_tk_image(tex, scale)
                            if img:
                                self.canvas.create_image(ix, iy - (Config.CALIB_OFFSET_Y * self.zoom_level) + 35, image=img, anchor="center")

            # --- Final Castle Art Render (On top of tiles but under overlays) ---
            for q, r_idx, x, y, data in render_list:
                p_tex = data.get("prop_texture_file")
                if p_tex and p_tex in self.app.asset_mgr.castle_assets:
                    # Render the castle prop on its original anchor tile
                    p_scale = data.get("prop_scale", 1.0)
                    p_x_shift = data.get("prop_x_shift", 0)
                    p_y_shift = data.get("prop_y_shift", 0)
                    
                    ps_x = (p_x_shift or 0) * self.zoom_level
                    ps_y = (p_y_shift or 0) * self.zoom_level
                    
                    img = self.app.asset_mgr.get_tk_image(p_tex, scale=p_scale)
                    if img:
                        self.canvas.create_image(
                            x + ps_x, y - Config.CALIB_OFFSET_Y - ps_y, image=img, tags="hex_prop_castle"
                        )

            # --- Castles Overlay Render (On top of EVERYTHING) ---
            if mode == "Castles":
                # Draw lines from spawns to their castles first so they're underneath
                for s in self.castle_spawn_cache:
                    cq, cr = None, None
                    for c in self.castle_cache:
                        if c["id"] == s["castle_id"]:
                            cq, cr = c["q"], c["r"]
                            break
                    if cq is not None and cr is not None:
                        spx, spy = HexEngine.hex_to_pixel(s["q"], s["r"])
                        cpx, cpy = HexEngine.hex_to_pixel(cq, cr)
                        self.canvas.create_line(
                            cx + spx, cy + spy, cx + cpx, cy + cpy, 
                            fill="cyan", dash=(4, 4), width=2
                        )
                
                # Draw Castle Centers
                for c in self.castle_cache:
                    cq, cr = c["q"], c["r"]
                    px, py = HexEngine.hex_to_pixel(cq, cr)
                    x, y = cx + px, cy + py
                    
                    # Highlight the entire center hex
                    poly = HexEngine.get_hex_polygon(x, y)
                    is_selected = getattr(self, "selected_castle_id", None) == c["id"]
                    fill_color = "gold" if is_selected else "yellow"
                    outline_color = "white" if is_selected else "gold"
                    line_width = 3 if is_selected else 1
                    
                    self.canvas.create_polygon(poly, fill=fill_color, stipple="gray25", outline=outline_color, width=line_width)
                    
                    rad = 12 * self.zoom_level
                    fill_marker = "gold" if is_selected else "yellow"
                    self.canvas.create_polygon(
                        x, y-rad, x+rad, y, x, y+rad, x-rad, y,
                        fill=fill_marker, outline="white", width=2
                    )
                    self.canvas.create_text(x, y-(15*self.zoom_level), text=f"Castle {c['id']}", fill="white", font=("Arial", int(8*self.zoom_level)))

                # Draw Castle Spawns
                for s in self.castle_spawn_cache:
                    sq, sr = s["q"], s["r"]
                    px, py = HexEngine.hex_to_pixel(sq, sr)
                    x, y = cx + px, cy + py
                    
                    rad = 8 * self.zoom_level
                    self.canvas.create_oval(x-rad, y-rad, x+rad, y+rad, fill="cyan", outline="white", width=1)
                    self.canvas.create_text(x, y+(15*self.zoom_level), text=s["monster_name"], fill="white", font=("Arial", int(8*self.zoom_level)))


    def _on_click(self, event):
        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)
        q, r = HexEngine.pixel_to_hex(cx - Config.CENTER_X, cy - Config.CENTER_Y)

        target_changed = (q != self.selected_q or r != self.selected_r)

        if target_changed:
            self.selected_q = q
            self.selected_r = r
            if hasattr(self, 'var_q'): # Check if standard inspector loaded
                self.var_q.set(str(q))
                self.var_r.set(str(r))
        
        mode = self.view_mode.get()
        if mode == "Standard":
            paint_del = getattr(self, "var_paint_delete", None) and self.var_paint_delete.get()
            if paint_del:
                self._delete_tile()
            elif self.var_paint_mode.get():
                if self.var_tile.get() or self.var_prop.get():
                    self._save_from_inspector()
                    self.render()
                elif target_changed:
                    self.render()
            elif target_changed:
                 existing = self.app.db.get_tile(q, r)
                 if existing: 
                     self._load_into_inspector(existing)
                 else:
                     self._load_into_inspector({})
                 self.render() # Rerender to show selection
                
        elif mode == "Levels":
            existing = self.app.db.get_tile(q, r)
            if not existing or not existing.get("texture_file"):
                self.app.show_toast("Cannot set level on an empty tile.")
                return
            # Direct Paint
            lvl = self.var_level_paint.get()
            self._update_tile_safe(q, r, {"level": lvl})
            
            # Sync monster level if one exists at this tile
            existing_monster = self.app.db.get_monster_at(q, r)
            if existing_monster:
                self.app.db.update_monster_level(q, r, lvl)
                
            self.render()

        elif mode == "Collision":
            col_mode = getattr(self, "var_collision_mode", None) and self.var_collision_mode.get()
            if col_mode == "passable":
                self._update_tile_safe(q, r, {"is_permanently_passable": 1})
            elif col_mode == "unpassable":
                self._update_tile_safe(q, r, {"is_permanently_passable": 0})
            self.render()

        elif mode == "Spawns":
            if target_changed:
                self.render()

        elif mode == "Items":
            item_fname = self.cb_items.get()
            if not item_fname:
                return
            
            # Load item data
            item_data = self.app.asset_mgr.load_json("item", item_fname)
            if item_data:
                # Add a copy to the map
                if self.app.db.add_item_to_map(item_data["name"], q, r, item_data):
                    self.refresh_cache()
                    self.render()
                else:
                    self.app.show_toast("Cannot place item on an empty tile.")
            
        elif mode == "Monsters":
            existing = self.app.db.get_monster_at(q, r)
            if existing:
                self.var_monster_health.set(existing.get("health", 50))
                self.var_monster_damage.set(existing.get("damage", 10))
                if hasattr(self, "btn_update_monster"):
                    self.btn_update_monster.config(state="normal")
                self.render()
                return

            # Left click places monster
            name = self.cb_monsters.get()
            if name:
                 # Need texture... load json to find it
                m_data = self.app.asset_mgr.load_json("monster", name)
                def_hp = m_data.get("default_health", 50)
                def_dmg = m_data.get("default_damage", 10)
                #get level of the tile to assign to monster
                tile = self.app.db.get_tile(q, r)
                monster_level = tile.get("level", 1) if tile else 1
                self.app.db.add_monster(name, q, r, def_hp, def_dmg, monster_level)

                self.var_monster_health.set(def_hp)
                self.var_monster_damage.set(def_dmg)
                if hasattr(self, "btn_update_monster"):
                    self.btn_update_monster.config(state="normal")
                self.refresh_cache()
                self.render()
            else:
                if hasattr(self, "btn_update_monster"):
                    self.btn_update_monster.config(state="disabled")
                self.var_monster_health.set(0)
                self.var_monster_damage.set(0)
                self.render()

        elif mode == "Castles":
            c_mode = getattr(self, "var_castle_mode", None) and self.var_castle_mode.get()
            if c_mode == "center":
                # Check if a castle already exists here (same tile)
                for c in self.castle_cache:
                    if c["q"] == q and c["r"] == r:
                        self.app.show_toast("A castle already exists on this tile!")
                        return

                # NEW: Check if this level already has a castle center
                tile = self.app.db.get_tile(q, r)
                lvl = tile.get("level", 1) if tile else 1
                
                for c in self.castle_cache:
                    if c["level"] == lvl:
                        self.app.show_toast(f"Level {lvl} already has a castle center!")
                        return

                # Get the asset info first
                castle_asset_fname = self.cb_castle_assets.get()
                if not castle_asset_fname:
                    self.app.show_toast("Select a castle asset from the list first!")
                    return
                    
                prop_data = self.app.asset_mgr.load_json("prop", castle_asset_fname)
                
                # Update tile art
                self._update_tile_safe(q, r, {
                    "prop_texture_file": prop_data.get("texture_file", ""),
                    "prop_scale": prop_data.get("prop_scale", 1.0),
                    "prop_x_shift": prop_data.get("prop_x_shift", 0),
                    "prop_y_shift": prop_data.get("prop_y_shift", 0)
                })
                
                tile = self.app.db.get_tile(q, r)
                lvl = tile.get("level", 1) if tile else 1
                new_id = self.app.db.add_map_castle(q, r, lvl, asset_file=castle_asset_fname)
                self.selected_castle_id = new_id
                
                # --- NEW: Apply Passability Footprint ---
                pmap = prop_data.get("passability_map", {})
                for k, v in pmap.items():
                    try:
                        dq, dr = eval(k) # k is string like "(0, 1)"
                        if v == False: # Impassable in template
                            self._update_tile_safe(q + dq, r + dr, {"is_permanently_passable": 0})
                    except: pass
                
                if hasattr(self, "lbl_sel_castle"): self.lbl_sel_castle.config(text=str(new_id))
                self.refresh_cache()
                self.render()
            elif c_mode == "select":
                for c in self.castle_cache:
                    if c["q"] == q and c["r"] == r:
                        self.selected_castle_id = c["id"]
                        if hasattr(self, "lbl_sel_castle"): self.lbl_sel_castle.config(text=str(c["id"]))
                        self.render()
                        break
            elif c_mode == "spawn":
                if not getattr(self, "selected_castle_id", None):
                    self.app.show_toast("Select a castle first!")
                    return

                # NEW: Level Restriction check
                # A spawn for a level X castle must be placed on a level X tile.
                target_tile = self.app.db.get_tile(q, r)
                target_lvl = target_tile.get("level", 1) if target_tile else 1
                
                c_data = next((c for c in self.castle_cache if c["id"] == self.selected_castle_id), None)
                castle_lvl = c_data["level"] if c_data else 0
                
                if target_lvl != castle_lvl:
                    self.app.show_toast(f"Spawns for Level {castle_lvl} must be on Level {castle_lvl} tiles!")
                    return

                # NEW: Block spawning on any castle center
                for c in self.castle_cache:
                    if c["q"] == q and c["r"] == r:
                        self.app.show_toast("Cannot place a spawn on a castle center!")
                        return

                # Check if a spawn already exists here
                for s in self.castle_spawn_cache:
                    if s["q"] == q and s["r"] == r:
                        self.app.show_toast("A castle spawn already exists on this tile!")
                        return

                m_name = self.cb_castle_monsters.get()
                if m_name:
                    def_hp = self.var_castle_monster_hp.get()
                    def_dmg = self.var_castle_monster_dmg.get()
                    self.app.db.add_castle_spawn(self.selected_castle_id, q, r, m_name, def_hp, def_dmg)
                    self.refresh_cache()
                    self.render()

    def _on_right_click(self, event):
        mode = self.view_mode.get()
        if mode == "Monsters":
            cx = self.canvas.canvasx(event.x)
            cy = self.canvas.canvasy(event.y)
            q, r = HexEngine.pixel_to_hex(cx - Config.CENTER_X, cy - Config.CENTER_Y)
            self.app.db.delete_monsters_at(q, r)
            if hasattr(self, "btn_update_monster") and self.selected_q == q and self.selected_r == r:
                self.btn_update_monster.config(state="disabled")
                self.var_monster_health.set(0)
                self.var_monster_damage.set(0)
            self.refresh_cache()
            self.render()
        elif mode == "Items":
            cx = self.canvas.canvasx(event.x)
            cy = self.canvas.canvasy(event.y)
            q, r = HexEngine.pixel_to_hex(cx - Config.CENTER_X, cy - Config.CENTER_Y)
            self.app.db.delete_items_at(q, r)
            self.refresh_cache()
            self.render()
        elif mode == "Castles":
            cx = self.canvas.canvasx(event.x)
            cy = self.canvas.canvasy(event.y)
            q, r = HexEngine.pixel_to_hex(cx - Config.CENTER_X, cy - Config.CENTER_Y)
            did_delete = False
            for s in self.castle_spawn_cache:
                if s["q"] == q and s["r"] == r:
                    self.app.db.delete_castle_spawn(q, r)
                    did_delete = True
            if not did_delete:
                for c in self.castle_cache:
                    if c["q"] == q and c["r"] == r:
                        # --- NEW: Reverse Passability Footprint ---
                        asset_fname = c.get("asset_file")
                        if asset_fname:
                            try:
                                prop_data = self.app.asset_mgr.load_json("prop", asset_fname)
                                pmap = prop_data.get("passability_map", {})
                                for k, v in pmap.items():
                                    try:
                                        dq, dr = eval(k)
                                        if v == False: # Was blocked, restore to passable
                                            self._update_tile_safe(q + dq, r + dr, {"is_permanently_passable": 1})
                                    except: pass
                            except: pass

                        self.app.db.delete_map_castle(q, r)
                        # Also clear the visual art associated with the castle center
                        self._update_tile_safe(q, r, {
                            "prop_texture_file": "",
                            "prop_scale": 1.0,
                            "prop_x_shift": 0,
                            "prop_y_shift": 0
                        })
                        if getattr(self, "selected_castle_id", None) == c["id"]:
                            self.selected_castle_id = None
                            if hasattr(self, "lbl_sel_castle"): self.lbl_sel_castle.config(text="None")
                        break
            self.refresh_cache()
            self.render()

    def _update_tile_safe(self, q, r, changes):
        # LEVEL SYNC & COLLISION DETECTION
        if "level" in changes:
            new_lvl = changes["level"]
            # Is there a castle anchor at this specific tile?
            this_castle = next((c for c in self.castle_cache if c["q"] == q and c["r"] == r), None)
            
            if this_castle:
                # Collision Check: Does ANOTHER castle already claim this new_lvl?
                for c in self.castle_cache:
                    if c["id"] != this_castle["id"] and c["level"] == new_lvl:
                        self.app.show_toast(f"Level {new_lvl} already has a castle elsewhere!")
                        return # Abort level update
                
                # Sync the castle logic record
                self.app.db.update_castle_level(q, r, new_lvl)
                self.refresh_cache()

        # Fetch existing or default
        data = self.app.db.get_tile(q, r)
        if not data:
            data = {
                "q": q, "r": r, 
                "tile_type": "grass", "texture_file": "", 
                "prop_texture_file": "", "prop_scale": 1.0, 
                "prop_x_shift": 0, "prop_y_shift": 0, "is_spawn": 0, "level": 1, "is_permanently_passable": 1
            }
        
        data.update(changes)
        self.app.db.save_tile(data)
        self.refresh_cache()
        self.render()

    def _load_into_inspector(self, data):
        tile_tex = data.get("texture_file", "")
        prop_tex = data.get("prop_texture_file", "")
        self.var_tile.set(tile_tex)
        self.var_prop.set(prop_tex)
        self.var_prop_scale.set(data.get("prop_scale", 1.0))
        self.var_prop_x_shift.set(data.get("prop_x_shift", 0))
        self.var_prop_shift.set(data.get("prop_y_shift", 0))

        if hasattr(self, "cb_tiles"):
            self.cb_tiles.set("")
            if tile_tex:
                for fname in self.cb_tiles["values"]:
                    jdata = self.app.asset_mgr.load_json("tile", fname)
                    if jdata.get("texture_file", "") == tile_tex:
                        self.cb_tiles.set(fname)
                        break

        if hasattr(self, "cb_props"):
            self.cb_props.set("")
            if prop_tex:
                for fname in self.cb_props["values"]:
                    jdata = self.app.asset_mgr.load_json("prop", fname)
                    if jdata.get("texture_file", "") == prop_tex:
                        self.cb_props.set(fname)
                        break

    def _save_from_inspector(self):
        if self.selected_q is None or self.selected_r is None:
            return

        tile_tex = self.var_tile.get()
        prop_tex = self.var_prop.get()

        # Block castle assets in standard mode
        if prop_tex and prop_tex in self.app.asset_mgr.castle_assets:
            if self.view_mode.get() != "Castles":
                self.app.show_toast("Please use Castle view mode to place castles.")
                return

        existing = self.app.db.get_tile(self.selected_q, self.selected_r)
        
        # Preserve existing texture if no new one is selected in the brush
        if not tile_tex and existing:
            tile_tex = existing.get("texture_file", "")

        if existing and existing.get("is_spawn") and prop_tex:
            self.app.show_toast("Cannot place a prop on a spawn point.")
            if not getattr(self, "var_paint_mode", None) or not self.var_paint_mode.get():
                prop_tex = ""
                self.var_prop.set("")
                if hasattr(self, "cb_props"):
                    self.cb_props.set("")
            return

        if not tile_tex and prop_tex:
            self.app.show_toast("Cannot place a prop on an empty tile.")
            if not getattr(self, "var_paint_mode", None) or not self.var_paint_mode.get():
                prop_tex = ""
                self.var_prop.set("")
                if hasattr(self, "cb_props"):
                    self.cb_props.set("")
            return

        changes = {
            "tile_type": existing.get("tile_type", "grass") if existing else "grass",
            "texture_file": tile_tex,
            "prop_texture_file": prop_tex,
            "prop_scale": self.var_prop_scale.get(),
            "prop_x_shift": self.var_prop_x_shift.get(),
            "prop_y_shift": self.var_prop_shift.get(),
        }
        self._update_tile_safe(self.selected_q, self.selected_r, changes)

    def _auto_save(self):
        self._save_from_inspector()
        self.render()

    def _browse(self, var):
        f = filedialog.askopenfilename(filetypes=[("Images", "*.png;*.jpg")])
        if f:
            base = os.path.basename(f)
            dest = os.path.join(Config.ASSET_DIR, base)
            if not os.path.exists(dest):
                shutil.copy(f, dest)
            var.set(base)
            self._save_from_inspector()
            self.render()

    def _on_tile_preset_select(self, event):
        fname = self.cb_tiles.get()
        data = self.app.asset_mgr.load_json("tile", fname)
        self.var_tile.set(data.get("texture_file", ""))
        self._save_from_inspector()
        self.render()

    def _on_prop_preset_select(self, event):
        if not self.var_tile.get() and not (getattr(self, "var_paint_mode", None) and self.var_paint_mode.get()):
            self.app.show_toast("Cannot add a prop to an empty tile. Add a base terrain tile first.")
            self.cb_props.set("")
            return
            
        fname = self.cb_props.get()
        data = self.app.asset_mgr.load_json("prop", fname)
        self.var_prop.set(data.get("texture_file", ""))
        self.var_prop_scale.set(data.get("prop_scale", 1.0))
        self.var_prop_x_shift.set(data.get("prop_x_shift", 0))
        self.var_prop_shift.set(data.get("prop_y_shift", 0))
        self._save_from_inspector()
        self.render()

    def _clear_prop(self):
        self.var_prop.set("")
        self._save_from_inspector()
        self.render()

    def _delete_tile(self):
        self.app.db.delete_tile(self.selected_q, self.selected_r)
        self.app.db.delete_monsters_at(self.selected_q, self.selected_r)
        self.refresh_cache()
        self.render()


class LibraryTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.anim_running = False
        self.current_frame = 0
        self.anim_timer = None
        self._vars_initialized = False
        self._init_vars()

        self._setup_ui()

    def _init_vars(self):
        if self._vars_initialized:
            return
        
        self.anim_data = {}
        self.is_loading = False

        # Shared (Prop/Tile/Anim)
        self.var_tex = tk.StringVar()
        self.var_scale = tk.DoubleVar(value=1.0)
        self.var_shift = tk.IntVar(value=0)
        self.var_x_shift = tk.IntVar(value=0)
        
        # Animation Specific
        self.var_anim_tex = tk.StringVar()
        self.var_anim_fw = tk.IntVar(value=32)
        self.var_anim_fh = tk.IntVar(value=32)
        self.var_anim_count = tk.IntVar(value=1)
        self.var_monster_def_health = tk.IntVar(value=50)
        self.var_monster_def_damage = tk.IntVar(value=10)
        
        # Item Specific
        self.var_item_type = tk.StringVar()
        self.var_item_tex = tk.StringVar()
        self.var_item_crop_x = tk.IntVar(value=0)
        self.var_item_crop_y = tk.IntVar(value=0)
        self.var_item_crop_size = tk.IntVar(value=32)
        self.var_item_desc = tk.StringVar()
        self.var_item_weight = tk.IntVar(value=1)
        self.var_item_base_damage = tk.IntVar(value=0)
        self.var_item_range = tk.IntVar(value=0)
        self.var_item_defense = tk.IntVar(value=0)
        self.var_item_max_durability = tk.IntVar(value=100)
        self.var_item_healing = tk.IntVar(value=0)
        self.var_item_hunger = tk.IntVar(value=0)
        self.var_item_power = tk.IntVar(value=0)
        self.var_item_slot = tk.StringVar(value="general")
        
        self.available_slots = ["weapon", "armor"]

        # Traces
        for v in [self.var_tex, self.var_scale, self.var_shift, self.var_x_shift]:
            v.trace_add("write", lambda *a: self._update_preview_static())
            
        for v in [self.var_anim_tex, self.var_anim_fw, self.var_anim_fh, self.var_anim_count, self.var_scale, self.var_shift, self.var_x_shift]:
            v.trace_add("write", lambda *a: self._on_anim_data_change())
            
        for v in [self.var_item_tex, self.var_item_crop_x, self.var_item_crop_y, self.var_item_crop_size]:
            v.trace_add("write", lambda *a: self._update_item_preview())
            
        self.var_item_type.trace_add("write", self._update_item_dynamic_fields)
        
        self._vars_initialized = True

    def _setup_ui(self):
        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill="both", expand=True)
        self.ctrl = ttk.Frame(paned, padding=10)
        paned.add(self.ctrl, weight=1)

        ttk.Label(self.ctrl, text="Asset Management", font=("Bold", 12)).pack(pady=10)
        self.var_cat = tk.StringVar(value="prop")
        f_cat = ttk.Frame(self.ctrl)
        f_cat.pack(fill="x", pady=5)
        for c in ["tile", "prop", "monster", "player", "item"]:
            ttk.Radiobutton(
                f_cat,
                text=c.capitalize(),
                variable=self.var_cat,
                value=c,
                command=self._on_category_change,
            ).pack(side=tk.LEFT)

        self.var_action_mode = tk.StringVar(value="new")
        self.f_action = ttk.Frame(self.ctrl)
        self.f_action.pack(fill="x", pady=(10, 5))
        ttk.Radiobutton(self.f_action, text="Make new", variable=self.var_action_mode, value="new", style="Toolbutton", command=self._on_action_mode_change).pack(side=tk.LEFT, expand=True, fill="x", padx=1)
        ttk.Radiobutton(self.f_action, text="Modify existing", variable=self.var_action_mode, value="modify", style="Toolbutton", command=self._on_action_mode_change).pack(side=tk.LEFT, expand=True, fill="x", padx=1)

        self.file_input_frame = ttk.Frame(self.ctrl)
        self.file_input_frame.pack(fill="x", pady=5)
        self.lbl_file = ttk.Label(self.file_input_frame, text="New Asset Name:", font=("Bold", 10))
        self.lbl_file.pack(anchor="w")

        self.entry_new_file = ttk.Entry(self.file_input_frame)
        self.cb_files = ttk.Combobox(self.file_input_frame, state="readonly")
        self.cb_files.bind("<<ComboboxSelected>>", self._load_file)

        # Item Type selection (shown only for Item category)
        self.f_item_type = ttk.Frame(self.file_input_frame)
        ttk.Label(self.f_item_type, text="Item Type:", font=("Bold", 10)).pack(anchor="w")
        
        type_row = ttk.Frame(self.f_item_type)
        type_row.pack(fill="x")
        self.cb_item_type = ttk.Combobox(type_row, textvariable=self.var_item_type, state="readonly")
        self.cb_item_type.pack(side=tk.LEFT, fill="x", expand=True)
        
        self.btn_new_cat = ttk.Button(type_row, text="+", width=3, command=self._add_item_category)
        self.btn_new_cat.pack(side=tk.LEFT, padx=2)
        self.btn_edit_cat = ttk.Button(type_row, text="📝", width=3, command=self._edit_item_category)
        self.btn_edit_cat.pack(side=tk.LEFT, padx=2)
        self.btn_del_cat = ttk.Button(type_row, text="-", width=3, command=self._delete_item_category)
        self.btn_del_cat.pack(side=tk.LEFT, padx=2)

        self.prop_frame = ttk.LabelFrame(self.ctrl, text="Properties", padding=5)
        self.prop_frame.pack(fill="both", expand=True, pady=10)
        ttk.Button(self.ctrl, text="SAVE ASSET", command=self._save_asset).pack(
            fill="x", pady=20
        )
        self.prev_frame = ttk.Frame(paned, padding=10)
        paned.add(self.prev_frame, weight=2)

        self.lbl_sheet = ttk.Label(self.prev_frame, text="Sprite Sheet Preview", font=("Bold", 10))
        self.f_sheet = ttk.Frame(self.prev_frame)
        self.sheet_canvas = Canvas(self.f_sheet, bg="#151515", height=200, highlightthickness=0)
        self.h_scroll = ttk.Scrollbar(self.f_sheet, orient=tk.HORIZONTAL, command=self.sheet_canvas.xview)
        self.sheet_canvas.config(xscrollcommand=self.h_scroll.set)
        self.sheet_canvas.pack(side=tk.TOP, fill="x", expand=True)
        self.h_scroll.pack(side=tk.BOTTOM, fill="x")

        self.lbl_anim = ttk.Label(self.prev_frame, text="Live Animation Preview", font=("Bold", 12))
        self.lbl_anim.pack()
        self.canvas = Canvas(self.prev_frame, bg="#303030")
        self.canvas.pack(fill="both", expand=True)

        self._on_action_mode_change()
        self._build_prop_ui()
        self._refresh_list()

    def _on_action_mode_change(self, select_name=None):
        mode = self.var_action_mode.get()
        is_item = self.var_cat.get() == "item"
        
        # Unpack all to ensure order
        self.lbl_file.pack_forget()
        self.entry_new_file.pack_forget()
        self.cb_files.pack_forget()
        self.f_item_type.pack_forget()
        
        # Pack Label first
        self.lbl_file.pack(fill="x", pady=(10, 0))
        
        if mode == "new":
            self.lbl_file.config(text="New Asset Name:")
            self.entry_new_file.pack(fill="x")
            self._clear_properties()
        else:
            self.lbl_file.config(text="Load Existing Asset:")
            self.cb_files.pack(fill="x")
            self._refresh_list(select_name=select_name)
            
        # Pack Type selector AFTER the name/file input
        if is_item:
            self.f_item_type.pack(fill="x", pady=5)

    def _clear_properties(self):
        if hasattr(self, 'anim_data'):
            self.anim_data = {}
        if hasattr(self, 'item_data'):
            self.item_data = {}
        if hasattr(self, 'var_tex') and self.var_tex:
            self.var_tex.set("")
        if hasattr(self, 'var_scale') and self.var_scale:
            self.var_scale.set(1.0)
        if hasattr(self, 'var_shift') and self.var_shift:
            self.var_shift.set(0)
        if hasattr(self, 'var_x_shift') and self.var_x_shift:
            self.var_x_shift.set(0)
        if hasattr(self, 'lb_anims') and self.lb_anims and self.lb_anims.winfo_exists():
            self.lb_anims.delete(0, tk.END)
            self.lb_anims.insert(tk.END, "idle")
            self.lb_anims.insert(tk.END, "move")
            self.lb_anims.insert(tk.END, "attack")
            
            if "animations" not in self.anim_data:
                self.anim_data["animations"] = {}
            for k in ["idle", "move", "attack"]:
                self.anim_data["animations"][k] = {"texture": "", "fw": 32, "fh": 32, "count": 1}
            
            self.lb_anims.selection_set(0) # Select "idle"
            self._update_anim_list_colors()
            self._on_anim_select(None)
            
        if hasattr(self, 'var_item_tex') and self.var_item_tex:
            self.var_item_tex.set("")
            self.var_item_crop_x.set(0)
            self.var_item_crop_y.set(0)
            self.var_item_crop_size.set(32)
            self.var_item_desc.set("")
            cats = self.app.asset_mgr.load_item_categories() if hasattr(self, 'app') and hasattr(self.app, 'asset_mgr') else {}
            self.var_item_type.set(list(cats.keys())[0] if cats else "")
            self.var_item_weight.set(1)
            self.var_item_base_damage.set(0)
            self.var_item_range.set(0)
            self.var_item_defense.set(0)
            self.var_item_max_durability.set(100)
            self.var_item_healing.set(0)
            self.var_item_hunger.set(0)
            self.var_item_power.set(0)
            self.var_item_slot.set("general")

        if hasattr(self, 'var_monster_def_health'):
            self.var_monster_def_health.set(50)
            self.var_monster_def_damage.set(10)

        if hasattr(self, 'entry_new_file') and self.entry_new_file.winfo_exists():
            self.entry_new_file.delete(0, tk.END)
        self.canvas.delete("all")
        if hasattr(self, 'sheet_canvas'):
            self.sheet_canvas.delete("all")
        self._stop_anim()

    def _on_category_change(self):
        self._stop_anim()
        cat = self.var_cat.get()
        
        # Reset visibility
        self.lbl_sheet.pack_forget()
        self.f_sheet.pack_forget()
        self.lbl_anim.pack_forget()
        self.canvas.pack_forget()

        if cat == "item":
            cats = self.app.asset_mgr.load_item_categories()
            # Filter out 'key' category from the general item editor
            item_cats = [c for c in cats.keys() if c != "key"]
            self.cb_item_type["values"] = item_cats
            if (not self.var_item_type.get() or self.var_item_type.get() == "key") and item_cats:
                self.var_item_type.set(item_cats[0])
            self.f_item_type.pack(fill="x", pady=5)
            self._build_item_ui()
            self.lbl_anim.pack()
            self.canvas.pack(fill="both", expand=True)
        else:
            self.f_item_type.pack_forget()
            if cat in ["monster", "player"]:
                self.lbl_sheet.pack(anchor="w")
                self.f_sheet.pack(fill="x", pady=(0, 10))
                self.lbl_anim.config(text="Live Animation Preview")
                self.lbl_anim.pack()
                self.canvas.pack(fill="both", expand=True)
                self._build_anim_ui()
                self._start_anim_loop()
            else:
                self.lbl_anim.config(text="Live Preview")
                self.lbl_anim.pack()
                self.canvas.pack(fill="both", expand=True)
                self._build_prop_ui()

        if self.var_action_mode.get() == "new":
            self._clear_properties()
        
        self._on_action_mode_change()
        self._refresh_list()

    def _build_prop_ui(self):
        for widget in self.prop_frame.winfo_children():
            widget.destroy()

        ttk.Label(self.prop_frame, text="Texture:").pack(anchor="w")
        h = ttk.Frame(self.prop_frame)
        h.pack(fill="x")
        ttk.Entry(h, textvariable=self.var_tex).pack(
            side=tk.LEFT, fill="x", expand=True
        )
        ttk.Button(
            h, text="...", width=3, command=lambda: self._browse(self.var_tex)
        ).pack(side=tk.LEFT)

        ttk.Label(self.prop_frame, text="Scale:").pack(anchor="w", pady=(5, 0))
        ttk.Scale(self.prop_frame, from_=0.1, to=3.0, variable=self.var_scale).pack(
            fill="x"
        )

        ttk.Label(self.prop_frame, text="X-Shift:").pack(anchor="w", pady=(5, 0))
        ttk.Scale(self.prop_frame, from_=-50, to=100, variable=self.var_x_shift).pack(
            fill="x"
        )

        ttk.Label(self.prop_frame, text="Y-Shift:").pack(anchor="w", pady=(5, 0))
        ttk.Scale(self.prop_frame, from_=-50, to=100, variable=self.var_shift).pack(
            fill="x"
        )

    def _build_anim_ui(self):
        for widget in self.prop_frame.winfo_children():
            widget.destroy()
            
        ttk.Label(self.prop_frame, text="Animations:", font=("Bold", 9)).pack(anchor="w")
        
        f_anims = ttk.Frame(self.prop_frame)
        f_anims.pack(fill="x", pady=5)
        self.lb_anims = tk.Listbox(f_anims, height=4, exportselection=False)
        self.lb_anims.pack(side=tk.LEFT, fill="x", expand=True)
        self.lb_anims.bind("<<ListboxSelect>>", self._on_anim_select)

        sc = ttk.Scrollbar(f_anims, orient=tk.VERTICAL, command=self.lb_anims.yview)
        sc.pack(side=tk.RIGHT, fill="y")
        self.lb_anims.config(yscrollcommand=sc.set)

        btn_frame = ttk.Frame(f_anims)
        btn_frame.pack(side=tk.LEFT, fill="y")
        ttk.Button(btn_frame, text="+", width=3, command=self._add_anim).pack()
        ttk.Button(btn_frame, text="-", width=3, command=self._del_anim).pack()

        ttk.Separator(self.prop_frame).pack(fill="x", pady=5)
        
        ttk.Label(self.prop_frame, text="Sprite Sheet:").pack(anchor="w")
        h = ttk.Frame(self.prop_frame)
        h.pack(fill="x")
        ttk.Entry(h, textvariable=self.var_anim_tex).pack(
            side=tk.LEFT, fill="x", expand=True
        )
        ttk.Button(
            h, text="...", width=3, command=lambda: self._browse(self.var_anim_tex)
        ).pack(side=tk.LEFT)

        grid = ttk.Frame(self.prop_frame)
        grid.pack(fill="x", pady=5)

        grid.columnconfigure(2, weight=1)

        ttk.Label(grid, text="Frame Width:").grid(row=0, column=0, sticky="w")
        ttk.Entry(grid, textvariable=self.var_anim_fw, width=5).grid(row=0, column=1, padx=2)
        ttk.Scale(grid, from_=8, to=256, variable=self.var_anim_fw, orient=tk.HORIZONTAL, command=lambda v: self.var_anim_fw.set(round(float(v)))).grid(row=0, column=2, sticky="we")

        ttk.Label(grid, text="Frame Height:").grid(row=1, column=0, sticky="w")
        ttk.Entry(grid, textvariable=self.var_anim_fh, width=5).grid(row=1, column=1, padx=2)
        ttk.Scale(grid, from_=8, to=256, variable=self.var_anim_fh, orient=tk.HORIZONTAL, command=lambda v: self.var_anim_fh.set(round(float(v)))).grid(row=1, column=2, sticky="we")

        ttk.Label(grid, text="Image Count:").grid(row=2, column=0, sticky="w")
        ttk.Entry(grid, textvariable=self.var_anim_count, width=5).grid(row=2, column=1, padx=2)
        ttk.Scale(grid, from_=1, to=64, variable=self.var_anim_count, orient=tk.HORIZONTAL, command=lambda v: self.var_anim_count.set(round(float(v)))).grid(row=2, column=2, sticky="we")

        ttk.Separator(self.prop_frame).pack(fill="x", pady=5)

        ttk.Label(self.prop_frame, text="Global Scale:").pack(anchor="w")
        ttk.Scale(self.prop_frame, from_=0.1, to=3.0, variable=self.var_scale).pack(
            fill="x"
        )

        ttk.Label(self.prop_frame, text="Global X-Shift:").pack(anchor="w")
        ttk.Scale(self.prop_frame, from_=-50, to=100, variable=self.var_x_shift).pack(
            fill="x"
        )

        ttk.Label(self.prop_frame, text="Global Y-Shift:").pack(anchor="w")
        ttk.Scale(self.prop_frame, from_=-50, to=100, variable=self.var_shift).pack(
            fill="x"
        )
        
        if self.var_cat.get() == "monster":
            ttk.Separator(self.prop_frame).pack(fill="x", pady=10)
            ttk.Label(self.prop_frame, text="Default Stats:", font=("Bold", 9)).pack(anchor="w")
            
            m_frame = ttk.Frame(self.prop_frame)
            m_frame.pack(fill="x", pady=5)
            
            ttk.Label(m_frame, text="Health:").grid(row=0, column=0, sticky="w")
            ttk.Entry(m_frame, textvariable=self.var_monster_def_health, width=8).grid(row=0, column=1, padx=5)
            
            ttk.Label(m_frame, text="Damage:").grid(row=1, column=0, sticky="w")
            ttk.Entry(m_frame, textvariable=self.var_monster_def_damage, width=8).grid(row=1, column=1, padx=5, pady=5)

    def _reset_item_stats(self):
        self.var_item_weight.set(1)
        self.var_item_base_damage.set(0)
        self.var_item_range.set(0)
        self.var_item_defense.set(0)
        self.var_item_max_durability.set(100)
        self.var_item_healing.set(0)
        self.var_item_hunger.set(0)
        self.var_item_power.set(0)
        self.var_item_slot.set("general")

    def _update_item_dynamic_fields(self, *args):
        if not self.is_loading:
            self._reset_item_stats()
        cat_name = self.var_item_type.get()
        cats = self.app.asset_mgr.load_item_categories()
        data = cats.get(cat_name, {})
        active_props = data.get("props", []) if isinstance(data, dict) else data
        for prop_name, (lbl, widget, row_idx) in getattr(self, "dynamic_widgets", {}).items():
            if not lbl.winfo_exists() or not widget.winfo_exists():
                continue
            if prop_name in active_props:
                lbl.grid(row=row_idx, column=0, sticky="w")
                widget.grid(row=row_idx, column=1, sticky="w")
            else:
                lbl.grid_remove()
                widget.grid_remove()

    def _delete_item_category(self):
        cats = self.app.asset_mgr.load_item_categories()
        if len(cats) <= 1:
            self.app.show_toast("Cannot delete the last category.")
            return

        del_top = tk.Toplevel(self)
        del_top.title("Delete Item Category")
        del_top.geometry("300x150")
        
        ttk.Label(del_top, text="Select category to delete:").pack(pady=(10,5))
        
        var_del = tk.StringVar(value=self.var_item_type.get() if self.var_item_type.get() in cats else list(cats.keys())[0])
        cb_del = ttk.Combobox(del_top, textvariable=var_del, values=list(cats.keys()), state="readonly")
        cb_del.pack(fill="x", padx=20, pady=5)
        
        def on_confirm_del():
            cat_to_del = var_del.get()
            if not cat_to_del or cat_to_del not in cats:
                self.app.show_toast("Please select a valid category.")
                return
            
            items_dir = Config.DIRS["item"]
            dependent_files = []
            if os.path.exists(items_dir):
                for fname in os.listdir(items_dir):
                    if fname.endswith(".json") and fname != "item_categories.json":
                        path = os.path.join(items_dir, fname)
                        try:
                            with open(path, "r") as f:
                                j = json.load(f)
                                if j.get("item_type") == cat_to_del:
                                    dependent_files.append(fname)
                        except:
                            pass
                            
            def _finalize_deletion(cat_name):
                del cats[cat_name]
                self.app.asset_mgr.save_item_categories(cats)
                if hasattr(self, "cb_item_type"):
                    self.cb_item_type["values"] = list(cats.keys())
                    if self.var_item_type.get() == cat_name:
                        self.var_item_type.set(list(cats.keys())[0])
                self.app.show_toast(f"Deleted category: {cat_name}")

            if not dependent_files:
                if messagebox.askyesno("Confirm Delete", f"Delete category '{cat_to_del}'?", parent=del_top):
                    _finalize_deletion(cat_to_del)
                    del_top.destroy()
                return

            reassign_top = tk.Toplevel(self)
            reassign_top.title("Reassign Items")
            reassign_top.geometry("380x200")
            ttk.Label(reassign_top, text=f"{len(dependent_files)} item(s) currently use '{cat_to_del}'.\nPlease select a new category for them:", justify="center").pack(pady=10)
            
            other_cats = [c for c in cats.keys() if c != cat_to_del]
            var_reassign = tk.StringVar(value=other_cats[0] if other_cats else "")
            
            cb_reassign = ttk.Combobox(reassign_top, textvariable=var_reassign, values=other_cats, state="readonly")
            cb_reassign.pack(fill="x", padx=20, pady=5)
            
            def on_reassign_and_delete():
                new_cat = var_reassign.get()
                if not new_cat or new_cat not in self.app.asset_mgr.load_item_categories():
                    self.app.show_toast("Please select a valid new category.")
                    return
                
                for fname in dependent_files:
                    path = os.path.join(items_dir, fname)
                    try:
                        with open(path, "r") as f:
                            j = json.load(f)
                        j["item_type"] = new_cat
                        with open(path, "w") as f:
                            json.dump(j, f, indent=4)
                    except Exception as e:
                        print(f"Failed to reassign {fname}: {e}")
                        
                _finalize_deletion(cat_to_del)
                reassign_top.destroy()
                del_top.destroy()

            btn_frame = ttk.Frame(reassign_top)
            btn_frame.pack(fill="x", pady=10, padx=10)
            ttk.Button(btn_frame, text="Reassign & Delete", command=on_reassign_and_delete).pack(side=tk.LEFT, expand=True, fill="x", padx=2)
            ttk.Button(btn_frame, text="Create New Category", command=self._add_item_category).pack(side=tk.LEFT, expand=True, fill="x", padx=2)
            
            def refresh_cb():
                if not reassign_top.winfo_exists():
                    return
                c2 = self.app.asset_mgr.load_item_categories()
                oc = [c for c in c2.keys() if c != cat_to_del]
                
                old_vals = cb_reassign["values"]
                if list(old_vals) != oc:
                    cb_reassign["values"] = oc
                    if var_reassign.get() not in oc and oc:
                        var_reassign.set(oc[-1])
                reassign_top.after(1000, refresh_cb)
                
            refresh_cb()

        ttk.Button(del_top, text="Delete", command=on_confirm_del).pack(pady=10)

    def _add_item_category(self):
        top = tk.Toplevel(self)
        top.title("New Item Category")
        top.geometry("300x350")
        ttk.Label(top, text="Category Name:").pack(pady=(10,0))
        var_name = tk.StringVar()
        ttk.Entry(top, textvariable=var_name).pack(fill="x", padx=10)
        
        ttk.Label(top, text="Select Properties:").pack(pady=(10,0))
        
        props_available = [
            ("slot", "Slot (per item)"),
            ("weight", "Weight"),
            ("base_damage", "Base Damage"),
            ("range", "Range"),
            ("defense", "Defense"),
            ("max_durability", "Max Durability"),
            ("healing_amount", "Healing Amount"),
            ("hunger_restore", "Hunger Restore"),
            ("power_bonus", "Power Bonus")
        ]
        
        var_checks = {}
        for p_id, p_label in props_available:
            var_checks[p_id] = tk.BooleanVar(value=False)
            ttk.Checkbutton(top, text=p_label, variable=var_checks[p_id]).pack(anchor="w", padx=20)
            
        def on_save():
            name = var_name.get().strip().lower()
            if not name:
                self.app.show_toast("Name cannot be empty.")
                return
            selected = [p_id for p_id, var in var_checks.items() if var.get()]
            cats = self.app.asset_mgr.load_item_categories()
            # Slot is now per-item property, so category-level slot defaults to general
            cats[name] = {"slot": "general", "props": selected}
            self.app.asset_mgr.save_item_categories(cats)
            
            if hasattr(self, "cb_item_type"):
                self.cb_item_type["values"] = list(cats.keys())
            self.var_item_type.set(name)
            self.app.show_toast(f"Added category: {name}")
            top.destroy()
            
        ttk.Button(top, text="Save Category", command=on_save).pack(pady=10)

    def _edit_item_category(self):
        cats = self.app.asset_mgr.load_item_categories()
        if not cats:
            self.app.show_toast("No categories to edit.")
            return

        top = tk.Toplevel(self)
        top.title("Edit Item Category")
        top.geometry("300x400")
        
        ttk.Label(top, text="Select Category to Edit:").pack(pady=(10,0))
        var_name = tk.StringVar(value=self.var_item_type.get() if self.var_item_type.get() in cats else list(cats.keys())[0])
        cb_cat = ttk.Combobox(top, textvariable=var_name, values=list(cats.keys()), state="readonly")
        cb_cat.pack(fill="x", padx=10)
        
        ttk.Label(top, text="Properties:").pack(pady=(10,0))
        
        props_available = [
            ("slot", "Slot (per item)"),
            ("weight", "Weight"),
            ("base_damage", "Base Damage"),
            ("range", "Range"),
            ("defense", "Defense"),
            ("max_durability", "Max Durability"),
            ("healing_amount", "Healing Amount"),
            ("hunger_restore", "Hunger Restore"),
            ("power_bonus", "Power Bonus")
        ]
        
        var_checks = {}
        for p_id, p_label in props_available:
            var_checks[p_id] = tk.BooleanVar(value=False)
            ttk.Checkbutton(top, text=p_label, variable=var_checks[p_id]).pack(anchor="w", padx=20)

        def update_checks(*args):
            selected_cat = var_name.get()
            if selected_cat in cats:
                data = cats[selected_cat]
                # Handle both migrated dict and legacy list formats safely
                current_props = data.get("props", []) if isinstance(data, dict) else data
                
                for p_id, var in var_checks.items():
                    var.set(p_id in current_props)
        
        var_name.trace_add("write", update_checks)
        update_checks() # Initial load

        def on_save():
            name = var_name.get()
            if not name: return
            selected = [p_id for p_id, var in var_checks.items() if var.get()]
            
            cats[name] = {"slot": "general", "props": selected}
            self.app.asset_mgr.save_item_categories(cats)
            
            # Refresh UI
            if hasattr(self, "cb_item_type"):
                self.cb_item_type["values"] = list(cats.keys())
            self.var_item_type.set(name)
            self._build_item_ui() # Rebuild the property fields in the sidebar
            self.app.show_toast(f"Updated category: {name}")
            top.destroy()
            
        ttk.Button(top, text="Save Changes", command=on_save).pack(pady=10)

    def _build_item_ui(self):
        for widget in self.prop_frame.winfo_children():
            widget.destroy()

        self.item_data = getattr(self, "item_data", {})
        
        style = ttk.Style()
        bg_color = style.lookup("TFrame", "background") or "#f0f0f0"
        
        canvas = tk.Canvas(self.prop_frame, highlightthickness=0, bg=bg_color)
        scrollbar = ttk.Scrollbar(self.prop_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        window_id = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(window_id, width=e.width))
        canvas.configure(yscrollcommand=scrollbar.set)
        
        scrollable_frame.columnconfigure(1, weight=1)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        row = 0
        
        # 1. Texture
        ttk.Label(scrollable_frame, text="Texture:").grid(row=row, column=0, sticky="w")
        h = ttk.Frame(scrollable_frame)
        h.grid(row=row, column=1, sticky="we")
        ttk.Entry(h, textvariable=self.var_item_tex).pack(side=tk.LEFT, fill="x", expand=True)
        ttk.Button(h, text="...", width=3, command=lambda: self._browse(self.var_item_tex)).pack(side=tk.LEFT)
        row += 1

        # 2. Crop Settings
        ttk.Label(scrollable_frame, text="Crop X:").grid(row=row, column=0, sticky="w")
        ttk.Scale(scrollable_frame, from_=0, to=512, variable=self.var_item_crop_x, orient="horizontal").grid(row=row, column=1, sticky="we"); row+=1
        
        ttk.Label(scrollable_frame, text="Crop Y:").grid(row=row, column=0, sticky="w")
        ttk.Scale(scrollable_frame, from_=0, to=512, variable=self.var_item_crop_y, orient="horizontal").grid(row=row, column=1, sticky="we"); row+=1

        ttk.Label(scrollable_frame, text="Crop Size:").grid(row=row, column=0, sticky="w")
        ttk.Scale(scrollable_frame, from_=8, to=256, variable=self.var_item_crop_size, orient="horizontal").grid(row=row, column=1, sticky="we"); row+=1

        # 3. Separator
        ttk.Label(scrollable_frame, text="- - - - - -").grid(row=row, column=0, columnspan=2); row+=1

        # 4. Description
        ttk.Label(scrollable_frame, text="Description:").grid(row=row, column=0, sticky="w")
        ttk.Entry(scrollable_frame, textvariable=self.var_item_desc).grid(row=row, column=1, sticky="we"); row+=1

        # 5. Dynamic Stats
        self.dynamic_widgets = {}

        stats_to_add = [
            ("slot", "Slot:"),
            ("weight", "Weight:"),
            ("base_damage", "Base Damage:"),
            ("range", "Range:"),
            ("defense", "Defense:"),
            ("max_durability", "Max Durability:"),
            ("healing_amount", "Healing Amount:"),
            ("hunger_restore", "Hunger Restore:"),
            ("power_bonus", "Power Bonus:")
        ]

        for p_id, p_label in stats_to_add:
            lbl = ttk.Label(scrollable_frame, text=p_label)
            if p_id == "slot":
                var = self.var_item_slot
                ent = ttk.Combobox(scrollable_frame, textvariable=var, values=self.available_slots, state="readonly", width=12)
            else:
                # Map p_id to variable name
                var_base = p_id.replace('healing_amount', 'healing').replace('hunger_restore', 'hunger').replace('power_bonus', 'power')
                var = getattr(self, f"var_item_{var_base}")
                ent = ttk.Entry(scrollable_frame, textvariable=var, width=8)
            
            self.dynamic_widgets[p_id] = (lbl, ent, row)
            row += 1

        self._update_item_dynamic_fields()
        self._update_item_preview()

    def _update_item_dynamic_fields(self, *args):
        if not hasattr(self, 'dynamic_widgets'):
            return
        
        # Determine which properties are active for the current item type
        cats = self.app.asset_mgr.load_item_categories()
        current_type = self.var_item_type.get().lower()
        data = cats.get(current_type, {})
        # Extract props list from the dict structure
        active_props = data.get("props", []) if isinstance(data, dict) else data
        
        # Toggle visibility of each dynamic widget
        for p_id, (lbl, ent, row) in self.dynamic_widgets.items():
            if p_id in active_props:
                lbl.grid(row=row, column=0, sticky="w", pady=2)
                ent.grid(row=row, column=1, sticky="we", pady=2)
            else:
                lbl.grid_forget()
                ent.grid_forget()


    def _update_item_preview(self):
        self.canvas.delete("all")
        tex = self.var_item_tex.get()
        if not tex:
            return
            
        path = os.path.join(Config.ASSET_DIR, tex)
        if not os.path.exists(path):
            return
            
        try:
            pil = Image.open(path)
            zoom = 2
            w, h = pil.size
            pil = pil.resize((w*zoom, h*zoom), Image.Resampling.NEAREST)
            tk_img = ImageTk.PhotoImage(pil)
            
            cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
            cx, cy = (cw//2, ch//2) if cw > 1 else (200, 200)
            
            self.canvas.create_image(cx, cy, image=tk_img)
            self.canvas.image = tk_img
            
            cx_orig = cx - (w*zoom)//2
            cy_orig = cy - (h*zoom)//2
            
            try:
                rx = self.var_item_crop_x.get() * zoom
                ry = self.var_item_crop_y.get() * zoom
                rs = self.var_item_crop_size.get() * zoom
                self.canvas.create_rectangle(cx_orig + rx, cy_orig + ry, cx_orig + rx + rs, cy_orig + ry + rs, outline="red", width=2)
            except:
                pass
        except:
            pass

    def _refresh_list(self, select_name=None):
        if hasattr(self, 'cb_files') and self.cb_files.winfo_exists():
            cat = self.var_cat.get()
            assets = self.app.asset_mgr.list_assets(cat)
            
            # Filter out castles from standard prop list
            if cat == "prop":
                castles = self.app.asset_mgr.list_castles()
                assets = [f for f in assets if f not in castles]

            # Filter out items of type 'key' if we are in the item category
            if cat == "item":
                filtered_assets = []
                for fname in assets:
                    try:
                        data = self.app.asset_mgr.load_json("item", fname)
                        if data.get("item_type") != "key":
                            filtered_assets.append(fname)
                    except:
                        filtered_assets.append(fname)
                assets = filtered_assets

            self.cb_files["values"] = assets
            if select_name and select_name in assets:
                self.cb_files.set(select_name)
            else:
                self.cb_files.set("")
                self.canvas.delete("all")

    def _load_file(self, event=None):
        self.is_loading = True
        try:
            name = self.cb_files.get()
            if not name:
                return
            data = self.app.asset_mgr.load_json(self.var_cat.get(), name)

            cat = self.var_cat.get()
            if cat in ["monster", "player"]:
                self.anim_data = data
                self.var_scale.set(data.get("scale", 1.0))
                self.var_x_shift.set(data.get("x_shift", 0))
                self.var_shift.set(data.get("y_shift", 0))
                self.lb_anims.delete(0, tk.END)
                anims = data.get("animations", {})
                for k in anims.keys():
                    self.lb_anims.insert(tk.END, k)
                self._update_anim_list_colors()
                if "idle" in anims:
                    idx = self.lb_anims.get(0, tk.END).index("idle")
                    self.lb_anims.selection_set(idx)
                    self._on_anim_select(None)
                elif anims:
                    self.lb_anims.selection_set(0)
                    self._on_anim_select(None)
                    
                if cat == "monster":
                    if hasattr(self, "var_monster_def_health"):
                        self.var_monster_def_health.set(data.get("default_health", 50))
                        self.var_monster_def_damage.set(data.get("default_damage", 10))

                self._start_anim_loop()

            elif cat == "item":
                self.item_data = data
                if hasattr(self, "var_item_tex"):
                    self.var_item_tex.set(data.get("texture_file", ""))
                    self.var_item_crop_x.set(data.get("crop_x", 0))
                    self.var_item_crop_y.set(data.get("crop_y", 0))
                    self.var_item_crop_size.set(data.get("crop_size", 32))
                    self.var_item_desc.set(data.get("description", ""))
                    cats = self.app.asset_mgr.load_item_categories() if hasattr(self, 'app') else {}
                    fallback = list(cats.keys())[0] if cats else ""
                    self.var_item_type.set(data.get("item_type", fallback))
                    self.var_item_slot.set(data.get("slot", data.get("item_slot", "general")))
                    self.var_item_weight.set(data.get("weight", 1))
                    self.var_item_base_damage.set(data.get("base_damage", 0))
                    self.var_item_range.set(data.get("range", 0))
                    self.var_item_defense.set(data.get("defense", 0))
                    self.var_item_max_durability.set(data.get("max_durability", 100))
                    self.var_item_healing.set(data.get("healing_amount", 0))
                    self.var_item_hunger.set(data.get("hunger_restore", 0))
                    self.var_item_power.set(data.get("power_bonus", 0))
                    self._update_item_preview()

            else:
                self.var_tex.set(data.get("texture_file", ""))
                self.var_scale.set(data.get("prop_scale", 1.0))
                self.var_x_shift.set(data.get("prop_x_shift", 0))
                self.var_shift.set(data.get("prop_y_shift", 0))
                self._update_preview_static()
        finally:
            self.is_loading = False
            if self.var_cat.get() in ["monster", "player"]:
                self._on_anim_data_change()

    def _add_anim(self):
        name = simpledialog.askstring(
            "New Animation", "Enter animation name (e.g., 'attack'):"
        )
        if name:
            if "animations" not in self.anim_data:
                self.anim_data["animations"] = {}
            self.anim_data["animations"][name] = {
                "texture": "",
                "fw": 32,
                "fh": 32,
                "count": 1,
            }
            self.lb_anims.insert(tk.END, name)
            self._update_anim_list_colors()

    def _del_anim(self):
        sel = self.lb_anims.curselection()
        if not sel:
            return
        key = self.lb_anims.get(sel[0])
        if key in self.anim_data.get("animations", {}):
            del self.anim_data["animations"][key]
            self.lb_anims.delete(sel[0])

    def _on_anim_select(self, event):
        sel = self.lb_anims.curselection()
        if not sel:
            return
        key = self.lb_anims.get(sel[0])

        anim = self.anim_data.get("animations", {}).get(key, {})
        self.var_anim_tex.set(anim.get("texture", ""))
        self.var_anim_fw.set(anim.get("fw", 32))
        self.var_anim_fh.set(anim.get("fh", 32))
        self.var_anim_count.set(anim.get("count", 1))

    def _on_anim_data_change(self):
        if not hasattr(self, 'lb_anims') or not self.lb_anims.winfo_exists():
            return
        if getattr(self, "is_loading", False):
            return
        sel = self.lb_anims.curselection()
        if not sel:
            return
        key = self.lb_anims.get(sel[0])

        if "animations" not in self.anim_data:
            self.anim_data["animations"] = {}

        try:
            self.anim_data["scale"] = self.var_scale.get()
            self.anim_data["x_shift"] = self.var_x_shift.get()
            self.anim_data["y_shift"] = self.var_shift.get()

            self.anim_data["animations"][key] = {
                "texture": self.var_anim_tex.get(),
                "fw": self.var_anim_fw.get(),
                "fh": self.var_anim_fh.get(),
                "count": self.var_anim_count.get(),
            }
            self._update_spritesheet_preview()
            self._update_anim_list_colors()
        except (tk.TclError, ValueError):
            pass

    def _browse(self, var):
        f = filedialog.askopenfilename(filetypes=[("Images", "*.png *.jpg")])
        if f:
            base = os.path.basename(f)
            dest = os.path.join(Config.ASSET_DIR, base)
            if not os.path.exists(dest):
                shutil.copy(f, dest)
            var.set(base)

    def _update_preview_static(self):
        self.canvas.delete("all")
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        cx, cy = (w // 2, h // 2) if w > 1 else (200, 200)

        preview_data = {
            "texture_file": "dirt.png",  # Dummy base
            "prop_texture_file": self.var_tex.get(),
            "prop_scale": self.var_scale.get(),
            "prop_x_shift": self.var_x_shift.get() if hasattr(self, 'var_x_shift') else 0,
            "prop_y_shift": self.var_shift.get(),
        }

        if self.var_cat.get() == "tile":
            preview_data["texture_file"] = self.var_tex.get()
            preview_data["tile_scale"] = self.var_scale.get()
            preview_data["tile_x_shift"] = self.var_x_shift.get() if hasattr(self, 'var_x_shift') else 0
            preview_data["tile_y_shift"] = self.var_shift.get()
            preview_data["prop_texture_file"] = None

        self.app.renderer.render_hex_at_pixel(
            self.canvas, cx, cy, preview_data, selected=True
        )

    def _stop_anim(self):
        if self.anim_timer:
            self.after_cancel(self.anim_timer)
            self.anim_timer = None
        self.anim_running = False

    def _start_anim_loop(self):
        self._stop_anim()
        self.anim_running = True
        self.current_frame = 0
        self._anim_loop()

    def _update_spritesheet_preview(self):
        if not hasattr(self, 'sheet_canvas'):
            return
        self.sheet_canvas.delete("all")
        
        try:
            tex = self.var_anim_tex.get()
            fw = self.var_anim_fw.get()
            fh = self.var_anim_fh.get()
            count = self.var_anim_count.get()
        except (tk.TclError, ValueError):
            return

        if not tex:
            return

        path = os.path.join(Config.ASSET_DIR, tex)
        if not os.path.exists(path):
            return

        try:
            pil = Image.open(path)
            cw = self.sheet_canvas.winfo_width()
            ch = self.sheet_canvas.winfo_height()
            if ch <= 1: ch = 200
            if cw <= 1: cw = 600
            
            # Scale to fit height of the canvas (max 200px)
            fit_scale = ch / float(pil.size[1])
            # fit_scale = min(fit_scale, 2.0) # Optional limit
            
            w_size = int(pil.size[0] * fit_scale)
            h_size = int(pil.size[1] * fit_scale)
            
            display_pil = pil.resize((w_size, h_size), Image.Resampling.NEAREST)
            self.sheet_tk_img = ImageTk.PhotoImage(display_pil)
            
            # Use scrollregion to handle overflow
            self.sheet_canvas.config(scrollregion=(0, 0, w_size, ch))
            
            # Center the image vertically if it's smaller than canvas height
            dy = (ch - h_size) // 2
            self.sheet_canvas.create_image(0, dy, anchor="nw", image=self.sheet_tk_img)
            
            scale_x = w_size / pil.size[0]
            scale_y = h_size / pil.size[1]
            
            for i in range(count):
                x = (i * fw) * scale_x
                y = dy
                w = fw * scale_x
                h = fh * scale_y
                self.sheet_canvas.create_rectangle(x, y, x + w, y + h, outline="red", width=2)
                self.sheet_canvas.create_text(x + 5, y + 5, text=str(i + 1), fill="white", anchor="nw", font=("Arial", 8, "bold"))
                
        except Exception as e:
            pass

    def _anim_loop(self):
        if not self.anim_running:
            return
        self.canvas.delete("all")
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        cx, cy = (w // 2, h // 2) if w > 1 else (200, 200)

        preview_data = {
            "tile_type": "grass",
            "texture_file": "dirt.png",  # Dummy base
            "prop_texture_file": None,
        }
        self.app.renderer.render_hex_at_pixel(
            self.canvas, cx, cy, preview_data, selected=True
        )
        sel = self.lb_anims.curselection()
        if sel:
            key = self.lb_anims.get(sel[0])
            anim = self.anim_data.get("animations", {}).get(key)
            if anim:
                tex = anim.get("texture")
                fw = anim.get("fw", 32)
                fh = anim.get("fh", 32)
                count = anim.get("count", 1)
                scale = self.var_scale.get()
                x_shift = self.var_x_shift.get()
                y_shift = self.var_shift.get()
                img = self.app.asset_mgr.get_anim_frame(
                    tex, self.current_frame, fw, fh, count, scale
                )
                if img:
                    self.canvas.create_image(
                        cx + x_shift, cy - Config.CALIB_OFFSET_Y - y_shift, image=img
                    )
                    self.canvas.image = img  # Keep ref
        self.current_frame += 1
        self.anim_timer = self.after(150, self._anim_loop)  # 150ms per frame

    def _update_anim_list_colors(self):
        if not hasattr(self, "lb_anims") or not self.lb_anims.winfo_exists():
            return
        anims = self.anim_data.get("animations", {})
        for i in range(self.lb_anims.size()):
            name = self.lb_anims.get(i)
            anim = anims.get(name, {})
            if not anim.get("texture"):
                self.lb_anims.itemconfig(i, foreground="red")
            else:
                self.lb_anims.itemconfig(i, foreground="black")

    def _save_asset(self):
        mode = self.var_action_mode.get()
        if mode == "new":
            name = getattr(self, "entry_new_file", None) and self.entry_new_file.get()
        else:
            name = getattr(self, "cb_files", None) and self.cb_files.get()
            
        if not name:
            self.app.show_toast("Please specify an asset name.")
            return

        cat = self.var_cat.get()

        if cat in ["monster", "player"]:
            self.anim_data["category"] = cat
            self.anim_data["name"] = name
            self.anim_data["scale"] = self.var_scale.get()
            self.anim_data["x_shift"] = self.var_x_shift.get()
            self.anim_data["y_shift"] = self.var_shift.get()
            if cat == "monster":
                if hasattr(self, "var_monster_def_health"):
                    self.anim_data["default_health"] = self.var_monster_def_health.get()
                    self.anim_data["default_damage"] = self.var_monster_def_damage.get()
            
            # Validation: Prevent out of bounds sprite rectangles
            if "animations" in self.anim_data:
                for anim_key, anim in self.anim_data["animations"].items():
                    tex = anim.get("texture")
                    if tex:
                        path_img = os.path.join(Config.ASSET_DIR, tex)
                        if os.path.exists(path_img):
                            try:
                                from PIL import Image
                                pil_img = Image.open(path_img)
                                w, h = pil_img.size
                                fw, fh = anim.get("fw", 32), anim.get("fh", 32)
                                count = anim.get("count", 1)
                                if fh > h:
                                    self.app.show_toast(f"Save failed: {anim_key} frame height ({fh}) exceeds image height ({h}).")
                                    return
                                if fw * count > w:
                                    self.app.show_toast(f"Save failed: {anim_key} total width ({fw*count}) exceeds image width ({w}).")
                                    return
                            except Exception:
                                pass
                                
            data = self.anim_data
        elif cat == "item":
            cats_load = self.app.asset_mgr.load_item_categories()
            itype = self.var_item_type.get() if hasattr(self, "var_item_type") else "melee"

            data = {
                "category": cat,
                "name": name,
                "texture_file": self.var_item_tex.get() if hasattr(self, "var_item_tex") else "",
                "crop_x": self.var_item_crop_x.get() if hasattr(self, "var_item_crop_x") else 0,
                "crop_y": self.var_item_crop_y.get() if hasattr(self, "var_item_crop_y") else 0,
                "crop_size": self.var_item_crop_size.get() if hasattr(self, "var_item_crop_size") else 32,
                "description": self.var_item_desc.get() if hasattr(self, "var_item_desc") else "",
                "item_type": itype,
                "item_slot": self.var_item_slot.get() if hasattr(self, "var_item_slot") else "general",
                "slot": self.var_item_slot.get() if hasattr(self, "var_item_slot") else "general",
                "weight": self.var_item_weight.get() if hasattr(self, "var_item_weight") else 1,
                "base_damage": self.var_item_base_damage.get() if hasattr(self, "var_item_base_damage") else 0,
                "range": self.var_item_range.get() if hasattr(self, "var_item_range") else 0,
                "defense": self.var_item_defense.get() if hasattr(self, "var_item_defense") else 0,
                "max_durability": self.var_item_max_durability.get() if hasattr(self, "var_item_max_durability") else 100,
                "healing_amount": self.var_item_healing.get() if hasattr(self, "var_item_healing") else 0,
                "hunger_restore": self.var_item_hunger.get() if hasattr(self, "var_item_hunger") else 0,
                "power_bonus": self.var_item_power.get() if hasattr(self, "var_item_power") else 0,
            }
        else:
            data = {
                "category": cat,
                "texture_file": self.var_tex.get(),
                "prop_scale": self.var_scale.get(),
                "prop_x_shift": self.var_x_shift.get(),
                "prop_y_shift": self.var_shift.get(),
            }

        full_name = name if name.endswith(".json") else name + ".json"
        self.app.asset_mgr.save_json(cat, name, data)
        self.app.show_toast(f"Saved {full_name}")
        
        if mode == "new":
            self.var_action_mode.set("modify")
            self._on_action_mode_change(select_name=full_name)
        else:
            self._refresh_list(select_name=full_name)
            
        self.app.map_tab.refresh_libraries()



class KeyTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.anim_tick = 0
        self.is_loading = False
        
        # Variables
        self.var_name = tk.StringVar()
        self.var_chest_link = tk.StringVar()
        self.var_variant = tk.IntVar(value=0) # 0: Blue, 1: White
        self.var_action_mode = tk.StringVar(value="new")
        
        # Default tile data for preview
        self.default_tile = self.app.asset_mgr.load_json("tile", "default.json")

        self._setup_ui()
        self._refresh_list()
        self._animate()

    def _setup_ui(self):
        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill="both", expand=True)
        
        # Left Panel: Controls
        ctrl = ttk.Frame(paned, padding=10)
        paned.add(ctrl, weight=1)
        
        ttk.Label(ctrl, text="Key Designer", font=("Bold", 12)).pack(pady=10)
        
        # Action Mode
        f_action = ttk.Frame(ctrl)
        f_action.pack(fill="x", pady=(0, 10))
        ttk.Radiobutton(f_action, text="Make New", variable=self.var_action_mode, value="new", style="Toolbutton", command=self._on_action_mode_change).pack(side=tk.LEFT, expand=True, fill="x")
        ttk.Radiobutton(f_action, text="Modify Existing", variable=self.var_action_mode, value="modify", style="Toolbutton", command=self._on_action_mode_change).pack(side=tk.LEFT, expand=True, fill="x")
        
        # Name / Selection
        self.lbl_name = ttk.Label(ctrl, text="Key Name:", font=("Bold", 10))
        self.lbl_name.pack(anchor="w")
        self.ent_name = ttk.Entry(ctrl, textvariable=self.var_name)
        self.ent_name.pack(fill="x", pady=(0, 10))
        
        self.cb_keys = ttk.Combobox(ctrl, state="readonly")
        self.cb_keys.bind("<<ComboboxSelected>>", self._on_key_select)
        
        # Properties
        prop_frame = ttk.LabelFrame(ctrl, text="Key Properties", padding=10)
        prop_frame.pack(fill="x", pady=10)
        
        ttk.Label(prop_frame, text="Link to Chest Name:").pack(anchor="w")
        self.cb_chest_link = ttk.Combobox(prop_frame, textvariable=self.var_chest_link, state="readonly")
        self.cb_chest_link["values"] = ["None", "CHEST_01", "CHEST_02", "CHEST_03"]
        self.cb_chest_link.pack(fill="x", pady=(0, 10))
        
        ttk.Label(prop_frame, text="Key Variant:").pack(anchor="w")
        f_var = ttk.Frame(prop_frame)
        f_var.pack(fill="x", pady=(0, 10))
        ttk.Radiobutton(f_var, text="Blue", variable=self.var_variant, value=0, command=self._update_preview).pack(side=tk.LEFT)
        ttk.Radiobutton(f_var, text="White", variable=self.var_variant, value=1, command=self._update_preview).pack(side=tk.LEFT)
        
        ttk.Button(ctrl, text="SAVE KEY", command=self._save_key).pack(fill="x", pady=5)
        ttk.Button(ctrl, text="DELETE KEY", command=self._delete_key).pack(fill="x", pady=5)
        
        # Right Panel: Preview
        preview_pane = ttk.Frame(paned, padding=10)
        paned.add(preview_pane, weight=2)
        
        ttk.Label(preview_pane, text="Animation Preview", font=("Bold", 12)).pack(pady=10)
        self.canvas = Canvas(preview_pane, bg="#303030", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

    def _on_action_mode_change(self):
        mode = self.var_action_mode.get()
        if mode == "new":
            self.cb_keys.pack_forget()
            self.ent_name.pack(fill="x", pady=(0, 10), after=self.lbl_name)
            self._clear_fields()
        else:
            self.ent_name.pack_forget()
            self.cb_keys.pack(fill="x", pady=(0, 10), after=self.lbl_name)
            self._refresh_list()

    def _clear_fields(self):
        self.var_name.set("")
        self.var_chest_link.set("None")
        self.var_variant.set(0)

    def _refresh_list(self):
        keys = []
        items_dir = Config.DIRS["item"]
        if os.path.exists(items_dir):
            for f in os.listdir(items_dir):
                if f.endswith(".json") and f != "item_categories.json":
                    try:
                        with open(os.path.join(items_dir, f), "r") as jf:
                            data = json.load(jf)
                            if data.get("item_type") == "key":
                                keys.append(f)
                    except:
                        pass
        self.cb_keys["values"] = sorted(keys)

    def _on_key_select(self, event):
        fname = self.cb_keys.get()
        if not fname: return
        path = os.path.join(Config.DIRS["item"], fname)
        with open(path, "r") as f:
            data = json.load(f)
            self.is_loading = True
            self.var_name.set(data.get("name", fname.replace(".json", "")))
            self.var_chest_link.set(data.get("chest_link", "None"))
            self.var_variant.set(data.get("key_variant", 0))
            self.is_loading = False
            self._update_preview()

    def _update_preview(self):
        if self.is_loading: return
        self.render()

    def _animate(self):
        self.anim_tick += 1
        self.render()
        self.after(200, self._animate)

    def render(self):
        if not hasattr(self, "canvas"): return
        self.canvas.delete("all")
        
        variant = self.var_variant.get()
        tex = "assetBank/Keys/key-blue.png" if variant == 0 else "assetBank/Keys/key-white.png"
        scale = Config.KEY_SCALE
        ox = Config.KEY_X_OFFSET
        oy = Config.KEY_Y_OFFSET
        
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        if cw < 2: cw, ch = 400, 400
        
        # Draw background tile
        if self.default_tile:
            tile_tex = self.default_tile.get("texture_file")
            if tile_tex:
                tile_s, tile_x, tile_y, _ = self.app.asset_mgr.get_asset_layout(tile_tex)
                tile_img = self.app.asset_mgr.get_tk_image(tile_tex, scale=tile_s)
                if tile_img:
                    self.canvas.create_image(cw//2 + tile_x, ch//2 - Config.CALIB_OFFSET_Y - tile_y, image=tile_img)

        img = self.app.asset_mgr.get_anim_frame(tex, self.anim_tick, 32, 32, 12, scale)
        if img:
            self.canvas.create_image(cw//2 + ox, ch//2 - Config.CALIB_OFFSET_Y - oy, image=img)
        
        self.canvas.create_text(10, 10, anchor="nw", text=f"Variant: {'Blue' if variant==0 else 'White'}", fill="white")
        self.canvas.create_text(10, 30, anchor="nw", text=f"Chest Link: {self.var_chest_link.get()}", fill="white")

    def _save_key(self):
        name = self.var_name.get().strip()
        if not name:
            self.app.show_toast("Please enter a key name.")
            return
            
        variant = self.var_variant.get()
        tex = "assetBank/Keys/key-blue.png" if variant == 0 else "assetBank/Keys/key-white.png"
        
        data = {
            "name": name,
            "item_type": "key",
            "chest_link": self.var_chest_link.get(),
            "key_variant": variant,
            "texture_file": tex,
            "scale": Config.KEY_SCALE,
            "x_offset": Config.KEY_X_OFFSET,
            "y_offset": Config.KEY_Y_OFFSET,
            "animations": {
                "idle": {
                    "texture": tex,
                    "fw": 32,
                    "fh": 32,
                    "count": 12
                }
            }
        }
        
        self.app.asset_mgr.save_json("item", name, data)
        self.app.show_toast(f"Saved key: {name}")
        self._refresh_list()
        
    def _delete_key(self):
        mode = self.var_action_mode.get()
        name = self.var_name.get() if mode == "new" else self.cb_keys.get().replace(".json", "")
        if not name: return
        
        if messagebox.askyesno("Confirm Delete", f"Delete key '{name}'?"):
            path = os.path.join(Config.DIRS["item"], name + ".json")
            if os.path.exists(path):
                os.remove(path)
                self.app.show_toast(f"Deleted key: {name}")
                self._clear_fields()
                self._refresh_list()


class CastleEditorTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.is_loading = False
        
        # Variables (Extended ranges)
        self.var_name = tk.StringVar()
        self.var_tex = tk.StringVar()
        self.var_scale = tk.DoubleVar(value=1.0)
        self.var_x_shift = tk.DoubleVar(value=0)
        self.var_y_shift = tk.DoubleVar(value=0)
        self.var_star_y_offset = tk.DoubleVar(value=50.0)
        
        # Linked precise inputs
        self.str_scale = tk.StringVar(value="1.0")
        self.str_x_shift = tk.StringVar(value="0")
        self.str_y_shift = tk.StringVar(value="0")
        self.str_star_y_offset = tk.StringVar(value="50.0")

        self.var_action_mode = tk.StringVar(value="new")
        
        # Default tile data for preview
        self.default_tile = self.app.asset_mgr.load_json("tile", "default.json")

        # Sync logic (Slider -> Entry)
        self.var_scale.trace_add("write", lambda *a: self._sync_val_to_str(self.var_scale, self.str_scale))
        self.var_x_shift.trace_add("write", lambda *a: self._sync_val_to_str(self.var_x_shift, self.str_x_shift))
        self.var_y_shift.trace_add("write", lambda *a: self._sync_val_to_str(self.var_y_shift, self.str_y_shift))
        self.var_star_y_offset.trace_add("write", lambda *a: self._sync_val_to_str(self.var_star_y_offset, self.str_star_y_offset))
        
        # Sync logic (Entry -> Slider)
        self.str_scale.trace_add("write", lambda *a: self._sync_str_to_val(self.str_scale, self.var_scale))
        self.str_x_shift.trace_add("write", lambda *a: self._sync_str_to_val(self.str_x_shift, self.var_x_shift))
        self.str_y_shift.trace_add("write", lambda *a: self._sync_str_to_val(self.str_y_shift, self.var_y_shift))
        self.str_star_y_offset.trace_add("write", lambda *a: self._sync_str_to_val(self.str_star_y_offset, self.var_star_y_offset))
        
        # Passability Map {(q, r): bool} where False means impassable
        self.passability_map = {}

        # Preview update
        for v in [self.var_tex, self.var_scale, self.var_x_shift, self.var_y_shift, self.var_star_y_offset]:
            v.trace_add("write", lambda *a: self._on_change())

        self.anim_tick = 0
        self._setup_ui()
        self._animate()

    def _sync_val_to_str(self, var, svar):
        if self.is_loading: return
        try:
            val = f"{var.get():.2f}"
            if svar.get() != val:
                svar.set(val)
        except: pass

    def _sync_str_to_val(self, svar, var):
        if self.is_loading: return
        try:
            val = float(svar.get())
            if var.get() != val:
                var.set(val)
        except: pass

    def _animate(self):
        self.anim_tick += 1
        self.render()
        # ~15 FPS matches the game's star animation speed
        self.after(66, self._animate)

    def _setup_ui(self):
        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill="both", expand=True)

        # Sidebar
        ctrl = ttk.Frame(paned, padding=10)
        paned.add(ctrl, weight=1)

        ttk.Label(ctrl, text="Castle Designer", font=("Bold", 14)).pack(pady=10)
        
        # Action selector
        f_mode = ttk.Frame(ctrl)
        f_mode.pack(fill="x", pady=5)
        ttk.Radiobutton(f_mode, text="New Castle", variable=self.var_action_mode, value="new", command=self._on_mode_change).pack(side=tk.LEFT, expand=True)
        ttk.Radiobutton(f_mode, text="Modify Existing", variable=self.var_action_mode, value="modify", command=self._on_mode_change).pack(side=tk.LEFT, expand=True)

        self.lbl_name = ttk.Label(ctrl, text="Asset Name:", font=("Bold", 10))
        self.lbl_name.pack(anchor="w", pady=(10, 0))
        
        self.ent_name = ttk.Entry(ctrl, textvariable=self.var_name)
        self.ent_name.pack(fill="x", pady=5)
        
        self.cb_load = ttk.Combobox(ctrl, state="readonly")
        self.cb_load.bind("<<ComboboxSelected>>", self._load_file)

        ttk.Label(ctrl, text="Texture File:", font=("Bold", 10)).pack(anchor="w", pady=(10, 0))
        f_tex = ttk.Frame(ctrl)
        f_tex.pack(fill="x")
        ttk.Entry(f_tex, textvariable=self.var_tex).pack(side=tk.LEFT, fill="x", expand=True)
        ttk.Button(f_tex, text="...", width=3, command=self._browse).pack(side=tk.LEFT, padx=2)

        props = ttk.LabelFrame(ctrl, text="Huge Prop Transformations", padding=10)
        props.pack(fill="x", pady=20)

        def add_precise_ctrl(parent, label, var, s_var, v_from, v_to):
            ttk.Label(parent, text=label).pack(anchor="w")
            row = ttk.Frame(parent)
            row.pack(fill="x", pady=(0, 10))
            ttk.Scale(row, from_=v_from, to=v_to, variable=var).pack(side=tk.LEFT, fill="x", expand=True)
            ttk.Entry(row, textvariable=s_var, width=8).pack(side=tk.LEFT, padx=(5, 0))

        add_precise_ctrl(props, "Scale (Full Castle Range):", self.var_scale, self.str_scale, 0.1, 10.0)
        add_precise_ctrl(props, "X Offset (Center Alignment):", self.var_x_shift, self.str_x_shift, -500.0, 500.0)
        add_precise_ctrl(props, "Y Offset (Center Alignment):", self.var_y_shift, self.str_y_shift, -500.0, 500.0)
        add_precise_ctrl(props, "Star Y Offset (Conquer Anim):", self.var_star_y_offset, self.str_star_y_offset, -200.0, 200.0)

        self.btn_save = ttk.Button(ctrl, text="SAVE PROOFS & DEFINITIONS", command=self._save)
        self.btn_save.pack(fill="x", pady=10)
        
        # Right Canvas Preview
        prev = ttk.Frame(paned, padding=10)
        paned.add(prev, weight=3)
        ttk.Label(prev, text="7-Tile Hex Cluster Preview", font=("Bold", 11)).pack()
        self.canvas = tk.Canvas(prev, bg="#1a1a1a", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self.render())
        self.canvas.bind("<Button-1>", self._on_canvas_click)

    def _on_mode_change(self):
        mode = self.var_action_mode.get()
        if mode == "new":
            self.cb_load.pack_forget()
            self.ent_name.pack(fill="x", pady=5, after=self.lbl_name)
            self._clear()
        else:
            self.ent_name.pack_forget()
            self.cb_load.pack(fill="x", pady=5, after=self.lbl_name)
            self._refresh_list()

    def _clear(self):
        self.var_name.set("")
        self.var_tex.set("")
        self.var_scale.set(1.0)
        self.var_x_shift.set(0.0)
        self.var_y_shift.set(0.0)
        self.var_star_y_offset.set(50.0)
        self.passability_map = {(0, 0): False}

    def _on_canvas_click(self, event):
        cw = self.canvas.winfo_width() / 2
        ch = self.canvas.winfo_height() / 2
        if cw < 1: cw, ch = 300, 300
        
        # Convert click to relative hex coordinate
        dq, dr = HexEngine.pixel_to_hex(event.x - cw, event.y - ch)
        
        # Limit to radius 2 (the shown cluster)
        if abs(dq) <= 2 and abs(dr) <= 2 and abs(-dq-dr) <= 2:
            current = self.passability_map.get((dq, dr), True)
            self.passability_map[(dq, dr)] = not current
            self.render()

    def _refresh_list(self):
        folder = Config.DIRS["prop"]
        castle_files = []
        for f in os.listdir(folder):
            if f.endswith(".json"):
                # Always include if 'castle' is in the name
                if "castle" in f.lower():
                    castle_files.append(f)
                    continue
                
                # Otherwise, check metadata for 'is_castle' flag
                try:
                    path = os.path.join(folder, f)
                    with open(path, "r") as jf:
                        data = json.load(jf)
                        if data.get("is_castle"):
                            castle_files.append(f)
                except:
                    pass
                    
        self.cb_load["values"] = sorted(list(set(castle_files)))

    def _load_file(self, e=None):
        fname = self.cb_load.get()
        if not fname: return
        path = os.path.join(Config.DIRS["prop"], fname)
        try:
            with open(path, "r") as f:
                data = json.load(f)
                self.is_loading = True
                self.var_name.set(fname.replace(".json", ""))
                self.var_tex.set(data.get("texture_file", ""))
                self.var_scale.set(data.get("prop_scale", 1.0))
                self.var_x_shift.set(data.get("prop_x_shift", 0.0))
                self.var_y_shift.set(data.get("prop_y_shift", 0.0))
                self.var_star_y_offset.set(data.get("star_y_offset", 50.0))
                
                # Load passability map
                pmap_raw = data.get("passability_map", {})
                self.passability_map = {}
                for k, v in pmap_raw.items():
                    # k is like "(0, 1)"
                    try:
                        coords = eval(k) # Safe here as it's our own format
                        self.passability_map[coords] = v
                    except: pass
                    
                self.is_loading = False
                self.render()
        except: pass

    def _browse(self):
        f = filedialog.askopenfilename(initialdir=Config.ASSET_DIR)
        if f:
            try:
                rel = os.path.relpath(f, Config.ASSET_DIR)
                self.var_tex.set(rel.replace("\\", "/"))
            except:
                self.var_tex.set(f)

    def _on_change(self):
        if self.is_loading: return
        self.render()

    def render(self):
        if not hasattr(self, "canvas"): return
        self.canvas.delete("all")
        cw = self.canvas.winfo_width() / 2
        ch = self.canvas.winfo_height() / 2
        if cw < 1: cw, ch = 300, 300

        # Collect all hexes in the cluster for Y-sorting
        render_items = []
        for q in range(-2, 3):
            r1 = max(-2, -q - 2)
            r2 = min(2, -q + 2)
            for r in range(r1, r2 + 1):
                px, py = HexEngine.hex_to_pixel(q, r)
                render_items.append((q, r, cw + px, ch + py))
        
        # Sort by Y-coordinate (Top-down rendering)
        render_items.sort(key=lambda x: x[3])

        # Pass 1: Draw background tiles
        for q, r, x, y in render_items:
            if self.default_tile:
                tile_tex = self.default_tile.get("texture_file")
                if tile_tex:
                    tile_s, tile_x, tile_y, _ = self.app.asset_mgr.get_asset_layout(tile_tex)
                    tile_img = self.app.asset_mgr.get_tk_image(tile_tex, scale=tile_s)
                    if tile_img:
                        self.canvas.create_image(x + tile_x, y - Config.CALIB_OFFSET_Y - tile_y, image=tile_img)

        # Pass 2: Main Asset
        tex = self.var_tex.get()
        if tex:
            scale = self.var_scale.get()
            img = self.app.asset_mgr.get_tk_image(tex, scale=scale)
            if img:
                ox = self.var_x_shift.get()
                oy = self.var_y_shift.get()
                # Apply same vertical calib offset as the game renderer
                self.canvas.create_image(cw + ox, ch - Config.CALIB_OFFSET_Y - oy, image=img)
                self.canvas.image = img # Keep reference
                
        # Pass 2.5: Conquer Star Preview
        star_offset = self.var_star_y_offset.get()
        # star.png is 416x32, with 13 frames of 32x32 each.
        # In main game it scales to target_size=48, which is a 1.5x scale.
        # Animation speed: self.after(66) matches the game's ~15 FPS (60 FPS / 4 slowdown)
        star_img = self.app.asset_mgr.get_anim_frame("star.png", self.anim_tick, fw=32, fh=32, count=13, scale=1.5)
        if star_img:
            self.canvas.create_image(
                cw, 
                ch - Config.CALIB_OFFSET_Y - star_offset, 
                image=star_img, 
                tags="star_preview"
            )
            self.canvas.star_img = star_img # Keep reference

        # Pass 3: Hex Overlays (Outlines, Passability X, Coordinates)
        for q, r, x, y in render_items:
            pts = HexEngine.get_hex_polygon(x, y)
            
            fill = ""
            outline = "#555"
            width = 1
            if q == 0 and r == 0:
                outline = "#ff4444"  # Stronger anchor highlight
                width = 2
            
            self.canvas.create_polygon(pts, fill=fill, outline=outline, width=width)
            
            # --- Passability Indicator ---
            if self.passability_map.get((q, r)) == False:
                # Draw a red X or stipple
                self.canvas.create_polygon(pts, fill="red", stipple="gray25", outline="red", width=1)
                self.canvas.create_text(x, y, text="X", fill="white", font=("Arial", int(12)))
            
            self.canvas.create_text(x, y + 15, text=f"{q},{r}", fill="#555", font=("Arial", 8))

        # Red Dot anchor point
        self.canvas.create_oval(cw-3, ch-3, cw+3, ch+3, fill="#ff4444", outline="white")

    def _save(self):
        name = self.var_name.get().strip()
        tex = self.var_tex.get().strip()
        if not name or not tex:
            messagebox.showwarning("Incomplete", "Please provide name and texture.")
            return

        # Convert tuple keys to strings for JSON
        pmap_json = {str(k): v for k, v in self.passability_map.items()}
        
        data = {
            "texture_file": tex,
            "prop_scale": self.var_scale.get(),
            "prop_x_shift": int(self.var_x_shift.get()),
            "prop_y_shift": int(self.var_y_shift.get()),
            "star_y_offset": float(self.var_star_y_offset.get()),
            "is_castle": True,
            "passability_map": pmap_json
        }
        
        path = os.path.join(Config.DIRS["prop"], f"{name}.json")
        with open(path, "w") as f:
            json.dump(data, f, indent=4)
        
        self.app.show_toast(f"Saved: {name}")
        self.app.asset_mgr.refresh_layouts()
        if self.var_action_mode.get() == "modify":
            self._refresh_list()


class MainApp:
    def __init__(self, root, db_file="game_data.db"):
        self.root = root
        self.root.title(f"Hex Architect - {db_file}")
        self.root.geometry("1400x900")
        self.db = DatabaseManager(db_file)
        self.asset_mgr = AssetManager()
        self.renderer = Renderer(self.asset_mgr)
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True, padx=5, pady=5)
        self.map_tab = MapTab(self.notebook, self)
        self.lib_tab = LibraryTab(self.notebook, self)
        self.castle_tab = CastleEditorTab(self.notebook, self)
        self.key_tab = KeyTab(self.notebook, self)
        self.notebook.add(self.map_tab, text="Map Designer")
        self.notebook.add(self.lib_tab, text="Asset Library")
        self.notebook.add(self.castle_tab, text="Castle Designer")
        self.notebook.add(self.key_tab, text="Key Designer")
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
        
        self.map_tab.refresh_libraries()
        self.map_tab.render()

    def _on_closing(self):
        missing = self.db.get_missing_castle_levels()
        if missing:
            msg = f"Warning: The following levels are missing castles:\n\n"
            msg += ", ".join([f"Level {l}" for l in missing])
            msg += "\n\nAre you sure you want to exit?"
            if not messagebox.askyesno("Map Integrity Check", msg):
                return
        self.root.destroy()

    def _on_tab_changed(self, event):
        # Determine which tab is selected
        selected_id = self.notebook.select()
        if not selected_id:
            return
            
        tab_name = self.notebook.tab(selected_id, "text")
        if tab_name == "Map Designer":
            # Refresh libraries (dropdowns) and render (art/props)
            self.map_tab.refresh_libraries()
            self.map_tab.render()
        elif tab_name == "Key Designer":
            self.key_tab._refresh_list()
        elif tab_name == "Castle Designer":
            self.castle_tab._refresh_list()

    def show_toast(self, message):
        toast = tk.Toplevel(self.root)
        toast.overrideredirect(True)
        toast.attributes("-alpha", 0.0)
        toast.configure(bg="#333333")
        
        lbl = tk.Label(toast, text=message, fg="white", bg="#333333", font=("Arial", 10, "bold"), padx=15, pady=10)
        lbl.pack()
        
        self.root.update_idletasks()
        w = toast.winfo_width()
        h = toast.winfo_height()
        
        x = self.root.winfo_x() + self.root.winfo_width() - w - 20
        y = self.root.winfo_y() + 20
        toast.geometry(f"+{x}+{y}")
        
        def fade_in(alpha=0.0):
            if alpha < 0.9:
                alpha += 0.1
                toast.attributes("-alpha", alpha)
                self.root.after(20, lambda: fade_in(alpha))
            else:
                self.root.after(2000, fade_out)
                
        def fade_out(alpha=0.9):
            if alpha > 0.0:
                alpha -= 0.1
                toast.attributes("-alpha", alpha)
                self.root.after(30, lambda: fade_out(alpha))
            else:
                toast.destroy()
                
        fade_in()


if __name__ == "__main__":
    db_filename = "default.db"
    print(f"Loading Editor Template: {db_filename}...")

    root = tk.Tk()
    style = ttk.Style()
    style.theme_use("clam")
    app = MainApp(root, db_file=db_filename)
    root.mainloop()
