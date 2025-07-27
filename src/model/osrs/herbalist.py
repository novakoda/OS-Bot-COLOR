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


class OSRSHerbalist(OSRSJagexAccountBot):
    def __init__(self):
        bot_title = "Herbalist"
        description = (
            "This crafts potions"
        )
        super().__init__(bot_title=bot_title, description=description, debug=False)
        self.running_time = 1
        self.take_breaks = False
        self.skip_slots = []

    def create_options(self):
        self.options_builder.add_slider_option("running_time", "How long to run (minutes)?", 5, 500)
        self.options_builder.add_checkbox_option("take_breaks", "Take breaks?", [" "])

    def save_options(self, options: dict):
        for option in options:
            if option == "running_time":
                self.running_time = options[option]
            elif option == "take_breaks":
                self.take_breaks = options[option] != []
            else:
                self.log_msg(f"Unknown option: {option}")
                print("Developer: ensure that the option keys are correct, and that options are being unpacked correctly.")
                self.options_set = False
                return
        self.log_msg(f"Running time: {self.running_time} minutes.")
        self.log_msg(f"Bot will{' ' if self.take_breaks else ' not '}take breaks.")
        self.log_msg("Options set successfully.")
        self.options_set = True

    def main_loop(self):
        self.log_msg("Selecting inventory...")
        self.mouse.move_to(self.win.cp_tabs[3].random_point())
        self.mouse.click()

        # Main loop
        start_time = time.time()
        end_time = self.running_time * 60
        while time.time() - start_time < end_time:
            # Craft potions again
            if not self.__craft_potions():
                continue

            # Wait until only 14 items left in inventory
            while self.get_item_count() > 14:
                time.sleep(1)

            # Open bank
            if not self.open_bank():
                continue

            # Withdraw Snape grass
            if not self.withdraw_item(4, conf=0.10) and not self.withdraw_item("Snape_grass_2", conf=0.10):
                continue

            # Close bank
            pag.press("escape")

            # Craft potions
            if not self.__craft_potions():
                continue

            # Wait until only 14 items left in inventory
            while self.get_item_count() > 14:
                time.sleep(1)

            # Open bank
            if not self.open_bank():
                continue

            # Click item in slot 0
            if not self.click_inventory_slot(0):
                continue

            # Withdraw Vial_of_water and Ranarr_weed
            if not self.withdraw_item(2, conf=0.14, keep_open=True):
                continue
            if not self.withdraw_item(3, conf=0.14):
                continue

            # Close bank
            pag.press("escape")

            self.update_progress((time.time() - start_time) / end_time)

        self.update_progress(1)
        self.logout("Finished.")

    def __craft_potions(self) -> bool:
        """
        Clicks items in slot 0 and 14, then presses space to craft.
        Returns:
            True if successful, False otherwise.
        """
        # Click item in slot 0
        if not self.click_inventory_slot(0):
            return False

        # Click item in slot 14
        if not self.click_inventory_slot(14):
            return False

        time.sleep(0.3)
        # Press space to craft
        pag.press("space")
        self.mouse.move_to(self.win.chat.random_point(), mouseSpeed="slow", knotsCount=2)
        return True

    def get_item_count(self) -> int:
        """
        Returns the number of items in the inventory.
        Uses the parent class's `is_inventory_full` logic but counts items instead.
        """
        empty_img = imsearch.BOT_IMAGES.joinpath("ui_templates", "empty_slot.png")
        count = 0
        for slot in self.win.inventory_slots:
            if not imsearch.search_img_in_rect(empty_img, slot, confidence=0.1):
                count += 1
        return count

    def deposit_all(self) -> bool:
        """
        Deposits all items in the inventory.
        Returns:
            True if successful, False otherwise.
        """
        return self.deposit_to_bank()

    def open_bank(self) -> bool:
        """
        Opens the bank.
        Returns:
            True if successful, False otherwise.
        """
        if not self.move_mouse_to_nearest_item(clr.YELLOW):
            return False
        if not self.mouseover_text(contains="Bank"):
            return False
        self.mouse.click()
        time.sleep(1)
        self.win.locate_bank_slots(self.win.rectangle())
        return True

