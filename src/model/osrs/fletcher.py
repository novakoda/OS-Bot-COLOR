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


class OSRSFletcher(OSRSJagexAccountBot):
    def __init__(self):
        bot_title = "Fletcher"
        description = (
            "This bot power-chops wood. Position your character near some trees, tag them, and press Play.\n\nLog Actions:\nDeposit in bank - Requires bank to be tagged yellow\nLight on fire: Requires tinderbox and firemaking level for logs\nDrop: Drops the logs"
        )
        super().__init__(bot_title=bot_title, description=description, debug=False)
        self.running_time = 1
        self.take_breaks = False

    def create_options(self):
        self.options_builder.add_slider_option("running_time", "How long to run (minutes)?", 1, 500)
        self.options_builder.add_checkbox_option("take_breaks", "Take breaks?", [" "])
        self.options_builder.add_slider_option("item_slot_1", "Item Slot? (i.e. Feather)", 0, 23)
        self.options_builder.add_slider_option("item_slot_2", "Item Slot 2? (i.e. Bolt Tip)", 0, 23)
    def save_options(self, options: dict):
        for option in options:
            if option == "running_time":
                self.running_time = options[option]
            elif option == "take_breaks":
                self.take_breaks = options[option] != []
            elif option == "item_slot_1":
                self.item_slot_1 = options[option]
            elif option == "item_slot_2":
                self.item_slot_2 = options[option]
            else:
                self.log_msg(f"Unknown option: {option}")
                print("Developer: ensure that the option keys are correct, and that options are being unpacked correctly.")
                self.options_set = False
                return
        self.log_msg(f"Running time: {self.running_time} minutes.")
        self.log_msg(f"Bot will{' ' if self.take_breaks else ' not '}take breaks.")
        self.log_msg(f"Item slot 1: {self.item_slot_1}.")
        self.log_msg(f"Item slot 2: {self.item_slot_2}.")
        self.log_msg("Options set successfully.")
        self.options_set = True

    def main_loop(self):
        # Setup API
        # api_m = MorgHTTPSocket()
        # api_s = StatusSocket()

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

            # Alternate the order of clicking items
            if alternate:
                self.__click_item(self.item_slot_2)
                time.sleep(0.5 + random.betavariate(1, 3))
                self.__click_item(self.item_slot_1)
            else:
                self.__click_item(self.item_slot_1)
                time.sleep(0.5 + random.betavariate(1, 3))
                self.__click_item(self.item_slot_2)
            alternate = not alternate  # Toggle the flag for the next iteration

            time.sleep(0.5 + random.betavariate(1, 3))
            pag.press("space")
            time.sleep(9 + random.betavariate(1, 3))

            self.update_progress((time.time() - start_time) / end_time)

        self.update_progress(1)
        self.__logout("Finished.")

    def __logout(self, msg):
        self.log_msg(msg)
        self.logout()
        self.stop()


    def __click_item(self, item_slot):
        t = self.win.inventory_slots[item_slot].random_point()
        self.mouse.move_to(
            (t[0], t[1]),
            mouseSpeed="fastest",
            knotsCount=1,
            offsetBoundaryY=40,
            offsetBoundaryX=40,
            tween=pytweening.easeInOutQuad,
        )
        self.mouse.click()


