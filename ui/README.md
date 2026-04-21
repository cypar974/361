# UI Module (Pygame Edition)

This module manages the game window, input loop, and user interface elements using **Pygame**.

## Coordinate System
To ensure the UI renders correctly across different screen resolutions, we use **relative coordinates** 
- **Buttons and Panels:** Calculated dynamically based on `self.manager.width` and `self.manager.height`.

## Files
- `game_window.py`: Contains the main game loop, event polling, and the update/draw cycle. It handles the inventory overlay with relative positioning.
- `base_screen.py`: Abstract base class for all UI screens.
- `screen_manager.py`: Manages transitions between different screens (Welcome, Main Menu, Game, etc.).
- `button.py`: A custom `Button` class for handling clickable UI elements.
- `welcome.py`, `main_menu.py`, `characters.py`, `game_rules.py`, `save_menu.py`, `game_over.py`, `winner.py`: Individual screen implementations using relative coordinate systems.
