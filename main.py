from abc import ABC, abstractmethod
import pygame


from ui.base_screen import Screen
import os


#screens (only place all the screens are imported)
# add to available screen dictionaty attribute
import ui.welcome as screen1
import ui.winner as screen2
import ui.game_rules as screen3
import ui.main_menu as screen4
import ui.characters as screen5
import ui.save_menu as screen6
import ui.game_window as screen7
import ui.game_over as screen8


# singleton and state design pattern
# singleton: (called first) run __new__(allocate memory) once, __init__(fill the memory) once to have non idempotent elements recreated
class ScreenManager:
    

    _screenManager_instance = None
    _initialized = False

    # cls = ScreenManager
    # override __new__
    def __new__(cls):
        # object is never created
        if cls._screenManager_instance is None:
            # call the parent class to create the object
            cls._screenManager_instance = super().__new__(cls)
        # object is created, return the same instance
        return cls._screenManager_instance

    def __init__(self):
        if self._initialized:
            #already initialized so don't recreate it
            return

        pygame.init()

        try:
            pygame.mixer.init()
        except pygame.error as e:
            print(f"Audio init failed: {e}")

        pygame.display.set_caption("Beyond") 

        # font has differnet sizes

        # background color (grey)
        self.bg_color = (79, 79, 79)
        # text color (green)
        self.text_color_green = (154, 205, 50)
        # text color (white)
        self.text_color_white = (255, 255, 255)

        # used for welcome screen to switch after 5 seconds
        self.start_time = pygame.time.get_ticks()
        
        self.current_music = None
        from core.config import Config
        import os
        import platform
        
        # window size full screen windowed (maximized)
        info = pygame.display.Info()
        self.width, self.height = info.current_w, info.current_h
        
        # FIX: Initialize with fixed size (no resizing allowed)
        self.screen = pygame.display.set_mode((self.width, self.height))
        
        # Maximize window on Windows
        if platform.system() == "Windows":
            try:
                import ctypes
                hwnd = pygame.display.get_wm_info().get("window")
                if hwnd:
                    # 3 is SW_MAXIMIZE
                    ctypes.windll.user32.ShowWindow(hwnd, 3)
            except Exception as e:
                print(f"Could not maximize window: {e}")

        # Update width and height from the actual window surface after maximization
        self.width, self.height = self.screen.get_size()
        
        # Sync with Config for UI and Game logic
        Config.WINDOW_WIDTH = self.width
        Config.WINDOW_HEIGHT = self.height
        Config.CENTER_X = self.width // 2
        Config.CENTER_Y = self.height // 2
        
        self.clock = pygame.time.Clock()
        self.running = True
        #game window specific variables
        self.selected_slot = None
        self.selected_skin = None

       
        self.available_screens = {
            "welcome": screen1.Welcome,
            "winner": screen2.Winner,
            "game_rules": screen3.GameRules,
            "main_menu": screen4.MainMenu,
            "characters": screen5.Characters,
            "save_menu": screen6.SaveSelectMenu,
            "game_window": screen7.GameWindow, 
            "game_over": screen8.GameOver
        }

        #start screen
        self.current_screen = self.available_screens["welcome"](self)
        self.play_music("start.mp3")
        self.current_music = "start.mp3"

        # part of singletone patern
        # want to avoid reinitialization 
        self._initialized = True

    def switch_screen(self, new_screen: str):
        # makes sure that the previous screen is cleaned up before switching to the new screen
        # This prevents the locking of the db file when switching screens
        if hasattr(self, "current_screen") and hasattr(self.current_screen, "cleanup"):
            try:
                self.current_screen.cleanup()
            except Exception as e:
                print(f"Issue during screen cleanup:\n {e}")

        self.current_screen = self.available_screens[new_screen](self)

        
        if new_screen == "main_menu" :
            self.play_music("start.mp3")
        elif new_screen == "game_window":
            self.play_music("game.mp3")
        elif new_screen == "winner":
            self.play_music("winner.mp3", loops=0)
        elif new_screen == "game_over":
            self.play_music("game_over.mp3", loops=0) 
        

    def run(self):
        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                    # Removed screen resize event handler
                else:
                    self.current_screen.handle_event(event)

            self.current_screen.draw()
            pygame.display.flip()  # Update the full display surface to the screen
           
            self.clock.tick(60)  # Limit to 60 FPS

        pygame.quit()
        
    def play_music(self, filename, loops=-1, volume=0.5):
        if self.current_music == filename:
            return
        try:
            path = os.path.join("assets", "music", filename)
            pygame.mixer.music.load(path)
            pygame.mixer.music.set_volume(volume)
            pygame.mixer.music.play(loops)
            self.current_music = filename
        except pygame.error as e:
            print(f"Could not play music {filename}: {e}")

    def stop_music(self):
        pygame.mixer.music.stop()
        self.current_music = None

if __name__ == "__main__":
    manager = ScreenManager()
    manager.run()
