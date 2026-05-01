import time

import utilities.color as clr
import utilities.random_util as rd
import pyautogui as pag
from model.osrs.common_banking import withdraw_tagged_item_from_bank_precise
from model.osrs.jagex_account_bot import OSRSJagexAccountBot
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
        self.fletching_type = "arrows"

    def create_options(self):
        self.options_builder.add_slider_option("running_time", "How long to run (minutes)?", 1, 500)
        self.options_builder.add_checkbox_option("take_breaks", "Take breaks?", [" "])
        self.options_builder.add_dropdown_option("fletching_type", "Fletching type:", ["arrows", "bows"])
        self.options_builder.add_slider_option("item_slot_1", "Item Slot? (i.e. Feather)", 0, 23)
        self.options_builder.add_slider_option("item_slot_2", "Item Slot 2? (i.e. Bolt Tip)", 0, 23)

    def save_options(self, options: dict):
        for option in options:
            if option == "running_time":
                self.running_time = options[option]
            elif option == "take_breaks":
                self.take_breaks = options[option] != []
            elif option == "fletching_type":
                self.fletching_type = options[option]
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
        self.log_msg(f"Fletching type: {self.fletching_type}.")
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

            if self.fletching_type == "bows":
                if not self.__fletch_bows_cycle():
                    time.sleep(1)
                    continue
            else:
                # Alternate the order of clicking items
                if alternate:
                    self.__click_item(self.item_slot_2)
                    self.__click_item(self.item_slot_1)
                else:
                    self.__click_item(self.item_slot_1)
                    self.__click_item(self.item_slot_2)
                alternate = not alternate  # Toggle the flag for the next iteration

            # pag.press("space")
            # time.sleep(9 + random.betavariate(1, 3))

            self.update_progress((time.time() - start_time) / end_time)

        self.update_progress(1)
        self.__logout("Finished.")

    def __logout(self, msg):
        self.log_msg(msg)
        self.logout()
        self.stop()

    def __fletch_bows_cycle(self) -> bool:
        # If a previous cycle bailed while the bank was still open, make sure we don't start fletching.
        if self.is_bank_open():
            pag.press("esc")
            self.__wait_until_bank_closed(timeout_seconds=15)
            if self.is_bank_open():
                self.log_msg("Bank did not close in time; aborting cycle.")
                return False

        self.__click_item(self.item_slot_1)
        self.__click_item(self.item_slot_2)
        time.sleep(random.uniform(0.6, 2.0))
        pag.press("space")

        if not self.__wait_until_no_logs():
            self.log_msg("Timed out waiting for logs to be used. Restarting cycle.")
            return False

        if not self.__open_bank_yellow():
            self.log_msg("Could not open bank.")
            if self.is_bank_open():
                pag.press("esc")
                self.__wait_until_bank_closed(timeout_seconds=15)
            return False

        self.__click_item(self.item_slot_2)
        time.sleep(random.uniform(0.6, 1.9))

        if not withdraw_tagged_item_from_bank_precise(self, color=clr.RED, keep_open=True):
            self.log_msg("Could not withdraw red-tagged item from bank.")
            pag.press("esc")
            self.__wait_until_bank_closed(timeout_seconds=15)
            return False

        pag.press("esc")
        self.__wait_until_bank_closed(timeout_seconds=15)
        time.sleep(random.uniform(0.2, 0.5))
        return True

    def __wait_until_no_logs(self, timeout_seconds: int = 90) -> bool:
        log_item_names = [
            "Logs",
            "Oak_logs",
            "Willow_logs",
            "Maple_logs",
            "Teak_logs",
            "Mahogany_logs",
            "Yew_logs",
            "Magic_logs",
            "Redwood_logs",
        ]
        start = time.time()
        while time.time() - start < timeout_seconds:
            has_logs = any(self.get_item_slot(item_name) != -1 for item_name in log_item_names)
            if not has_logs:
                return True
            time.sleep(0.6)
        return False

    def __open_bank_yellow(self, timeout_seconds: int = 20) -> bool:
        start = time.time()
        last_click = 0
        while time.time() - start < timeout_seconds:
            if self.is_bank_open():
                return True

            if time.time() - last_click > 1.5:
                if self.move_mouse_to_bank(clr.YELLOW):
                    time.sleep(0.3)
                    if self.mouseover_text(contains="Bank", color=clr.OFF_WHITE):
                        self.mouse.click()
                        last_click = time.time()
            time.sleep(0.3)
        return False

    def __wait_until_bank_closed(self, timeout_seconds: int = 15) -> None:
        start = time.time()
        while self.is_bank_open() and time.time() - start < timeout_seconds:
            time.sleep(0.2)
        # If it's still open after timeout, try one more close.
        if self.is_bank_open():
            pag.press("esc")
            time.sleep(0.5)

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


