from numpy import tile
import pygame
import math
from core.config import Config
from core.hexmath import HexMath
from gameplay import world


class GameRenderer:
    def __init__(self, asset_manager):
        self.assets = asset_manager
        self.COLOR_BG = (17, 17, 17)
        self.COLOR_GRASS = (46, 59, 40)
        self.COLOR_WATER = (40, 59, 69)
        self.COLOR_STONE = (56, 56, 56)
        self.COLOR_OUTLINE = (34, 34, 34)

        # render cache pool, to reduce lagging
        self.image_cache = {}

        # load cloud images into list
        self.cloud_images = []

        for image_number in range(1, 21):
            image = pygame.image.load(
                f"assets/assetBank/clouds/Cloud {image_number}.png"
            ).convert_alpha()
            self.cloud_images.append(image)

    def render(self, screen, world, frame_index=0):
        screen.fill(self.COLOR_BG)

        player = world.player
        if not player:
            return

        cx = Config.CENTER_X
        cy = Config.CENTER_Y
        render_range = 15

        # if the player is moving, let the camera focus on the player for interpolation
        if getattr(player, "is_moving", False):
            from_px, from_py = HexMath.hex_to_pixel(
                player.move_from_q, player.move_from_r
            )
            to_px, to_py = HexMath.hex_to_pixel(player.move_to_q, player.move_to_r)
            t = player.move_progress

            ppx = from_px + (to_px - from_px) * t
            ppy = from_py + (to_py - from_py) * t
        else:
            ppx, ppy = HexMath.hex_to_pixel(player.q, player.r)

        terrain_layer = []
        object_layer = []  # Scenery: Monsters, Player, Items, Chests
        castle_layer = []  # Castles: Large structures rendered on top for visual clarity

        # Iterate tiles around player
        for q in range(player.q - render_range, player.q + render_range):
            for r in range(player.r - render_range, player.r + render_range):
                if HexMath.distance(q, r, player.q, player.r) > render_range:
                    continue

                tile = world.get_tile(q, r)
                if not tile:
                    continue

                px, py = HexMath.hex_to_pixel(q, r)

                draw_x = cx + (px - ppx)
                draw_y = cy + (py - ppy)

                # Culling
                if (
                    -100 < draw_x < Config.WINDOW_WIDTH + 100
                    and -100 < draw_y < Config.WINDOW_HEIGHT + 100
                ):
                    terrain_layer.append((tile, draw_x, draw_y))
                    if tile.discovered and tile.prop_texture:
                        # NEW: Separate castles from standard objects
                        obj_data = {
                            "depth": draw_y,
                            "type": "prop",
                            "tile": tile,
                            "x": draw_x,
                            "y": draw_y,
                        }
                        if self.assets.is_castle(tile.prop_texture):
                            castle_layer.append(obj_data)
                        else:
                            object_layer.append(obj_data)

        # Add Player
        object_layer.append(
            {"depth": cy, "type": "entity", "entity": player, "x": cx, "y": cy}
        )

        # Add Monsters
        for monster in world.monsters:
            tile = world.get_tile(monster.q, monster.r)
            if not tile or not tile.discovered:
                continue

            if getattr(monster, "is_moving", False):
                from_px, from_py = HexMath.hex_to_pixel(
                    monster.move_from_q, monster.move_from_r
                )
                to_px, to_py = HexMath.hex_to_pixel(
                    monster.move_to_q, monster.move_to_r
                )
                t = monster.move_progress

                mqx = from_px + (to_px - from_px) * t
                mqy = from_py + (to_py - from_py) * t
            else:
                mqx, mqy = HexMath.hex_to_pixel(monster.q, monster.r)

            mdx = cx + (mqx - ppx)
            mdy = cy + (mqy - ppy)

            # Culling
            if (
                -100 < mdx < Config.WINDOW_WIDTH + 100
                and -100 < mdy < Config.WINDOW_HEIGHT + 100
            ):
                object_layer.append(
                    {
                        "depth": mdy,
                        "type": "entity",
                        "entity": monster,
                        "x": mdx,
                        "y": mdy,
                    }
                )

        # Add Assistants
        for assistant in getattr(world, "assistants", []):
            tile = world.get_tile(assistant.q, assistant.r)
            # Only render if the tile is discovered by the player
            if not tile or not tile.discovered:
                continue

            # Handle smooth tile-to-tile movement interpolation
            if getattr(assistant, "is_moving", False):
                from_px, from_py = HexMath.hex_to_pixel(assistant.move_from_q, assistant.move_from_r)
                to_px, to_py = HexMath.hex_to_pixel(assistant.move_to_q, assistant.move_to_r)
                t = assistant.move_progress

                aqx = from_px + (to_px - from_px) * t
                aqy = from_py + (to_py - from_py) * t
            else:
                # Stand still if not moving
                aqx, aqy = HexMath.hex_to_pixel(assistant.q, assistant.r)
                
            # Convert world hex coordinates to screen pixel coordinates
            adx = cx + (aqx - ppx)
            ady = cy + (aqy - ppy)
            
            # Culling: Only add to the render list if it's within the screen bounds
            if (
                -100 < adx < Config.WINDOW_WIDTH + 100
                and -100 < ady < Config.WINDOW_HEIGHT + 100
            ):
                # Add to the depth-sorted object layer
                # We use "type": "entity" so it reuses the monster/player drawing logic
                object_layer.append(
                    {"depth": ady, "type": "entity", "entity": assistant, "x": adx, "y": ady}
                )
                
        # Add Chests
        for chest in world.chests:
            cqx, cqy = HexMath.hex_to_pixel(chest.q, chest.r)
            cdxp = cx + (cqx - ppx)
            cdyp = cy + (cqy - ppy)
            if (
                -100 < cdxp < Config.WINDOW_WIDTH + 100
                and -100 < cdyp < Config.WINDOW_HEIGHT + 100
            ):
                object_layer.append(
                    {
                        "depth": cdyp,
                        "type": "chest",
                        "chest": chest,
                        "x": cdxp,
                        "y": cdyp,
                    }
                )

        # Add Castle Stars
        if hasattr(world, "castles"):
            for castle in world.castles:
                if castle.is_conquered and castle.level <= world.current_level:
                    cqx, cqy = HexMath.hex_to_pixel(castle.q, castle.r)
                    cdxp = cx + (cqx - ppx)
                    cdyp = cy + (cqy - ppy)
                    if (
                        -100 < cdxp < Config.WINDOW_WIDTH + 100
                        and -100 < cdyp < Config.WINDOW_HEIGHT + 100
                    ):
                        tile = world.get_tile(castle.q, castle.r)
                        star_y = 50.0
                        if tile and tile.prop_texture:
                            _, _, _, star_y = self.assets.get_layout(tile.prop_texture)

                        # NEW: Stars are handled in a separate pass to ensure they sit on top of massive castles
                        castle_layer.append(
                            {
                                "depth": cdyp,
                                "type": "castle_star",
                                "x": cdxp,
                                "y": cdyp,
                                "star_y": star_y,
                            }
                        )

        # Add Ground Items
        for item in world.ground_items:
            # We add q, r to the item object for rendering by converting the tile id to q, r
            tile = world.get_tile(item.q, item.r)

            if not tile or not tile.discovered:
                continue

            iqx, iqy = HexMath.hex_to_pixel(item.q, item.r)
            idx = cx + (iqx - ppx)
            idy = cy + (iqy - ppy)

            # Culling (don't draw if off screen)
            if (
                -100 < idx < Config.WINDOW_WIDTH + 100
                and -100 < idy < Config.WINDOW_HEIGHT + 100
            ):
                object_layer.append(
                    {"depth": idy, "type": "item", "item": item, "x": idx, "y": idy}
                )

        # Draw Terrain (Sorted by Y for slight depth effect if needed, but mostly Z-order matters)
        terrain_layer.sort(key=lambda t: t[2])
        for tile, dx, dy in terrain_layer:
            self._draw_hex_base(screen, tile, dx, dy)

            # clouds that cover locked levels
            if world.is_tile_locked(tile.q, tile.r):
                if tile.discovered:
                    continue  # if already discovered, don't draw clouds

                # cloud couverage
                if (tile.q * 5 + tile.r * 7) % 200 != 0:
                    # cloud selection (images in the list)
                    idx = abs(tile.q * 31 + tile.r * 17) % len(self.cloud_images)
                    img = self.cloud_images[idx]

                    self._draw_cloud_overlay(screen, img, dx, dy, scale=2.3)

        # Draw Objects (Sorted by Depth Y)
        object_layer.sort(key=lambda obj: obj["depth"])

        for obj in object_layer:
            if obj["type"] == "prop":
                self._draw_prop(screen, obj["tile"], obj["x"], obj["y"])
            elif obj["type"] == "entity":
                self._draw_entity(
                    screen, obj["entity"], obj["x"], obj["y"], frame_index
                )
            elif obj["type"] == "item":
                self._draw_item(screen, obj["item"], obj["x"], obj["y"], frame_index)
            elif obj["type"] == "chest":
                self._draw_chest(screen, obj["chest"], obj["x"], obj["y"])

        # Drawin castles sorted by depth Y ensuring they render over props etc while respecting their own relative depth
        castle_layer.sort(key=lambda obj: obj["depth"])
        for obj in castle_layer:
            if obj["type"] == "prop":
                self._draw_prop(screen, obj["tile"], obj["x"], obj["y"])
            elif obj["type"] == "castle_star":
                # Render star on top of the castle center
                self._draw_castle_star(
                    screen,
                    obj["x"],
                    obj["y"],
                    frame_index,
                    star_y_offset=obj.get("star_y", 50),
                )

        if hasattr(world, "effects"):
            for effect in world.effects:
                edx, edy = 0, 0

                if effect.__class__.__name__ == "HealEffect":
                    target = effect.target

                    # Smoothly follow the target if they are currently moving between tiles
                    if getattr(target, "is_moving", False):
                        from_px, from_py = HexMath.hex_to_pixel(target.move_from_q, target.move_from_r)
                        to_px, to_py = HexMath.hex_to_pixel(target.move_to_q, target.move_to_r)
                        t = target.move_progress
                        eqx = from_px + (to_px - from_px) * t
                        eqy = from_py + (to_py - from_py) * t
                    else:
                        eqx, eqy = HexMath.hex_to_pixel(target.q, target.r)
                        
                    # Apply camera offset to get final screen position
                    edx = cx + (eqx - ppx)
                    edy = cy + (eqy - ppy)
                
                    # Fetch the raw sprite sheet from assets
                    sheet = self.assets.get_image("Heal_Effect.png", scale_to_tile=False) 
                    
                    if sheet:
                        fw = 192
                        fh = 180

                        current_frame = (effect.anim_tick // effect.anim_speed) % effect.frame_count
                        crop_rect = (current_frame * fw, 0, fw, fh)
                        try:
                            frame = sheet.subsurface(crop_rect)
                            display_w = 96 
                            display_h = 90
                            frame = pygame.transform.smoothscale(frame, (display_w, display_h))
                            
                            rect = frame.get_rect(centerx=edx, centery=edy + 60 - Config.CALIB_OFFSET_Y)
                            screen.blit(frame, rect)
                        except ValueError:
                            pass
                    
                        continue
            
                # Convert hex coordinates to pixel coordinates
                eqx, eqy = HexMath.hex_to_pixel(effect.q, effect.r)

                # Apply camera offset to keep VFX fixed on the map
                edx = cx + (eqx - ppx)
                edy = cy + (eqy - ppy)

                if (
                    -200 < edx < Config.WINDOW_WIDTH + 200
                    and -200 < edy < Config.WINDOW_HEIGHT + 200
                ):
                    # Calculate alpha for fade-out effect (160 -> 0)
                    progress = effect.current_radius / effect.max_pixel_radius
                    alpha = int(160 * (1.0 - progress))
                    alpha = max(0, min(255, alpha))

                    if alpha <= 0:
                        continue

                    # Create a temporary surface with per-pixel alpha
                    surf_size = int(effect.max_pixel_radius * 2)
                    if surf_size <= 0:
                        continue

                    temp_surf = pygame.Surface((surf_size, surf_size), pygame.SRCALPHA)
                    center = (surf_size // 2, surf_size // 2)

                    # Draw the circle with color and alpha
                    pygame.draw.circle(
                        temp_surf,
                        (*effect.color, alpha),
                        center,
                        int(effect.current_radius),
                    )

                    # Blit onto the main screen
                    rect = temp_surf.get_rect(
                        centerx=edx, centery=edy - Config.CALIB_OFFSET_Y
                    )
                    screen.blit(temp_surf, rect)

    def _draw_hex_base(self, screen, tile, x, y):
        # HexMath returns list of floats, Pygame needs list of tuples
        poly_floats = HexMath.get_hex_polygon(x, y)
        # Convert flat list [x1, y1, x2, y2...] to [(x1,y1), (x2,y2)...]
        poly_points = list(zip(poly_floats[0::2], poly_floats[1::2]))

        if not tile.discovered:
            pygame.draw.polygon(screen, (0, 0, 0), poly_points)
            return

        fill = self.COLOR_GRASS
        if tile.type == "water":
            fill = self.COLOR_WATER
        elif tile.type == "stone":
            fill = self.COLOR_STONE

        pygame.draw.polygon(screen, fill, poly_points)
        pygame.draw.polygon(screen, self.COLOR_OUTLINE, poly_points, 1)

        if tile.texture:
            scale, x_shift, y_shift, _ = self.assets.get_layout(tile.texture)
            img = self.assets.get_image(tile.texture, scale=scale)
            if img:
                # Center horizontally, shift vertically or horizontally
                rect = img.get_rect(
                    centerx=x + x_shift, centery=y - Config.CALIB_OFFSET_Y - y_shift
                )
                screen.blit(img, rect)

    def _draw_prop(self, screen, tile, x, y):
        if tile.prop_texture:
            img = self.assets.get_image(tile.prop_texture, scale=tile.prop_scale)
            if img:
                rect = img.get_rect(
                    centerx=x + tile.prop_x_shift,
                    centery=y - Config.CALIB_OFFSET_Y - tile.prop_shift,
                )
                screen.blit(img, rect)

    def _draw_entity(self, screen, entity, x, y, frame_index):
        if entity.texture:
            # monsters can use their own animation tick for attack
            if hasattr(entity, "anim_state") and hasattr(entity, "anim_tick"):
                # Now match with archer_...
                if entity.anim_state.endswith(
                    ("attack", "hit", "die", "move", "stun", "charge")
                ):
                    use_frame = entity.anim_tick
                else:
                    use_frame = frame_index
            else:
                use_frame = frame_index

            base_img = self.assets.get_anim_frame(entity.texture, use_frame)
            if not base_img:
                return

            flash_color = None

            # first check poison state
            if getattr(entity, "poison_flash_timer", 0) > 0:
                flash_color = (180, 50, 255)
            # add red flash effect to both player and monster
            elif getattr(entity, "damage_flash_timer", 0) > 0:
                flash_color = (255, 50, 50)
            elif getattr(entity, "heal_flash_timer", 0) > 0:
                flash_color = (50, 255, 50)

            if hasattr(entity, "anim_state") and hasattr(entity, "anim_tick"):
                if entity.anim_state.endswith("die") and entity.anim_tick < 4:
                    flash_color = (255, 50, 50)

            # Change the texture direction with player and monsters direction
            is_flipped = getattr(entity, "flip_x", False)

            # If the monster has the "invert_flip" label, reverse the flipped state
            if getattr(entity, "invert_flip", False):
                is_flipped = not is_flipped

            # special scale mark for small stone monster
            mini_override = getattr(entity, "mini_scale_override", 1.0)

            cache_key = (id(base_img), flash_color, is_flipped, mini_override)

            # First look in cache, if not found, generate new one and cache it
            if cache_key in self.image_cache:
                img = self.image_cache[cache_key]
            else:
                img = base_img

                if flash_color is not None:
                    flash_img = img.copy()  # make a copy of origin img
                    flash_img.fill(flash_color, special_flags=pygame.BLEND_RGB_MULT)
                    img = flash_img

                if is_flipped:
                    img = pygame.transform.flip(img, True, False)

                # Get the size after scaling
                if mini_override != 1.0:
                    new_w = int(img.get_width() * mini_override)
                    new_h = int(img.get_height() * mini_override)
                    img = pygame.transform.smoothscale(img, (new_w, new_h))

                # cache it
                self.image_cache[cache_key] = img

            scale, x_shift, y_shift, _ = self.assets.get_layout(entity.texture)
            override_y = getattr(entity, "y_shift_override", None)

            final_y_shift = override_y if override_y is not None else y_shift

            rect = img.get_rect(
                centerx=x + x_shift, centery=y - Config.CALIB_OFFSET_Y - final_y_shift
            )
            screen.blit(img, rect)

            if hasattr(entity, "hp") and hasattr(entity, "max_hp"):
                if entity.hp < entity.max_hp and entity.hp > 0:
                    max_hp = max(1, entity.max_hp)
                    ratio = max(0.0, min(1.0, entity.hp / max_hp))

                    bar_w = 40
                    bar_h = 6

                    bar_x = x - (bar_w // 2)
                    bar_y = y - Config.CALIB_OFFSET_Y

                    if ratio > 0.5:
                        fill_color = (50, 205, 50)  # green
                    elif ratio > 0.2:
                        fill_color = (255, 215, 0)  # yellow
                    else:
                        fill_color = (220, 20, 60)  # red

                    pygame.draw.rect(screen, (40, 40, 40), (bar_x, bar_y, bar_w, bar_h))
                    fill_w = int(bar_w * ratio)
                    if fill_w > 0:
                        pygame.draw.rect(
                            screen, fill_color, (bar_x, bar_y, fill_w, bar_h)
                        )
                    pygame.draw.rect(
                        screen, (20, 20, 20), (bar_x, bar_y, bar_w, bar_h), 1
                    )
        else:
            pygame.draw.circle(screen, (255, 0, 0), (int(x), int(y)), 10)

    def _draw_chest(self, screen, chest, x, y):
        if not chest.texture:
            return
        img = self.assets.get_anim_frame(
            chest.texture, chest.anim_tick, row=chest.anim_row
        )
        if not img:
            return
        scale, x_shift, y_shift, _ = self.assets.get_layout(chest.texture)
        rect = img.get_rect(
            centerx=x + x_shift,
            centery=y - Config.CALIB_OFFSET_Y - y_shift,
        )
        screen.blit(img, rect)

    def _draw_item(self, screen, item, x, y, frame_index):
        if not item.texture:
            return

        img = self.assets.get_anim_frame(item.texture, frame_index)
        scale, x_shift, y_shift, _ = self.assets.get_layout(item.texture)

        if img:
            rect = img.get_rect(
                centerx=x + x_shift, centery=y - Config.CALIB_OFFSET_Y - y_shift
            )
            screen.blit(img, rect)

    def _draw_castle_star(self, screen, x, y, frame_index, star_y_offset=50):
        # We use scale_to_tile=False to get the raw high-res asset
        img_sheet = self.assets.get_image("star.png", scale_to_tile=False)

        if img_sheet:
            width = img_sheet.get_width()
            height = img_sheet.get_height()

            # Since there are 13 frames side-by-side
            count = 13
            fw = width // count
            fh = height

            # Slow down the animation works by skipping every 4 frames
            anim_slowdown = 4
            safe_idx = (frame_index // anim_slowdown) % count

            try:
                # Extract correct frame
                crop = (safe_idx * fw, 0, fw, fh)
                frame_surf = img_sheet.subsurface(crop)

                target_size = 48
                star_scale = target_size / fw

                sw, sh = frame_surf.get_size()
                frame_surf = pygame.transform.smoothscale(
                    frame_surf, (int(sw * star_scale), int(sh * star_scale))
                )

                # Draw the specific frame, offset upwards to sit on the castle
                rect = frame_surf.get_rect(
                    centerx=x, centery=y - Config.CALIB_OFFSET_Y - star_y_offset
                )
                screen.blit(frame_surf, rect)
                return
            except (ValueError, pygame.error):
                return

    def _draw_cloud_overlay(self, screen, img, x, y, scale=1.3):

        width = int(img.get_width() * scale * 1.15)  # slightly wider
        height = int(img.get_height() * scale * 0.9)  # slightly shorter
        cloud = pygame.transform.smoothscale(img, (width, height))
        cloud.set_alpha(210)  # soft fog
        rect = cloud.get_rect(center=(x, y - Config.CALIB_OFFSET_Y))
        screen.blit(cloud, rect)
