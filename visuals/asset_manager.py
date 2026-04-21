import os
import json
import pygame
from core.config import Config

class AssetManager:
    def __init__(self):
        self.cache = {}
        self.layouts = {}  # Map: texture_filename -> (scale, y_shift)
        self.anim_metadata = {}  # Map: texture_filename -> {fw, fh, count}
        self.castle_assets = set()
        self._load_layouts()

    def _load_layouts(self):
        """Scans definition files."""
        # Using Config.DIRS values
        search_dirs = list(Config.DIRS.values())

        for d in search_dirs:
            if not os.path.exists(d):
                continue

            for f in os.listdir(d):
                if f.endswith(".json"):
                    try:
                        with open(os.path.join(d, f), "r") as jf:
                            data = json.load(jf)
                            
                            # Caching metadata for animations
                            if "animations" in data:
                                for anim_name, anim_data in data["animations"].items():
                                    tex = anim_data.get("texture")
                                    if tex:
                                        # Per-(texture, row) metadata so one sheet
                                        # can host multiple animation tracks
                                        row = anim_data.get("row", 0)
                                        self.anim_metadata[(tex, row)] = {
                                            "fw": anim_data.get("fw", 32),
                                            "fh": anim_data.get("fh", 32),
                                            "count": anim_data.get("count", 1),
                                            "scale": data.get("scale", 1.0),
                                            "x_shift": data.get("x_shift", 0),
                                            "y_shift": data.get("y_shift", 0),
                                            "row": row,
                                        }
                                        # Legacy single-row lookup still works
                                        if tex not in self.anim_metadata:
                                            self.anim_metadata[tex] = self.anim_metadata[(tex, row)]
                                        self.layouts[tex] = (
                                            float(data.get("scale", 1.0)),
                                            int(data.get("x_shift", 0)),
                                            int(data.get("y_shift", 0)),
                                            50.0  # Default star_y_offset for non-castle entities
                                        )
                            
                            tex = data.get("texture_file")
                            if not tex and "animations" in data:
                                tex = data["animations"].get("idle", {}).get("texture")

                            if tex:
                                s = data.get("prop_scale") or data.get("scale", 1.0)
                                x = data.get("prop_x_shift") or data.get("x_shift", 0)
                                y = data.get("prop_y_shift") or data.get("prop_shift") or data.get("y_shift", 0)
                                star_y = data.get("star_y_offset", 50.0)
                                self.layouts[tex] = (float(s), int(x), int(y), float(star_y))
                                
                                # Detect castles for separate rendering pass
                                if data.get("is_castle") or "castle" in f.lower():
                                    self.castle_assets.add(tex)
                    except Exception as e:
                        print(f"Error loading layout {f}: {e}")

    def get_layout(self, filename):
        """Returns (scale, x_shift, y_shift, star_y_offset) for a given texture file."""
        return self.layouts.get(filename, (1.0, 0, 0, 50.0))

    def is_castle(self, filename):
        return filename in self.castle_assets

    def get_anim_frame(self, filename, frame_index=0, row=0):
        """Extracts and scales a specific frame from a sprite sheet.

        `row` selects the horizontal strip inside a multi-row sheet
        (e.g. chest sheet has 8 rows for 4 colors x 2 states).
        """
        if not filename:
            return None

        meta_key = (filename, row) if (filename, row) in self.anim_metadata else filename
        if meta_key not in self.anim_metadata:
            return self.get_image(filename)  # Fallback to static

        meta = self.anim_metadata[meta_key]
        path = os.path.join(Config.ASSET_DIR, filename)

        # Key includes frame_index + row so we cache each frame individually
        key = (filename, frame_index, row, "anim")
        if key in self.cache:
            return self.cache[key]

        if not os.path.exists(path):
            return None

        try:
            # Helper to load raw sheet
            if filename not in self.cache:
                 self.cache[filename] = pygame.image.load(path).convert_alpha()

            sheet = self.cache[filename]

            fw = meta["fw"]
            fh = meta["fh"]
            count = meta["count"]
            scale = meta["scale"]

            safe_idx = frame_index % max(1, count)
            x = safe_idx * fw
            y = row * fh

            if x + fw > sheet.get_width():
                x = 0
            if y + fh > sheet.get_height():
                y = 0
            frame_surf = sheet.subsurface((x, y, fw, fh))
            
            target_w = int(fw * scale)
            target_h = int(fh * scale)
            
            scaled_surf = pygame.transform.scale(frame_surf, (target_w, target_h))
            
            self.cache[key] = scaled_surf
            return scaled_surf
            
        except Exception as e:
            print(f"Anim Error {filename}: {e}")
            return None

    def get_image(self, filename, scale=None, scale_to_tile=True):
        if not filename:
            return None
        
        # Special case: animation sheet being accessed as a static image
        if filename in self.anim_metadata:
            return self.get_anim_frame(filename, 0)
        
        if scale is None:
            scale, _, _, _ = self.get_layout(filename)
            
        key = (filename, scale, scale_to_tile)
        if key in self.cache:
            return self.cache[key]

        path = os.path.join(Config.ASSET_DIR, filename)
        if not os.path.exists(path):
            return None

        try:
            raw_img = pygame.image.load(path).convert_alpha()
            
            if scale_to_tile:
                # Scale relative to hex size
                target_w = max(1, int(Config.HEX_SIZE * scale))
                w, h = raw_img.get_size()
                ratio = target_w / w
                target_h = int(h * ratio)
                img = pygame.transform.scale(raw_img, (target_w, target_h))
            else:
                # Use raw size or simple scale multiply if scale != 1.0
                if scale != 1.0:
                    w, h = raw_img.get_size()
                    img = pygame.transform.scale(raw_img, (int(w*scale), int(h*scale)))
                else:
                    img = raw_img
            
            self.cache[key] = img
            return img
        except Exception as e:
            print(f"Failed to load {filename}: {e}")
            return None
