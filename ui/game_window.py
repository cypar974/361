import pygame
from core.config import Config
from core.hexmath import HexMath
from database.db_manager import DatabaseManager
from gameplay.engine import GameEngine
from visuals.asset_manager import AssetManager
from visuals.renderer import GameRenderer
from ui.button import Button
from ui.base_screen import Screen
import random
import os


class GameWindow(Screen):
    def __init__(self, manager, slot_id=1, selected_skin=None):
        super().__init__(manager)

        slot_id = manager.selected_slot or 1
        selected_skin = manager.selected_skin

        pygame.display.set_caption(f"Hex RPG - Slot {slot_id}")
      

        db_file = f"game_data_{slot_id}.db"
        self.db = DatabaseManager(db_file)
        # Ensure session exists (auto-create slot 1)
        if not self.db.get_session(1):
            char_type = getattr(manager, "selected_character", "warrior")
            sid = self.db.create_session(1, char_type=char_type)
            
            # Add and equip starting weapon
            weapon_name = "basic_bow" if char_type == "archer" else "basic_sword"
            weapon_id = self.db.get_or_create_item(weapon_name)
            if weapon_id:
                self.db.add_item(sid, weapon_id, quantity=1)
                self.db.toggle_equip(sid, weapon_id)

            if char_type == "archer":
                # Give the archer some starting arrows
                arrow_id = self.db.get_or_create_item("arrow")
                self.db.add_item(sid, arrow_id, quantity=99)

        if selected_skin:
            self.db.cursor.execute("UPDATE player_state SET texture_file=? WHERE session_id=1", (selected_skin,))
            self.db.conn.commit()

        self.engine = GameEngine(self.db, 1)
        
        self.engine.world.player.load_inventory(self.db, 1)

        # Demo: spawn a visible chest next to the player only if it's a fresh game
        # (check if inventory only has the starting weapon or less)
        if not self.engine.world.chests and len(self.engine.world.player.inventory) <= 1:
            self.engine.world.spawn_chest()
        self.assets = AssetManager()
        self.renderer = GameRenderer(self.assets)

        self.font = pygame.font.SysFont("Arial", 18)
        self.loot_font = pygame.font.SysFont("Arial", 22, bold=True)
        self.frame_index = 0
        self.anim_timer = 0
        self.inventory_scroll_offset = 0 # tracks how far the inventory list is scrolled
        self.inventory_last_selected_index = self.engine.selected_index
        self.last_click_time = 0 # timestamp of the previous click to detect double-clicks
        self.last_clicked_index = -1 # index of the item previously clicked

        self.active_loot_notification = None
        self.loot_notification_duration_ms = 1000  # 1 second fade

    

    def handle_event(self, event):
        if event.type == pygame.QUIT:
            self.manager.running = False
            # Key Presses (Single Action)
        if event.type == pygame.MOUSEWHEEL and getattr(
            self.engine, "show_inventory", False
        ):
            # Scroll inventory list up/down
            self.inventory_scroll_offset -= event.y
            return

        # Handling clicking on inventory items
        if event.type == pygame.MOUSEBUTTONDOWN and getattr(
            self.engine, "show_inventory", False
        ):
            if event.button == 1:  # Left click
                # Re-calculate the list panel dimensions to find if the click is inside the item list area.
                # These variables must match the layout logic in _draw_inventory so change both if needed
                panel_x, panel_y = 200, 80
                panel_w = Config.WINDOW_WIDTH - 400
                panel_h = Config.WINDOW_HEIGHT - 160
                
                body_top = panel_y + 116
                body_height = panel_h - 140
                left_width = int(panel_w * 0.62)
                list_rect = pygame.Rect(panel_x + 18, body_top, left_width, body_height)

                # Only proceed if the user clicked inside the item list region
                if list_rect.collidepoint(event.pos):
                    # 'top' is the starting Y-coordinate of the first item in the list (including padding)
                    top = list_rect.y + 42
                    row_height = 52
                    row_gap = 8
                    
                    mouse_y = event.pos[1]
                    relative_y = mouse_y - top
                    
                    # Ensure the click isn't in the header area of the list
                    if relative_y >= 0:
                        # Convert vertical pixel distance to a row index
                        clicked_row = relative_y // (row_height + row_gap)

                        # Offset the row by the current scroll position to get the actual item index
                        clicked_index = self.inventory_scroll_offset + clicked_row
                        
                        items = self.engine.world.player.inventory
                        if 0 <= clicked_index < len(items):
                            # Double-Click Detection:
                            # If the same item was clicked twice within 500ms, trigger the "INTERACT" action.
                            now = pygame.time.get_ticks()
                            if (clicked_index == self.last_clicked_index and 
                                now - self.last_click_time < 500):
                                self.engine.selected_index = clicked_index
                                self.engine.run_turn("INTERACT") # Executes 'Use' or 'Equip/Unequip'
                                self.last_click_time = 0 # Reset timer to prevent triple-click triggering twice
                            else:
                                # First click: simply select and highlight the item
                                self.engine.selected_index = clicked_index
                                self.last_click_time = now
                                self.last_clicked_index = clicked_index
                            # Stop event propagation for this click
                            return

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                if getattr(self.engine, "show_inventory", False):
                    self.engine.run_turn("INVENTORY")
                else:
                    self.manager.switch_screen("main_menu")

            # Open/Close Inventory should strictly be a single key press
            elif event.key == pygame.K_i or event.key == pygame.K_TAB:
                action = "INVENTORY"
                self.engine.run_turn(action)

            # Let the inventory still read from the input key
            elif getattr(self.engine, "show_inventory", False):
                action = None

                if event.key == pygame.K_w:
                    action = "MOVE_NORTH"       
                elif event.key == pygame.K_s:
                    action = "MOVE_SOUTH"       
                elif event.key == pygame.K_a:
                    action = "MOVE_SW"        
                elif event.key == pygame.K_f or event.key == pygame.K_SPACE:
                    action = "INTERACT"         

                if action:
                    self.engine.run_turn(action)

    def cleanup(self):
        if hasattr(self, "db") and self.db:
            self.db.close()

    def _update_and_cleanup_entities(self, entities, removal_attr, on_death_finish=None):
        for entity in entities:
            entity.update_animation(self.assets)
            
            if on_death_finish and getattr(entity, "death_finished", False):
                on_death_finish(entity)
        
        # Remove entities that meet the removal condition
        entities[:] = [e for e in entities if not getattr(e, removal_attr, False)]
                    
    def update(self):
        # Loot notifications: per-frame (not tied to 50ms anim tick) so fade is smooth
        self._update_loot_notifications(self.manager.clock.get_time())

        # Animation tick
        self.anim_timer += self.manager.clock.get_time()
        if self.anim_timer > 50:
            self.anim_timer = 0
            self.frame_index += 1

            # player animation
            player = self.engine.world.player
            if player:
                player.update_animation(self.assets)

            # Update monsters, assistants, and chests
            self._update_and_cleanup_entities(
                self.engine.world.monsters, 
                "remove_after_death", 
                on_death_finish=self.engine.drop_monster_loot
            )

            self._update_and_cleanup_entities(
                self.engine.world.assistants, 
                "remove_after_death"
            )

            self._update_and_cleanup_entities(
                self.engine.world.chests, 
                "remove_after_open"
            )

            if hasattr(self.engine.world, "update_vfx"):
                self.engine.world.update_vfx()

        # Implement real-time ARPG 
        player = self.engine.world.player
        if not player:
            return
        
        is_player_animating = getattr(player, "is_moving", False) or getattr(player, "is_attacking", False)
        is_inventory_open = getattr(self.engine, "show_inventory", False)

        # Only process game actions if the inventory is closed
        if not is_inventory_open:

            # Only accept new commands if the player has finished their current action
            if not is_player_animating:
                keys = pygame.key.get_pressed()
                action = None
            
                if keys[pygame.K_w]: action = "MOVE_NORTH"
                elif keys[pygame.K_s]: action = "MOVE_SOUTH"
                elif keys[pygame.K_a]: action = "MOVE_SW"
                elif keys[pygame.K_d]: action = "MOVE_EAST"
                elif keys[pygame.K_q]: action = "MOVE_WEST"
                elif keys[pygame.K_e]: action = "MOVE_NE"
                elif keys[pygame.K_f] or keys[pygame.K_SPACE]: action = "INTERACT"

                if action:
                    if action in ("MOVE_WEST", "MOVE_SW"): # q, a
                        player.flip_x = True
                    elif action in ("MOVE_EAST", "MOVE_NE"): # e, d
                        player.flip_x = False
                    
                    result = self.engine.run_turn(action)

                    if result == "WIN":
                        slot = self.manager.selected_slot
                        filename = f"game_data_{slot}.db"
                        # close the db properly 
                        if hasattr(self, "db") and self.db:
                            self.db.close()
                        
                        # making sure windows releases the db file so it doesnt crash
                        import time
                        time.sleep(1)

                        # force delete the file
                        if os.path.exists(filename):
                            try:
                                os.remove(filename)
                            except Exception as e:
                                print(f"deletion failed: {e}")
                        self.manager.switch_screen("winner")
                        return
                    elif result == "GAME_OVER":
                        
                        slot = self.manager.selected_slot
                        filename = f"game_data_{slot}.db"
                        # close the db properly 
                        if hasattr(self, "db") and self.db:
                            self.db.close()
                        
                        # making sure windows releases the db file so it doesnt crash
                        import time
                        time.sleep(1)

                        # force delete the file
                        if os.path.exists(filename):
                            try:
                                os.remove(filename)
                            except Exception as e:
                                print(f"deletion failed: {e}")
                        self.manager.selected_slot = None
                        self.manager.switch_screen("game_over")
                        
                        return

            # Independent Monster AI Handling
            for monster in self.engine.world.monsters:
                if not monster.is_alive():
                    continue

                is_monster_animating = getattr(monster, "is_moving", False) or monster.anim_state in ("move", "attack", "hit")
                if is_monster_animating:
                    continue

                # Initialize real-time action timer 
                if not hasattr(monster, "rt_action_timer"):
                    monster.rt_action_timer = random.randint(30, 40) 
                
                monster.rt_action_timer -= 1

                # Trigger monster AI decision if timer reaches zero
                if monster.rt_action_timer <= 0:

                    monster.decide_and_act(self.engine.world, player)
                    monster.rt_action_timer = random.randint(30, 40)
            
            # Independent Assistant AI Handling
            for assistant in getattr(self.engine.world, "assistants", []):
                if not assistant.is_alive():
                    continue

                # Skip if the assistant is currently performing an action
                is_busy = getattr(assistant, "is_moving", False) or assistant.anim_state in ("move", "attack", "hit")
                if is_busy:
                    continue

                # Initialize or decrement the real-time action timer
                if not hasattr(assistant, "rt_action_timer"):
                    # Slightly different interval than monsters to prevent synchronized movement
                    assistant.rt_action_timer = random.randint(25, 35) 
                
                assistant.rt_action_timer -= 1

                # Execute AI decision-making when timer hits zero
                if assistant.rt_action_timer <= 0:
                    # Assistant AI logic: Follow player or attack nearby monsters
                    assistant.decide_and_act(self.engine.world, player)
                    
                    # Reset timer for the next action cycle
                    assistant.rt_action_timer = random.randint(25, 35)

    def _update_loot_notifications(self, dt_ms):
        # Pop next notification if slot is free
        if self.active_loot_notification is None:
            if self.engine.loot_notifications_queue:
                name, count = self.engine.loot_notifications_queue.pop(0)
                self.active_loot_notification = {
                    "text": f"{name} x{count}",
                    "age_ms": 0,
                }
            return

        self.active_loot_notification["age_ms"] += dt_ms
        if self.active_loot_notification["age_ms"] >= self.loot_notification_duration_ms:
            self.active_loot_notification = None

    def _draw_loot_notification(self):
        """Draw the active floating loot text above the player with a fade."""
        notif = self.active_loot_notification
        if notif is None:
            return

        # Linear fade out across the full duration
        progress = notif["age_ms"] / self.loot_notification_duration_ms
        progress = max(0.0, min(1.0, progress))
        alpha = int(255 * (1.0 - progress))
        # Rise a little as it fades (10px over the full duration)
        y_offset = int(progress * 10)

        text_surf = self.loot_font.render(
            notif["text"], True, (255, 236, 140)
        )
        faded = pygame.Surface(text_surf.get_size(), pygame.SRCALPHA)
        faded.blit(text_surf, (0, 0))
        faded.set_alpha(alpha)

        # Center horizontally, anchor above the player's HUD position.
        # Player is always drawn at screen center.
        cx = self.manager.screen.get_width() // 2
        cy = self.manager.screen.get_height() // 2
        rect = faded.get_rect(center=(cx, cy - 80 - y_offset))
        self.manager.screen.blit(faded, rect)

    def draw(self):
        self.update()
        # Render World
        self.renderer.render(self.manager.screen, self.engine.world, self.frame_index)

        # Render UI Overlay
        self._draw_ui()

        # Loot pickup text (drawn after world, before inventory overlay)
        self._draw_loot_notification()

        # inventory
        if self.engine.show_inventory:
            self._draw_inventory()

    def _draw_panel_box(self, rect, fill, border, border_width=2):
        pygame.draw.rect(self.manager.screen, fill, rect, border_radius=10)
        pygame.draw.rect(
            self.manager.screen,
            border,
            rect,
            border_width,
            border_radius=10,
        )

    # Top part of inventory page
    def _draw_inventory_header(self, panel_rect, player):
        # Create two font size for this part
        title_font = pygame.font.SysFont("Arial", 28, bold=True)
        small_font = pygame.font.SysFont("Arial", 16)

        # Dispaly title, control instruction and player info
        title = title_font.render("Inventory", True, (236, 228, 204))
        controls = small_font.render(
            "1 left click: to select   2 left clicks/F: to Equip/Unequip   Wheel: Scroll   I/ESC: Close",
            True,
            (162, 169, 178),
        )
        summary = self.font.render(
            f"ATK: {player.total_damage}   DEF: {player.total_defense}",
            True,
            (162, 204, 198),
        )

        # Place them on the screen
        self.manager.screen.blit(title, (panel_rect.x + 24, panel_rect.y + 18))
        self.manager.screen.blit(controls, (panel_rect.x + 24, panel_rect.y + 52))
        self.manager.screen.blit(summary, (panel_rect.x + 24, panel_rect.y + 80))

    # Left side of inventory page, list all items in inventory and show which one is selected
    def _draw_inventory_list(self, rect, items):
        self._draw_panel_box(rect, (31, 34, 40), (84, 90, 98))

        list_title = self.font.render("Items", True, (210, 214, 220))
        self.manager.screen.blit(list_title, (rect.x + 16, rect.y + 12))

        # Empty state
        if not items:
            self.inventory_scroll_offset = 0
            self.inventory_last_selected_index = self.engine.selected_index
            empty = self.font.render("Your inventory is empty.", True, (145, 150, 158))
            hint = self.font.render("Pick up items to see them here.", True, (105, 112, 121))
            self.manager.screen.blit(empty, (rect.x + 16, rect.y + 52))
            self.manager.screen.blit(hint, (rect.x + 16, rect.y + 78))
            return

        row_height = 52
        row_gap = 8
        top = rect.y + 42
        bottom = rect.bottom - 12
        visible_count = max(1, (bottom - top + row_gap) // (row_height + row_gap))
        max_scroll_offset = max(0, len(items) - visible_count)
        selected_index = min(self.engine.selected_index, len(items) - 1)

        self.inventory_scroll_offset = max(
            0,
            min(self.inventory_scroll_offset, max_scroll_offset),
        )

        # If the selected index has changed, adjust scroll offset to ensure it's visible
        if selected_index != self.inventory_last_selected_index:
            if selected_index < self.inventory_scroll_offset:
                self.inventory_scroll_offset = selected_index
            elif selected_index >= self.inventory_scroll_offset + visible_count:
                self.inventory_scroll_offset = selected_index - visible_count + 1
            self.inventory_last_selected_index = selected_index

        self.inventory_scroll_offset = max(
            0,
            min(self.inventory_scroll_offset, max_scroll_offset),
        )

        if len(items) > visible_count:
            # Show scroll range indicator
            end_item = min(len(items), self.inventory_scroll_offset + visible_count)
            range_text = self.font.render(
                f"{end_item} / {len(items)}",
                True,
                (145, 150, 158),
            )
            self.manager.screen.blit(
                range_text,
                (rect.right - range_text.get_width() - 16, rect.y + 12),
            )

        visible_items = items[
            self.inventory_scroll_offset:self.inventory_scroll_offset + visible_count
        ]
        for display_index, item in enumerate(visible_items):
            # If the row goes beyond the bottom of the panel, stop drawing more items
            row_y = top + display_index * (row_height + row_gap)
            if row_y + row_height > bottom:
                break

            # Engine stores selected_index which is used to determine which item is highlighted
            item_index = self.inventory_scroll_offset + display_index
            row_rect = pygame.Rect(rect.x + 12, row_y, rect.width - 24, row_height)
            selected = item_index == self.engine.selected_index
            row_fill = (92, 69, 41) if selected else (42, 46, 53)
            row_border = (230, 196, 120) if selected else (74, 80, 89)
            name_color = (255, 241, 197) if selected else (225, 228, 232)
            meta_color = (244, 214, 147) if selected else (152, 159, 168)

            self._draw_panel_box(row_rect, row_fill, row_border)

            # Draw item icon or placeholder
            icon_size = 40
            icon_x = row_rect.x + 8
            icon_y = row_rect.y + (row_height - icon_size) // 2
            icon_rect = pygame.Rect(icon_x, icon_y, icon_size, icon_size)

            item_icon = None
            if item.texture:
                # Scale calculation because get_image uses Config.HEX_SIZE
                raw_icon = self.assets.get_image(item.texture, scale=1.0) # get base scale
                if raw_icon:
                    # Resize to fit the inventory row exactly
                    item_icon = pygame.transform.scale(raw_icon, (icon_size, icon_size))
            
            if item_icon:
                self.manager.screen.blit(item_icon, icon_rect)
            else:
                # Placeholder: A simple rounded box for items with no texture
                placeholder_color = (60, 65, 75)
                pygame.draw.rect(self.manager.screen, placeholder_color, icon_rect, border_radius=6)
                pygame.draw.rect(self.manager.screen, row_border, icon_rect, 1, border_radius=6)
                
                letter = item.name[0].upper()

                # Draw the letter in the center of the icon
                letter_surf = self.font.render(letter, True, (100, 105, 115))
                letter_rect = letter_surf.get_rect(center=icon_rect.center)
                self.manager.screen.blit(letter_surf, letter_rect)

            # Display item name, quantity, type, slot and equipped status
            # Offset text to the right of the icon
            text_x_offset = 60
            
            # Hide quantity for equipment or for single items
            show_quantity = item.quantity > 1 and not item.is_equippable
            qty_text = f" x{item.quantity}" if show_quantity else ""
            
            name = self.font.render(f"{item.name}{qty_text}", True, name_color)
            meta_bits = [item.type.title()]
            if item.is_equippable and item.slot:
                meta_bits.append(item.slot.title())
            if item.equipped:
                meta_bits.append("Equipped")
            meta = self.font.render("  |  ".join(meta_bits), True, meta_color)

            self.manager.screen.blit(name, (row_rect.x + text_x_offset, row_rect.y + 10))
            self.manager.screen.blit(meta, (row_rect.x + text_x_offset, row_rect.y + 28))

    # Right top of inventory page
    def _draw_equipment_summary(self, rect, player):
        self._draw_panel_box(rect, (31, 34, 40), (84, 90, 98))

        title = self.font.render("Equipped", True, (210, 214, 220))
        self.manager.screen.blit(title, (rect.x + 16, rect.y + 12))

        # Define display labels for each equipment slot
        slot_labels = {
            "weapon": "Weapon",
            "armor": "Armor",
        }

        line_y = rect.y + 46
        # Loop through each equipment slot and display the equipped item or "--" if empty
        for slot_name in ("weapon", "armor"):
            equipped = player.equipment.get(slot_name)
            
            label = "--"
            color = (120, 127, 135)
            
            if equipped:
                label = equipped.name
                color = (186, 220, 198)
            elif slot_name == "weapon":
                label = "(No Weapon Equipped)"
                color = (255, 120, 120) # Red warning
            
            slot_surf = self.font.render(
                f"{slot_labels[slot_name]}: {label}",
                True,
                color,
            )
            self.manager.screen.blit(slot_surf, (rect.x + 16, line_y))
            line_y += 28

    # Right bottom of inventory page
    def _selected_item_detail_lines(self, item):
        if not item:
            return [("Select an item to inspect its details.", (145, 150, 158), None)]

        lines = []
        if item.description:
            lines.append((item.description, (182, 188, 196), None))
        if item.damage_bonus > 1:
            lines.append((f"Damage +{item.damage_bonus}", (169, 214, 205), None))
        if item.defense > 1:
            lines.append((f"Defense +{item.defense}", (169, 214, 205), None))
        if item.max_durability > 1:
            lines.append(
                (
                    f"Durability {item.durability}/{item.max_durability}",
                    (169, 214, 205),
                    None
                )
            )
        if item.type == "food":
            if item.healing_amount > 0:
                lines.append((f"{item.healing_amount}", (169, 214, 205), "Heart.png"))
            if item.hunger_restore > 0:
                lines.append((f"{item.hunger_restore}", (169, 214, 205), "Food_Restaurant_Eating_Utensils_Plate_Fork_Knife.png"))
        if item.weight > 1:
            lines.append((f"Weight {item.weight}", (169, 214, 205), None))
        if not lines:
            lines.append(("No additional details.", (145, 150, 158), None))
        return lines

    def _wrap_text(self, text, font, limit):
        # word-wrapping function that splits text into lines that fit within limit
        if not text: 
            return [""]
        
        result = []
        words = text.split(' ')
        line = ""
        
        for word in words:
            if font.size(word)[0] > limit:
                if line:
                    result.append(line)
                    line = ""
                
                frag = ""
                for char in word:
                    if font.size(frag + char)[0] <= limit:
                        frag += char
                    else:
                        result.append(frag)
                        frag = char
                line = frag
                continue

            # append and check if it fits
            test = line + (" " if line else "") + word
            if font.size(test)[0] <= limit:
                line = test
            else:
                result.append(line)
                line = word
                
        if line: 
            result.append(line)
        return result

    # Right bottom of inventory page
    def _draw_selected_item_details(self, rect, item):
        self._draw_panel_box(rect, (31, 34, 40), (84, 90, 98))

        title = self.font.render("Details", True, (210, 214, 220))
        self.manager.screen.blit(title, (rect.x + 16, rect.y + 12))

        # If an item is selected, display its name, type and details. Otherwise show a hint to select an item
        if item:
            name = self.font.render(item.name, True, (236, 228, 204))
            item_type = self.font.render(item.type.title(), True, (244, 214, 147))
            self.manager.screen.blit(name, (rect.x + 16, rect.y + 44))
            self.manager.screen.blit(item_type, (rect.x + 16, rect.y + 68))
            line_y = rect.y + 102
        else:
            line_y = rect.y + 46

        max_text_width = rect.width - 32
        bottom_padding = 16
        line_height = 24
        icon_size = 20
        
        for line, color, icon_file in self._selected_item_detail_lines(item):
            # If there's an icon we need to offset the text and draw the icon
            icon_img = None
            text_x = rect.x + 16
            
            if icon_file:
                # Load and scale icon
                raw_img = self.assets.get_image(icon_file, scale=1.0)
                if raw_img:
                    icon_img = pygame.transform.scale(raw_img, (icon_size, icon_size))
                    text_x += icon_size + 6

            for wrapped_line in self._wrap_text(line, self.font, max_text_width - (icon_size + 6 if icon_img else 0)):
                # If the next line would go beyond the bottom of the panel, stop drawing more lines
                if line_y + line_height > rect.bottom - bottom_padding:
                    return
                
                # Draw icon on the first line of the wrapped text if applicable
                if icon_img:
                    icon_y = line_y + (line_height - icon_size) // 2
                    self.manager.screen.blit(icon_img, (rect.x + 16, icon_y))
                    icon_img = None # Only draw icon once per logical line
                
                surf = self.font.render(wrapped_line, True, color)
                self.manager.screen.blit(surf, (text_x, line_y))
                line_y += line_height


    def _draw_ui(self):
        p = self.engine.world.player
        if not p:
            return

        # Simple Stat Bar
        pygame.draw.rect(self.manager.screen, (30, 30, 30), (0, 0, Config.WINDOW_WIDTH, 40))

        hp_text = self.font.render(f"HP: {p.hp}/{p.max_hp}", True, (255, 80, 80))
        hunger_text = self.font.render(
            f"Hunger: {p.hunger}/{p.max_hunger}", True, (255, 160, 50)
        )
        dmg_text = self.font.render(f"ATK: {p.total_damage}", True, (255, 200, 100))
        # Add unarmed warning to HUD if no weapon
        unarmed_warning = None
        if not p.equipment.get("weapon"):
            unarmed_warning = self.font.render("(Unarmed!)", True, (255, 100, 100))

        def_text = self.font.render(f"DEF: {p.total_defense}", True, (100, 200, 255))
        loc_text = self.font.render(f"Q:{p.q} R:{p.r}", True, (200, 200, 200))

        self.manager.screen.blit(hp_text, (20, 10))
        self.manager.screen.blit(hunger_text, (150, 10))
        self.manager.screen.blit(dmg_text, (320, 10))
        if unarmed_warning:
            self.manager.screen.blit(unarmed_warning, (550 + dmg_text.get_width() + 5, 10))
        self.manager.screen.blit(def_text, (420, 10))
        self.manager.screen.blit(loc_text, (Config.WINDOW_WIDTH - 100, 10))

        #Draw Hearts
        self.draw_hearts(3, getattr(p, "hearts", 0), Config.WINDOW_WIDTH - 200, 17)

        #Adding level box 
        level = self.engine.world.current_level

        # Colors
        bg_color = (20, 20, 30)
        border_color = (212, 175, 55)   # gold
        text_color = (255, 236, 140)

        # Box
        badge_rect = pygame.Rect(Config.WINDOW_WIDTH - 260, 45, 200, 50)

        # Shadow 
        shadow_rect = badge_rect.move(3, 3)
        pygame.draw.rect(self.manager.screen, (0, 0, 0), shadow_rect, border_radius=12)

        # Background
        pygame.draw.rect(self.manager.screen, bg_color, badge_rect, border_radius=12)

        # Border
        pygame.draw.rect(self.manager.screen, border_color, badge_rect, 3, border_radius=12)

        # Text
        level_text = self.font.render(f"LEVEL {level}", True, text_color)

        # Center text
        text_rect = level_text.get_rect(center=badge_rect.center)
        self.manager.screen.blit(level_text, text_rect)

        # Castle Progress HUD
        nearby_unconquered_castles = []
        for c in self.engine.world.castles:
            if c.level == self.engine.world.current_level and c.is_spawned and not c.is_conquered:
                if HexMath.distance(p.q, p.r, c.q, c.r) <= 8:
                    nearby_unconquered_castles.append(c)
        
        if nearby_unconquered_castles:
            # Show progress for the first nearby castle
            target_castle = nearby_unconquered_castles[0]
            
            total_monsters = len(target_castle.spawn_points)
            alive_monsters = len([m for m in self.engine.world.monsters if m.castle_id == target_castle.id and m.is_alive()])
            defeated_monsters = max(0, total_monsters - alive_monsters)
            
            progress_text = self.font.render(f"Castle: {defeated_monsters}/{total_monsters} Monsters Defeated", True, (255, 236, 140))
            
            bar_w = max(300, progress_text.get_width() + 40)
            bar_h = 40
            bar_x = (Config.WINDOW_WIDTH - bar_w) // 2
            bar_y = 60
            
            s = pygame.Surface((bar_w, bar_h), pygame.SRCALPHA)
            s.fill((0, 0, 0, 150))
            self.manager.screen.blit(s, (bar_x, bar_y))
            pygame.draw.rect(self.manager.screen, (212, 175, 55), (bar_x, bar_y, bar_w, bar_h), 2, border_radius=4)
            
            t_rect = progress_text.get_rect(center=(bar_x + bar_w//2, bar_y + bar_h//2))
            self.manager.screen.blit(progress_text, t_rect)
    
    def draw_hearts(self, max_hearts, current_hearts, start_x, y):
        spacing = 35

        for i in range(max_hearts):
            color = (220, 40, 40) if i < current_hearts else (80, 80, 80)
            x = start_x + i * spacing
            self.draw_heart(x, y, color)
    
    def draw_heart(self, x, y, color):
        r = 8

        # top circles
        pygame.draw.circle(self.manager.screen, color, (x - r, y), r)
        pygame.draw.circle(self.manager.screen, color, (x + r, y), r)

        # bottom triangle
        points = [
            (x - 2 * r, y + 2),
            (x + 2 * r, y + 2),
            (x, y + 22),]
        pygame.draw.polygon(self.manager.screen, color, points)

    # Inventory screen with 3 sections
    def _draw_inventory(self):
        # Semi-transparent dark overlay
        overlay = pygame.Surface(
            (Config.WINDOW_WIDTH, Config.WINDOW_HEIGHT), pygame.SRCALPHA
        )
        overlay.fill((0, 0, 0, 160))
        self.manager.screen.blit(overlay, (0, 0))

        # Main panel
        p = self.engine.world.player
        panel_x, panel_y = 200, 80
        panel_w, panel_h = Config.WINDOW_WIDTH - 400, Config.WINDOW_HEIGHT - 160
        panel_rect = pygame.Rect(panel_x, panel_y, panel_w, panel_h)
        self._draw_panel_box(panel_rect, (22, 24, 29), (176, 182, 188), 3)

        self._draw_inventory_header(panel_rect, p)

        # Splits the panel body into left list and right sidebar
        body_top = panel_y + 116
        body_height = panel_h - 140
        left_width = int(panel_w * 0.62)
        sidebar_width = panel_w - left_width - 54

        # Define rectangles for the three sections
        list_rect = pygame.Rect(panel_x + 18, body_top, left_width, body_height)
        equipment_rect = pygame.Rect(
            list_rect.right + 18,
            body_top,
            sidebar_width,
            174,
        )
        details_rect = pygame.Rect(
            list_rect.right + 18,
            equipment_rect.bottom + 14,
            sidebar_width,
            body_height - equipment_rect.height - 14,
        )

        # Get the player's inventory items
        items = self.engine.world.player.inventory
        selected_item = None
        if items and self.engine.selected_index < len(items):
            selected_item = items[self.engine.selected_index]

        # Draw the three sections of the inventory panel
        self._draw_inventory_list(list_rect, items)
        self._draw_equipment_summary(equipment_rect, p)
        self._draw_selected_item_details(details_rect, selected_item)