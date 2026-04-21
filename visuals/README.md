# Visuals Module (Pygame Edition)

This module handles the artistic representation of the game using **Pygame**.

**Files:**
- `asset_manager.py`: Loads images using `pygame.image.load()` and caches them as `pygame.Surface` objects for performance.
- `renderer.py`: Handles the drawing of surfaces to the main screen using `screen.blit()`. It manages the paint order (terrain first, then objects/entities).