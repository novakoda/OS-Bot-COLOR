import random
import time

import pyautogui as pag

import utilities.color as clr
import utilities.ocr as ocr
import utilities.random_util as rd
from model.osrs.common_banking import withdraw_tagged_item_from_bank_precise
from model.osrs.jagex_account_bot import OSRSJagexAccountBot


_LOG_ITEM_NAMES = (
    "Logs",
    "Oak_logs",
    "Willow_logs",
    "Maple_logs",
    "Teak_logs",
    "Mahogany_logs",
    "Yew_logs",
    "Magic_logs",
    "Redwood_logs",
)

# Bank object-marker red is rarely exact [255,0,0] in screenshots; combine solid + range for contour detection.
_BANK_LOG_TAG_COLORS = [
    clr.RED,
    clr.DARK_RED,
    clr.Color([150, 0, 0], [255, 100, 100]),
]


class OSRSPlankBuyer(OSRSJagexAccountBot):
    def __init__(self):
        bot_title = "Plank buyer"
        description = (
            "Buys planks from a sawmill operator.\n"
            "Tag the trader CYAN and ensure mouseover shows Buy-plank.\n"
            "Tag the bank YELLOW.\n"
            "Tag logs in the bank RED (bank highlighter; pure red or dark red both work).\n"
            "Tag the walk-back tile GREEN.\n"
            "Deposits with one inventory click (first non-money stack); use empty-slot template off so teak planks still deposit."
        )
        super().__init__(bot_title=bot_title, description=description, debug=False)
        self.running_time = 1
        self.take_breaks = False
        self.money_slot = 0

    def create_options(self):
        self.options_builder.add_slider_option("running_time", "How long to run (minutes)?", 5, 500)
        self.options_builder.add_checkbox_option("take_breaks", "Take breaks?", [" "])
        self.options_builder.add_slider_option("money_slot", "Money slot", 0, 27)

    def save_options(self, options: dict):
        for option in options:
            if option == "running_time":
                self.running_time = options[option]
            elif option == "take_breaks":
                self.take_breaks = options[option] != []
            elif option == "money_slot":
                self.money_slot = int(options[option])
            else:
                self.log_msg(f"Unknown option: {option}")
                print("Developer: ensure that the option keys are correct, and that options are being unpacked correctly.")
                self.options_set = False
                return
        self.log_msg(f"Running time: {self.running_time} minutes.")
        self.log_msg(f"Bot will{' ' if self.take_breaks else ' not '}take breaks.")
        self.log_msg(f"Money (coins) inventory slot to keep when banking: {self.money_slot}.")
        self.log_msg("Options set successfully.")
        self.options_set = True

    def main_loop(self):
        self.log_msg("Selecting inventory...")
        self.mouse.move_to(self.win.cp_tabs[3].random_point())
        self.mouse.click()

        start_time = time.time()
        end_time = self.running_time * 60
        while time.time() - start_time < end_time:
            if rd.random_chance(probability=0.05) and self.take_breaks:
                self.take_break(max_seconds=30, fancy=True)

            self.update_progress((time.time() - start_time) / end_time)

            if not self.__click_trader():
                time.sleep(0.5)
                continue

            if not self.__wait_plank_menu_open():
                continue

            pag.press("space")
            # Wait for the dialogue to close and inventory to update; otherwise __has_logs() can still
            # see logs from before the trade and we wrongly click the trader again instead of banking.
            self.__wait_plank_menu_closed()
            time.sleep(random.uniform(0.15, 0.35))
            if self.__still_has_logs_after_inventory_settles():
                continue

            if not self.deposit_to_bank(
                color=clr.YELLOW,
                skip_slots=[self.money_slot],
                keep_open=True,
                use_empty_slot_template=False,
                single_inventory_click=True,
            ):
                continue

            if not withdraw_tagged_item_from_bank_precise(
                self,
                color=_BANK_LOG_TAG_COLORS,
                keep_open=True,
                max_attempts=10,
                retry_sleep=0.35,
            ):
                self.log_msg("Could not withdraw red-tagged logs from bank.")
                pag.press("esc")
                self.__wait_until_bank_closed()
                continue

            pag.press("esc")
            self.__wait_until_bank_closed()
            time.sleep(random.uniform(0.2, 0.45))

            if not self.move_mouse_to_nearest_item(clr.GREEN, speed="fast"):
                self.log_msg("Green walk tile not found.")
                time.sleep(1)
                continue

            self.mouse.click()
            time.sleep(random.uniform(0.4, 0.9))

            if not self.__wait_until_trader_visible():
                self.log_msg("Timed out waiting for trader after walk.")
                time.sleep(1)
                continue

        self.update_progress(1)
        self.logout("Finished.")

    def __is_plank_buy_menu_open(self) -> bool:
        return bool(
            ocr.find_text(
                ["Howmanydoyouwishtomake"],
                self.win.chat,
                ocr.BOLD_12,
                clr.COOK_BROWN,
            )
        )

    def __has_logs(self) -> bool:
        return any(self.get_item_slot(name) != -1 for name in _LOG_ITEM_NAMES)

    def __wait_plank_menu_closed(self, timeout_seconds: float = 12.0) -> None:
        start = time.time()
        while self.__is_plank_buy_menu_open() and time.time() - start < timeout_seconds:
            time.sleep(0.12)

    def __still_has_logs_after_inventory_settles(self, timeout_seconds: float = 8.0) -> bool:
        """
        Returns True if logs remain after the trade (need another Buy-plank).
        Returns False when logs are gone → go to the bank.
        """
        start = time.time()
        while time.time() - start < timeout_seconds:
            if not self.__has_logs():
                return False
            time.sleep(0.2)
        return self.__has_logs()

    def __click_trader(self) -> bool:
        if not self.move_mouse_to_nearest_item(clr.CYAN, speed="fast"):
            return False
        if not self.mouseover_text(contains="Buy-plank"):
            return False
        self.mouse.click()
        time.sleep(1)
        return True

    def __wait_plank_menu_open(self) -> bool:
        secs = 0
        while not self.__is_plank_buy_menu_open():
            secs += 1
            if secs > 6:
                return False
            time.sleep(1)
        return True

    def __wait_until_trader_visible(self, timeout_seconds: float = 35.0) -> bool:
        """Wait until the cyan-tagged trader is on screen after walking; next loop iteration clicks via __click_trader."""
        start = time.time()
        while time.time() - start < timeout_seconds:
            if self.move_mouse_to_nearest_item(clr.CYAN, speed="fast") and self.mouseover_text(contains="Buy-plank"):
                return True
            time.sleep(0.4)
        return False

    def __wait_until_bank_closed(self, timeout_seconds: int = 15) -> None:
        t0 = time.time()
        while self.is_bank_open() and time.time() - t0 < timeout_seconds:
            time.sleep(0.2)
        if self.is_bank_open():
            pag.press("esc")
            time.sleep(0.5)
