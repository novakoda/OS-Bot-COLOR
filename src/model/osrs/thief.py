import time

import utilities.api.item_ids as ids
import utilities.color as clr
import utilities.random_util as rd
import pyautogui as pag
from model.osrs.jagex_account_bot import OSRSJagexAccountBot
from model.runelite_bot import BotStatus
from utilities.api.morg_http_client import MorgHTTPSocket
from utilities.api.status_socket import StatusSocket
from utilities.geometry import RuneLiteObject
import random
import pytweening


class OSRSThief(OSRSJagexAccountBot):
    def __init__(self):
        bot_title = "Thief"
        description = (
            "Tag the fruit item and the bot will steal and drop your inventory in between steals. Set slots that you don't want to drop in the options seperated by spaces"
        )
        super().__init__(bot_title=bot_title, description=description, debug=False)
        self.running_time = 1
        self.take_breaks = False

    def create_options(self):
        self.options_builder.add_slider_option("running_time", "How long to run (minutes)?", 1, 500)
        self.options_builder.add_checkbox_option("take_breaks", "Take breaks?", [" "])
        self.options_builder.add_text_edit_option("skip_slots", "Skip Slots (space seperated)", "0 1 2")
    def save_options(self, options: dict):
        for option in options:
            if option == "running_time":
                self.running_time = options[option]
            elif option == "take_breaks":
                self.take_breaks = options[option] != []
            elif option == "skip_slots":
                self.skip_slots = [int(slot) for slot in options[option].split()] if options[option].strip() else []
            else:
                self.log_msg(f"Unknown option: {option}")
                print("Developer: ensure that the option keys are correct, and that options are being unpacked correctly.")
                self.options_set = False
                return
        self.log_msg(f"Running time: {self.running_time} minutes.")
        self.log_msg(f"Bot will{' ' if self.take_breaks else ' not '}take breaks.")
        self.log_msg(f"Skipping Slots: {self.skip_slots} when dropping items.")
        self.log_msg("Options set successfully.")
        self.options_set = True

    def main_loop(self):
        self.log_msg("Selecting inventory...")
        self.mouse.move_to(self.win.cp_tabs[3].random_point())
        self.mouse.click()

        self.logs = 0
        failed_searches = 0
        alternate = False  # Flag to alternate the order

        # Main loop
        start_time = time.time()
        end_time = self.running_time * 60
        while time.time() - start_time < end_time:
            # 5% chance to take a break between tree searches
            if rd.random_chance(probability=0.05) and self.take_breaks:
                self.take_break(max_seconds=30, fancy=True)

            if not self.mouseover_text(contains="Steal") and not self.move_mouse_to_nearest_item(clr.PINK):
                failed_searches += 1
                if failed_searches % 10 == 0:
                    self.log_msg("Searching for tagged items...")
                if failed_searches > 60:
                    # If we've been searching for a whole minute...
                    self.__logout("No tagged items found. Logging out.")
                time.sleep(1)
                continue
            failed_searches = 0

             # Click if the mouseover text assures us we're clicking a tree
            if not self.mouseover_text(contains="Steal"):
                continue
            self.mouse.click()
            time.sleep(random.betavariate(1, 3))
            self.drop_all(skip_slots=self.skip_slots)
            time.sleep(random.betavariate(1, 3))
            self.update_progress((time.time() - start_time) / end_time)

        self.update_progress(1)
        self.__logout("Finished.")

    def __logout(self, msg):
        self.log_msg(msg)
        self.logout()
        self.stop()


    def __click_object(self, wait: float = 2.5):
        """
        Attempts to click an object with any of the provided color-key pairs.
        Args:
            color_key_pairs: List of tuples where each tuple is (color, key).
            wait: Time to sleep after clicking (default: 2.5 seconds).
        Returns:
            True if any click was successful, False otherwise.
        """
        options = ["Steal"]
        for color, key in color_key_pairs:
            if not self.move_mouse_to_nearest_item(clr.PINK):
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


