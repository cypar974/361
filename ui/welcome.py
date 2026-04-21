import pygame
import sys
import os
from pygame.draw import rect

from ui.base_screen import Screen

# Constants
BASE_DIR = os.path.dirname(os.path.abspath(__file__)) # directory of this script

# screen resolution of original computer that placed the images for relative image placement
ORIGINAL_SCREEN_W = 1536
ORIGINAL_SCREEN_H = 1024

class Welcome(Screen):
    def __init__(self, manager):
        super().__init__(manager)

        # make images relative (verses absolute) to be positioned properly on all screen sizes
        # on original laptop screen (1536x1024) correct image placement

        # (image name, x (percentage), y (percentage) , anngle, scale)
        self.decoration_images = [
            ('Water_Duck.png', 98/ORIGINAL_SCREEN_W, 68/ORIGINAL_SCREEN_H, 30, 4.7),
            ('Dirt_Pumpkins.png', 166/ORIGINAL_SCREEN_W, 372/ORIGINAL_SCREEN_H, 25, 3.7),
            ('Grass_Plants.png', 94/ORIGINAL_SCREEN_W, 247/ORIGINAL_SCREEN_H, 60, 2.8),
            ('Snow_Trees.png', 1270/ORIGINAL_SCREEN_W, 587/ORIGINAL_SCREEN_H, 25, 4.1),
            ('Magic_Crystals.png', 1421/ORIGINAL_SCREEN_W, 614/ORIGINAL_SCREEN_H, 40, 2.8),
            ('FrosenWater_Lilypads.png', 1297/ORIGINAL_SCREEN_W, 732/ORIGINAL_SCREEN_H, 20, 2.9),
            ('Magic.png', 265/ORIGINAL_SCREEN_W, 152/ORIGINAL_SCREEN_H, 20, 2.5),
            ('Snow.png', 286/ORIGINAL_SCREEN_W, 273/ORIGINAL_SCREEN_H, 35, 4.0),
            ('Grass_Plants2.png', 1452/ORIGINAL_SCREEN_W, 776/ORIGINAL_SCREEN_H, 30, 4.3)
        ]

        self.texts = [
            "WELCOME",
            "BEYOND"
        ]
    
    def handle_event(self, event):  
        pass
    
    def draw(self):
        """
        Draw the welcome screen with title and images.
        Input: None
        Output: None
        """
        self.manager.screen.fill(self.manager.bg_color) 

        self.draw_title()

        # Draw decoration images based on relative positions
        for image_name, x, y, angle, scale in self.decoration_images:
            # convert relative x and y to absolute position based on current screen size
            self.draw_image(image_name, int(x * self.manager.width), int(y * self.manager.height), angle, scale)


        # timing logic
        current_time = pygame.time.get_ticks()
        elapsed = current_time - self.manager.start_time
       
        if elapsed >= 4000:  # 4000 ms = 4 seconds
            self.manager.switch_screen("main_menu")

    def draw_title(self):
        """
        draw title on the screen
        Input: None
        Output: None
        """
        pygame.font.init()
        font = pygame.font.Font(os.path.join(BASE_DIR, '..', 'assets', 'fonts', 'Jersey10-Regular.ttf'), size=210)
        
        rendered_texts = []
        for text in self.texts:
            text = font.render(text, True, self.manager.text_color_green)
            rendered_texts.append(text)

        # the font has top and bottom padding
        # negative spacing allows the padding to overlap
        spacing = -70 

        total_text_height = 0

        for ren_text in rendered_texts:
            total_text_height += ren_text.get_height()
            
        total_text_height += spacing * (len(rendered_texts) - 1) 

        y_offset = (self.manager.height - total_text_height) // 2

        # blit each line
        # loop is used to adjust the y offset
        for text in rendered_texts:
            rect = text.get_rect(midtop=(self.manager.width // 2, y_offset)) # middle
            self.manager.screen.blit(source=text, dest=rect) 
            y_offset += text.get_height() + spacing
    
    def draw_image(self, image_name: str, x: int, y: int, angle: int, scale: float):
        """
        draw image on the screen
        Inputs:
            image_name(str): name of the image file 
            x(int): x position
            y(int): y position
            angle(int): rotation angle in degrees
            scale(float): scaling factor (e.g., 0.5 for half size, 2 for double size)
        Output: None
        """
        # path
        image_path = os. path.join(BASE_DIR, '..', 'assets', 'assetBank', 'Hex Tiles', image_name)
        
        image = pygame.image.load(image_path)
        original_w, original_h = image.get_size()
        scaled_image = pygame.transform.scale(image, (int(original_w * scale), int(original_h * scale)))
        rotated_image = pygame.transform.rotate(scaled_image, angle)
        rect = rotated_image.get_rect(center=(x, y))
        self.manager.screen.blit(rotated_image, rect)
