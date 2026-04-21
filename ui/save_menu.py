import pygame
import sys
import os
import json
import shutil
from visuals.asset_manager import AssetManager
import ui.button

# state design pattern
from ui.base_screen import Screen

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class SaveSelectMenu(Screen):
    def __init__(self, manager):
        super().__init__(manager)
        font_path = os.path.join(
            BASE_DIR, "..", "assets", "fonts", "Jersey10-Regular.ttf"
        )
        self.title_font = pygame.font.Font(font_path, 140)
        self.button_font = pygame.font.Font(font_path, 50)
        self.confirm_font = pygame.font.Font(font_path, 80)

        self.am = AssetManager()
        self._load_skins()
        self.current_skin_idx = 0

        self.skin_y = 150

        self.skin_y = 150

        # Confirmation State
        self.confirm_delete_slot = None  # None or slot_id

        # Colors
        self.bg_color = (79, 79, 79)
        self.text_color = (154, 205, 50)
        self.btn_text_color = (255, 255, 255)
        self.btn_color = (70, 70, 90)
        self.hover_color = (120, 100, 160)
        self.slot_color = (199, 234, 70)
        self.del_color = (147, 112, 219)
        self.del_hover = (120, 100, 160)

        self.slots = [1, 2, 3]
        self.buttons = []
        self._create_buttons()

        self.decoration_images = [
            ("Water_Duck.png", -365, 75, 5, 2.3999999999999995),
            ("Grass.png", -410, 175, 20, 1.5999999999999996),
            ("Grass_Pine.png", 309, 201, -15, 2.1),
            ("Magic_Crystals.png", -290, 200, -15, 2.8),
            ("Snow_Trees.png", 373, 76, 10, 2.4999999999999996),
            ("Grass_Plants2.png", 470, 145, 25, 1.5999999999999996),
        ]

    def draw_image(self, image_name: str, x: int, y: int, angle: int, scale: float):
        """
        Draw image on the screen.
        """
        image_path = os.path.join(
            BASE_DIR, "..", "assets", "assetBank", "Hex Tiles", image_name
        )

        image = pygame.image.load(image_path).convert_alpha()

        original_w, original_h = image.get_size()
        scaled_image = pygame.transform.scale(
            image, (int(original_w * scale), int(original_h * scale))
        )
        rotated_image = pygame.transform.rotate(scaled_image, angle)
        rect = rotated_image.get_rect(center=(x, y))

        self.manager.screen.blit(rotated_image, rect)

    def _load_skins(self):
        self.skins = []
        player_def_dir = "assets/definitions/player"
        if os.path.exists(player_def_dir):
            for f in os.listdir(player_def_dir):
                if f.endswith(".json"):
                    try:
                        with open(os.path.join(player_def_dir, f), "r") as jf:
                            data = json.load(jf)
                            skin_name = data.get("name", f.replace(".json", ""))
                            tex = data.get("texture_file")
                            if not tex and "animations" in data:
                                tex = data["animations"].get("idle", {}).get("texture")
                            if tex:
                                self.skins.append({"name": skin_name, "texture": tex})
                    except Exception as e:
                        print(f"Error loading skin {f}: {e}")

        if not self.skins:
            self.skins.append({"name": "Default", "texture": None})

    def _create_buttons(self):
        self.buttons = []

        button_width = 400  # bigger width
        button_height = 90  # bigger height
        spacing = 100  # space between rows

        total_height = len(self.slots) * spacing
        start_y = (self.manager.height // 2) - (total_height // 2)

        for i, slot in enumerate(self.slots):
            y = start_y + i * spacing

            # Center main button
            rect = pygame.Rect(
                self.manager.width // 2 - button_width // 2,
                y,
                button_width,
                button_height,
            )

            # Delete button (to the right of main button)
            del_rect = pygame.Rect(rect.right + 20, y, 80, button_height)

            self.buttons.append(
                {
                    "type": "slot",
                    "rect": rect,
                    "text": f"Save Slot {slot}",
                    "value": slot,
                }
            )

            self.buttons.append(
                {"type": "delete", "rect": del_rect, "text": "X", "value": slot}
            )

    def draw(self):
        self.manager.screen.fill(self.bg_color)
        center_x = self.manager.width // 2
        for image_name, dx, dy, angle, scale in self.decoration_images:
            self.draw_image(image_name, center_x + dx, dy, angle, scale)

        # Title
        title_surf = self.title_font.render("SAVED GAMES", True, self.text_color)
        title_rect = title_surf.get_rect(center=(self.manager.width // 2, 120))
        self.manager.screen.blit(title_surf, title_rect)

        mouse_pos = pygame.mouse.get_pos()

        for btn in self.buttons:
            slot = btn["value"]
            target_db = f"game_data_{slot}.db"
            file_exists = os.path.exists(target_db)

            rect = btn["rect"]
            is_hover = rect.collidepoint(mouse_pos)

            if btn["type"] == "slot":
                text = f"Load Save {slot}" if file_exists else f"Create Save {slot}"

                color = self.hover_color if is_hover else self.slot_color
                pygame.draw.rect(self.manager.screen, color, rect)
                pygame.draw.rect(self.manager.screen, (100, 100, 100), rect, 2)

                text_surf = self.button_font.render(text, True, self.btn_text_color)
                text_rect = text_surf.get_rect(center=rect.center)
                self.manager.screen.blit(text_surf, text_rect)

            elif btn["type"] == "delete" and file_exists:
                color = self.del_hover if is_hover else self.del_color
                pygame.draw.rect(self.manager.screen, color, rect)
                pygame.draw.rect(self.manager.screen, (100, 100, 100), rect, 2)

                text_surf = self.button_font.render("X", True, self.btn_text_color)
                text_rect = text_surf.get_rect(center=rect.center)
                self.manager.screen.blit(text_surf, text_rect)

        # Confirmation Dialouge
        if self.confirm_delete_slot:
            self._draw_confirmation()

    def _draw_confirmation(self):
        # Darken background
        overlay = pygame.Surface((self.manager.width, self.manager.height))
        overlay.set_alpha(180)
        overlay.fill((0, 0, 0))
        self.manager.screen.blit(overlay, (0, 0))

        msg = f"Delete Save Slot {self.confirm_delete_slot}?"
        text_surf = self.confirm_font.render(msg, True, (255, 255, 255))
        tw, th = text_surf.get_size()

        # Popup Box but reactive in size to the text
        padding = 40
        box_w = tw + padding * 2
        box_h = th + 120  # text + space for buttons

        box_x = (self.manager.width - box_w) // 2
        box_y = (self.manager.height - box_h) // 2
        box_rect = pygame.Rect(box_x, box_y, box_w, box_h)
        pygame.draw.rect(self.manager.screen, (50, 50, 50), box_rect, border_radius=15)
        pygame.draw.rect(
            self.manager.screen, (200, 50, 50), box_rect, 2, border_radius=15
        )

        text_rect = text_surf.get_rect(
            center=(self.manager.width // 2, box_y + padding + th // 2)
        )
        self.manager.screen.blit(text_surf, text_rect)

        # Yes / No Buttons
        btn_w, btn_h = 120, 50
        buttons_y = box_rect.bottom - 70
        yes_rect = pygame.Rect(
            self.manager.width // 2 - btn_w - 20, buttons_y, btn_w, btn_h
        )
        no_rect = pygame.Rect(self.manager.width // 2 + 20, buttons_y, btn_w, btn_h)

        mouse_pos = pygame.mouse.get_pos()

        # Yes
        c_yes = (200, 50, 50) if yes_rect.collidepoint(mouse_pos) else (150, 50, 50)
        pygame.draw.rect(self.manager.screen, c_yes, yes_rect, border_radius=5)
        yes_txt = self.button_font.render("YES", True, (255, 255, 255))
        self.manager.screen.blit(yes_txt, yes_txt.get_rect(center=yes_rect.center))

        # No
        c_no = (100, 100, 100) if no_rect.collidepoint(mouse_pos) else (80, 80, 80)
        pygame.draw.rect(self.manager.screen, c_no, no_rect, border_radius=5)
        no_txt = self.button_font.render("NO", True, (255, 255, 255))
        self.manager.screen.blit(no_txt, no_txt.get_rect(center=no_rect.center))

        self.confirm_buttons = {"yes": yes_rect, "no": no_rect}

    def _delete_save(self, slot):
        filename = f"game_data_{slot}.db"
        if os.path.exists(filename):
            try:
                os.remove(filename)
                print(f"Deleted {filename}")
            except Exception as e:
                print(f"Error deleting {filename}: {e}")
        else:
            print(f"File {filename} does not exist.")

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                if self.confirm_delete_slot:
                    self.confirm_delete_slot = None
                else:
                    self.manager.switch_screen("main_menu")

        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                if self.confirm_delete_slot:
                    # Handle Confirmation
                    if self.confirm_buttons["yes"].collidepoint(event.pos):
                        self._delete_save(self.confirm_delete_slot)
                        self.confirm_delete_slot = None
                    elif self.confirm_buttons["no"].collidepoint(event.pos):
                        self.confirm_delete_slot = None
                else:
                    # Handle Slot Buttons
                    for btn in self.buttons:
                        slot = btn["value"]
                        target_db = f"game_data_{slot}.db"
                        file_exists = os.path.exists(target_db)

                        if btn["rect"].collidepoint(event.pos):
                            if btn["type"] == "slot":
                                target_db = f"game_data_{slot}.db"
                                is_new_game = not os.path.exists(target_db)

                                if is_new_game:
                                    if os.path.exists("default.db"):
                                        print(
                                            f"Creating new save slot {slot} from default.db..."
                                        )
                                        shutil.copy("default.db", target_db)
                                    else:
                                        print(
                                            "No default.db found! Starting with empty database."
                                        )

                                self.manager.selected_slot = slot

                                if is_new_game:
                                    # Make archer default for now (until we have more characters)
                                    self.manager.selected_skin = "archer"
                                    self.manager.switch_screen("characters")
                                else:
                                    self.manager.selected_skin = None  # Don't overwrite existing skin as you can't change it in-game
                                    # as they will have different stats depending on the skin
                                    self.manager.switch_screen("game_window")
                                break  # Exit loop after handling click

                            elif btn["type"] == "delete" and file_exists:
                                self.confirm_delete_slot = btn["value"]
                                break  # Exit loop after handling click
