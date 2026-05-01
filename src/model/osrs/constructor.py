import time

import utilities.api.item_ids as ids
import utilities.color as clr
import utilities.random_util as rd
import utilities.imagesearch as imsearch
import random
import pyautogui as pag
from model.osrs.jagex_account_bot import OSRSJagexAccountBot
from model.runelite_bot import BotStatus
from utilities.api.morg_http_client import MorgHTTPSocket
from utilities.api.status_socket import StatusSocket
from utilities.geometry import RuneLiteObject


class OSRSConstructor(OSRSJagexAccountBot):
    def __init__(self):
        bot_title = "Constructor"
        description = (
            "This bot constructs items"
        )
        super().__init__(bot_title=bot_title, description=description, debug=False)
        self.running_time = 1
        self.take_breaks = False
        self.skip_slots = []

    def create_options(self):
        self.options_builder.add_slider_option("running_time", "How long to run (minutes)?", 5, 500)
        self.options_builder.add_checkbox_option("take_breaks", "Take breaks?", [" "])
        self.options_builder.add_dropdown_option("item_type", "Item Type:", ["Mahogany", "Oak"])

    def save_options(self, options: dict):
        for option in options:
            if option == "running_time":
                self.running_time = options[option]
            elif option == "take_breaks":
                self.take_breaks = options[option] != []
            elif option == "item_type":
                self.item_type = options[option]
            else:
                self.log_msg(f"Unknown option: {option}")
                print("Developer: ensure that the option keys are correct, and that options are being unpacked correctly.")
                self.options_set = False
                return
        self.log_msg(f"Running time: {self.running_time} minutes.")
        self.log_msg(f"Bot will{' ' if self.take_breaks else ' not '}take breaks.")
        self.log_msg(f"{self.item_type} when inventory is full.")
        self.log_msg("Options set successfully.")
        self.options_set = True
        self.min_planks = 6 if self.item_type == "Mahogany" else 8

    def main_loop(self):
        # Setup API
        # api_m = MorgHTTPSocket()
        # api_s = StatusSocket()

        self.log_msg("Selecting inventory...")
        self.mouse.move_to(self.win.cp_tabs[3].random_point())
        self.mouse.click()

        # Main loop
        start_time = time.time()
        end_time = self.running_time * 60
        build_key = "6" if self.item_type == "Mahogany" else "2"
        

        while time.time() - start_time < end_time:
            if rd.random_chance(probability=0.05) and self.take_breaks:
                self.take_break(max_seconds=30, fancy=True)
            

            if self.get_item_count(f"{self.item_type}_plank") < self.min_planks:
                print(f"Not enough {self.item_type} planks, waiting for more...")
                if not self.__talk_to_butler():
                    continue
                print(f"Waiting for {self.item_type} planks...")
                continue

            # build the table or destroy the table
            if not self.__click_object([(clr.PINK, build_key), (clr.YELLOW, "1")]):
                continue

            # Wait until no more planks
            if self.get_item_count(f"{self.item_type}_plank") < self.min_planks:
                print(f"Not enough {self.item_type} planks, waiting for more...")
                if not self.__talk_to_butler():
                    continue
                print(f"Waiting for {self.item_type} planks...")
                continue

            self.update_progress((time.time() - start_time) / end_time)

        self.update_progress(1)
        self.logout("Finished.")

    def __talk_to_butler(self) -> bool:
        """
        Talks to the butler
        Returns:
            True if successful, False otherwise.
        """
        if not self.__click_object([(clr.CYAN, "1")]):
            return True

        if self.get_item_count(f"{self.item_type}_plank") < self.min_planks:
            print(f"Not enough {self.item_type} planks, waiting for more...")
            pag.press("1")
            if not self.__click_object([(clr.CYAN, "space"), (clr.YELLOW, "1")]):
                print("Paying butler...")
                time.sleep(2)
                self.__talk_to_butler()

        return True

    def __click_object(self, color_key_pairs: list[tuple[clr, str]], wait: float = 1.5):
        """
        Attempts to click an object with any of the provided color-key pairs.
        Args:
            color_key_pairs: List of tuples where each tuple is (color, key).
            wait: Time to sleep after clicking (default: 2.5 seconds).
        Returns:
            True if any click was successful, False otherwise.
        """
        options = ["Remove", "Build", "Talk"]
        for color, key in color_key_pairs:
            if not self.move_mouse_to_nearest_item(color):
                continue
            if not self.mouseover_text(contains=options):
                continue
            self.mouse.click()
            time.sleep(wait + random.betavariate(1, 3))  # Skewed towards 0
            pag.press(key)
            time.sleep(1 + random.betavariate(1, 3))  # Skewed towards 0
            if key == "space":
                pag.press("1")
                time.sleep(1 + random.betavariate(1, 3))  # Skewed towards 0
            return True
        return False

