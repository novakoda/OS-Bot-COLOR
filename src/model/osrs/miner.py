import time

import utilities.api.item_ids as ids
import utilities.color as clr
import utilities.random_util as rd
from model.osrs.jagex_account_bot import OSRSJagexAccountBot
from model.runelite_bot import BotStatus
from utilities.api.morg_http_client import MorgHTTPSocket
from utilities.api.status_socket import StatusSocket
from utilities.geometry import RuneLiteObject


class OSRSMiner(OSRSJagexAccountBot):
    def __init__(self):
        bot_title = "Miner"
        description = (
            "This bot power-mines ore. Position your character near some trees, tag them, and press Play.\n\nLog Actions:\nDeposit in bank - Requires bank to be tagged yellow\nLight on fire: Requires tinderbox and firemaking level for logs\nDrop: Drops the logs"
        )
        super().__init__(bot_title=bot_title, description=description, debug=False)
        self.running_time = 1
        self.take_breaks = False
        self.skip_slots = []

    def create_options(self):
        self.options_builder.add_slider_option("running_time", "How long to run (minutes)?", 1, 500)
        self.options_builder.add_checkbox_option("take_breaks", "Take breaks?", [" "])
        self.options_builder.add_dropdown_option("ore_action", "When full inventory:", ["Drop ore", "Smelt ore", "Deposit ore to bank"])
        self.options_builder.add_dropdown_option("ore_type", "Ore type:", ["Iron", "Coal", "Gold"])

    def save_options(self, options: dict):
        for option in options:
            if option == "running_time":
                self.running_time = options[option]
            elif option == "take_breaks":
                self.take_breaks = options[option] != []
            elif option == "ore_action":
                self.ore_action = options[option]
            elif option == "ore_type":
                self.ore_type = options[option]
            else:
                self.log_msg(f"Unknown option: {option}")
                print("Developer: ensure that the option keys are correct, and that options are being unpacked correctly.")
                self.options_set = False
                return
        self.log_msg(f"Running time: {self.running_time} minutes.")
        self.log_msg(f"Bot will{' ' if self.take_breaks else ' not '}take breaks.")
        self.log_msg(f"{self.ore_action} when inventory is full.")
        self.log_msg(f"{self.ore_type} will be mined.")
        self.log_msg("Options set successfully.")
        self.options_set = True

    def main_loop(self):
        self.log_msg("Selecting inventory...")
        self.mouse.move_to(self.win.cp_tabs[3].random_point())
        self.mouse.click()

        self.logs = 0
        failed_searches = 0

        # Main loop
        start_time = time.time()
        end_time = self.running_time * 60
        while time.time() - start_time < end_time:
            pick_slot = self.get_item_slot("Rune_pickaxe")
            if self.skip_slots.count(pick_slot) == 0:
                self.skip_slots.append(pick_slot)

            if rd.random_chance(probability=0.05) and self.take_breaks:
                self.take_break(max_seconds=30, fancy=True)

            if self.is_inventory_full():
                print("Inventory is full.")
                print(self.ore_action)
                if self.ore_action == "Deposit ore to bank":
                    print("Depositing ore to bank...")
                    if not self.__deposit_to_bank():
                        continue
                elif self.ore_action == "Smelt ore":
                    if not self.__light_logs_on_fire():
                        continue
                elif self.ore_action == "Drop ore":
                    self.drop_all(skip_slots=self.skip_slots)
                    continue


            # If our mouse isn't hovering over a tree, and we can't find another tree...
            print(self.mouseover_text(color=clr.OFF_GREEN))
            print(self.mouseover_text())
            if not self.mouseover_text(contains=self.ore_type, color=clr.OFF_GREEN) and not self.move_mouse_to_nearest_item(clr.PINK):
                print("no ore found")
                failed_searches += 1
                if failed_searches % 10 == 0:
                    self.log_msg("Searching for trees...")
                if failed_searches > 60:
                    # If we've been searching for a whole minute...
                    self.__logout("No tagged trees found. Logging out.")
                time.sleep(1)
                continue
            failed_searches = 0  # If code got here, a tree was found

            # Click if the mouseover text assures us we're clicking a tree
            if not self.mouseover_text(contains=self.ore_type, color=clr.OFF_GREEN) and not self.active_message("Mining"):
                print('in if loop check')
                continue
            self.mouse.click()
            time.sleep(1)

            # While the player is chopping (or moving), wait
            probability = 0.10
            while not self.idle_message('NOTmining'):
                # Every second there is a chance to move the mouse to the next tree, lessen the chance as time goes on
                if rd.random_chance(probability):
                    self.move_mouse_to_nearest_item(clr.PINK, next_nearest=True)
                    probability /= 2
                time.sleep(1)

            self.update_progress((time.time() - start_time) / end_time)

        self.update_progress(1)
        self.__logout("Finished.")

    def __logout(self, msg):
        self.log_msg(msg)
        self.logout()
        self.stop()

    def __move_mouse_to_bank(self):
        bank = self.get_nearest_tag(clr.YELLOW)
        if not bank:
            return False
        self.mouse.move_to(bank.random_point(), mouseSpeed="slow", knotsCount=2)

    def __climb_ladder(self, dir="up", tag=clr.RED) -> bool:
        print(f"Climbing ladder {dir}...")
        if tag == clr.RED and self.get_all_tagged_in_rect(self.win.game_view, clr.BLUE):
            print("already up")
            return True

        if tag == clr.BLUE and self.get_all_tagged_in_rect(self.win.game_view, clr.RED):
            print("already down")
            return True

        failed_searches = 0
        if not self.mouseover_text(contains="Climb-", color=clr.OFF_WHITE) and not self.move_mouse_to_nearest_item(tag):
            failed_searches += 1
            if failed_searches % 10 == 0:
                self.log_msg("Searching for ladder...")
            if failed_searches > 60:
                # If we've been searching for a whole minute...
                self.__logout("No tagged ladders found. Logging out.")
            time.sleep(1)
            return False

        if not self.mouseover_text( contains=f"Climb-{dir}", color=clr.OFF_WHITE):
            return False

        self.mouse.click()
        self.mouse.move_to(self.win.chat.random_point(), mouseSpeed="slow", knotsCount=2)
        time.sleep(4)
        return True

    def __deposit_to_bank(self) -> bool:
        """
        Handles finding and interacting with the bank when inventory is full.
        Returns:
            True if banking was successful, False if bank couldn't be found
        """
        if not self.__climb_ladder():
            return False
        print("after climb ladder")
        if not self.deposit_to_bank():
            return False

        if not self.__climb_ladder("dow", clr.BLUE):
            return False

        time.sleep(5)
        return True
