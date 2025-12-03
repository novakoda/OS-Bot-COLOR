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


class OSRSSmelter(OSRSJagexAccountBot):
    def __init__(self):
        bot_title = "Smelter"
        description = (
            "This bot smelts ore\n"
            "Tag the furnace PINK\n"
            "Tag the bank chest YELLOW\n"
            "Mark the iron ore RED (255, 0, 0) using bank highlighter plugin"
        )
        super().__init__(bot_title=bot_title, description=description, debug=False)
        self.running_time = 1
        self.take_breaks = False
        self.skip_slots = []

    def create_options(self):
        self.options_builder.add_slider_option("running_time", "How long to run (minutes)?", 5, 500)
        self.options_builder.add_checkbox_option("take_breaks", "Take breaks?", [" "])
        self.options_builder.add_dropdown_option("ore_type", "Ore Type:", ["Silver", "Iron", "Gold Bar", "Steel"])

    def save_options(self, options: dict):
        for option in options:
            if option == "running_time":
                self.running_time = options[option]
            elif option == "take_breaks":
                self.take_breaks = options[option] != []
            elif option == "ore_type":
                self.ore_type = options[option]
            else:
                self.log_msg(f"Unknown option: {option}")
                print("Developer: ensure that the option keys are correct, and that options are being unpacked correctly.")
                self.options_set = False
                return
        self.log_msg(f"Running time: {self.running_time} minutes.")
        self.log_msg(f"Bot will{' ' if self.take_breaks else ' not '}take breaks.")
        self.log_msg(f"{self.ore_type} when inventory is full.")
        self.log_msg("Options set successfully.")
        self.options_set = True

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
        while time.time() - start_time < end_time:
            if self.ore_type == "Iron":
                if not self.__smelt_ore(ore="Iron_ore2"):
                    continue

                # Wait until no more iron ore
                while self.get_item_slot("Iron_ore2") != -1:
                    time.sleep(1)

                # Bank items
                if not self.deposit_to_bank(keep_open=True):
                    continue

                self.withdraw_item(clr.RED)
            
            elif self.ore_type == "Steel":
                if not self.__smelt_ore(ore="Iron_ore2", key="2"):
                    continue

                # Wait until no more iron ore
                while self.get_item_slot("Iron_ore2") != -1:
                    time.sleep(1)

                # Bank items
                if not self.deposit_to_bank(keep_open=True):
                    continue

                # Withdraw coal and verify it's in inventory
                if not self.withdraw_item(clr.BLUE, keep_open=True):
                    continue
                print("clicked blue tag once")
                self.mouse.click()
                print("clicked blue tag twice")
                time.sleep(0.5)  # Brief wait for item to appear in inventory
                if self.get_item_slot(clr.BLUE) == -1:
                    self.log_msg("Coal not found in inventory after withdrawal, retrying...")
                    pag.press("esc")
                    continue
                print("clicking red tag")
                self.withdraw_item(clr.RED)

            elif self.ore_type == "Silver":
                # Verify inventory has tiara mould
                tiara_slot = self.get_item_slot("Tiara_mould")

                if tiara_slot == -1:
                    self.log_msg("Missing tiara mould!")
                    continue

                if self.skip_slots.count(tiara_slot) == 0:
                    self.skip_slots.append(tiara_slot)

                # Find and click furnace
                if not self.__smelt_ore("3"):
                    continue

                # Wait until no more silver ore
                while self.get_item_slot("Silver_ore") != -1:
                    time.sleep(1)

                if not self.__craft_tiaras():
                    continue

                # Wait until no more silver bars
                while self.get_item_slot("Silver_bar") != -1:
                    time.sleep(1)

                # Bank items (except tiara mould)
                if not self.deposit_to_bank(self.skip_slots, True):
                    continue

                self.withdraw_item("Silver_ore")

            elif self.ore_type == "Gold Bar":
                # Verify inventory has tiara mould
                tiara_slot = self.get_item_slot("Tiara_mould")

                if tiara_slot == -1:
                    self.log_msg("Missing tiara mould!")
                    continue

                if self.skip_slots.count(tiara_slot) == 0:
                    self.skip_slots.append(tiara_slot)

                if not self.__craft_tiaras("Gold_bar"):
                    continue

                while self.get_item_slot("Gold_bar") != -1:
                    time.sleep(1)

                # Bank items (except tiara mould)
                if not self.deposit_to_bank(self.skip_slots, True):
                    continue

                self.withdraw_item("Gold_bar")

            self.update_progress((time.time() - start_time) / end_time)

        self.update_progress(1)
        self.logout("Finished.")

    def __smelt_ore(self, key: str = "space", ore: str = "Silver_ore") -> bool:
        """
        Smelts ore and deposits the result to the bank.
        Returns:
            True if successful, False otherwise.
        """
        if self.get_item_slot(ore) == -1:
            return True

        if not self.__click_furnace():
            return False

        # Press 3 for silver bars
        secs = 0
        while not self.is_smelt_menu_open():
            secs += 1
            if secs > 6:
                # If we've been searching for 7 seconds...
                return False
            time.sleep(1)
        pag.press(key)
        return True

    def __craft_tiaras(self, bar: str = "Silver_bar") -> bool:
        """
        Smelts ore and deposits the result to the bank.
        Returns:
            True if successful, False otherwise.
        """
        if self.get_item_slot(bar) == -1:
            return True

        if not self.__click_furnace():
            return False

        # Click furnace again
        random_tab = random.choice(self.win.chat_tabs)
        self.mouse.move_to(random_tab.random_point(), mouseSpeed="slow", knotsCount=2)

        secs = 0
        while not self.is_smelt_menu_open():
            secs += 1
            if secs > 6:
                # If we've been searching for 7 seconds...
                return False
            time.sleep(1)

        pag.press("space")
        return True

    def __click_furnace(self):
        if not self.move_mouse_to_nearest_item(clr.PINK):
            return False
        if not self.mouseover_text(contains="Smelt"):
            return False
        self.mouse.click()
        time.sleep(1)
        return True

