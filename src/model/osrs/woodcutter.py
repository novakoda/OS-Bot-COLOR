import time

import utilities.api.item_ids as ids
import utilities.color as clr
import utilities.random_util as rd
from model.osrs.jagex_account_bot import OSRSJagexAccountBot
from model.runelite_bot import BotStatus
from utilities.api.morg_http_client import MorgHTTPSocket
from utilities.api.status_socket import StatusSocket
from utilities.geometry import RuneLiteObject


class OSRSWoodcutter(OSRSJagexAccountBot):
    def __init__(self):
        bot_title = "Woodcutter"
        description = (
            "This bot power-chops wood. Position your character near some trees, tag them, and press Play.\n\nLog Actions:\nDeposit in bank - Requires bank to be tagged yellow\nLight on fire: Requires tinderbox and firemaking level for logs\nDrop: Drops the logs"
        )
        super().__init__(bot_title=bot_title, description=description, debug=False)
        self.running_time = 1
        self.take_breaks = False

    def create_options(self):
        self.options_builder.add_slider_option("running_time", "How long to run (minutes)?", 1, 500)
        self.options_builder.add_checkbox_option("take_breaks", "Take breaks?", [" "])
        self.options_builder.add_dropdown_option("log_action", "When full inventory:", ["Deposit logs in bank", "Light logs on fire", "Drop logs"])

    def save_options(self, options: dict):
        for option in options:
            if option == "running_time":
                self.running_time = options[option]
            elif option == "take_breaks":
                self.take_breaks = options[option] != []
            elif option == "log_action":
                self.log_action = options[option]
            else:
                self.log_msg(f"Unknown option: {option}")
                print("Developer: ensure that the option keys are correct, and that options are being unpacked correctly.")
                self.options_set = False
                return
        self.log_msg(f"Running time: {self.running_time} minutes.")
        self.log_msg(f"Bot will{' ' if self.take_breaks else ' not '}take breaks.")
        self.log_msg(f"{self.log_action} when inventory is full.")
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

        # Main loop
        start_time = time.time()
        end_time = self.running_time * 60
        while time.time() - start_time < end_time:
            # 5% chance to take a break between tree searches
            if rd.random_chance(probability=0.05) and self.take_breaks:
                self.take_break(max_seconds=30, fancy=True)

            # 2% chance to drop logs early
            # if rd.random_chance(probability=0.02):
            #     self.__drop_logs(api_s)

            # If inventory is full, drop logs
            if self.is_inventory_full():
                print("Inventory is full.")
                print(self.log_action)
                if self.log_action == "Deposit logs in bank":
                    print("Depositing logs to bank...")
                    if not self.__deposit_to_bank():
                        continue
                elif self.log_action == "Light logs on fire":
                    if not self.__light_logs_on_fire():
                        continue
                elif self.log_action == "Drop logs":
                    self.drop_all()
                    continue


            # If our mouse isn't hovering over a tree, and we can't find another tree...
            if not self.mouseover_text(contains="Chop", color=clr.OFF_WHITE) and not self.move_mouse_to_nearest_item(clr.PINK):
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
            if not self.mouseover_text(contains="Chop", color=clr.OFF_WHITE):
                continue
            self.mouse.click()
            time.sleep(1)

            # While the player is chopping (or moving), wait
            probability = 0.10
            while not self.idle_message('NOTwoodcutting'):
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
        """
        Locates the nearest tree and moves the mouse to it. This code is used multiple times in this script,
        so it's been abstracted into a function.
        Args:
            next_nearest: If True, will move the mouse to the second nearest tree. If False, will move the mouse to the
                          nearest tree.
            mouseSpeed: The speed at which the mouse will move to the tree. See mouse.py for options.
        Returns:
            True if success, False otherwise.
        """

        bank = self.get_nearest_tag(clr.YELLOW)
        if not bank:
            return False
        self.mouse.move_to(bank.random_point(), mouseSpeed="slow", knotsCount=2)

    def __light_logs_on_fire(self):
        """
        Lights logs on fire.
        Returns:
            True if success, False otherwise.
        """
        # Check if tinderbox in inventory
        tinderbox_slot = self.get_item_slot("Tinderbox")

        if tinderbox_slot != -1:
            self.set_fires(tinderbox_slot)
            time.sleep(1)

    def __deposit_to_bank(self) -> bool:
        """
        Handles finding and interacting with the bank when inventory is full.
        Returns:
            True if banking was successful, False if bank couldn't be found
        """
        failed_searches = 0
        if not self.mouseover_text(contains="Bank", color=clr.OFF_WHITE) and not self.__move_mouse_to_bank():
            failed_searches += 1
            if failed_searches % 10 == 0:
                self.log_msg("Searching for bank...")
            if failed_searches > 60:
                # If we've been searching for a whole minute...
                self.__logout("No tagged banks found. Logging out.")
            time.sleep(1)
            return False

        if not self.mouseover_text(contains="Bank", color=clr.OFF_WHITE):
            return False

        self.mouse.click()
        self.mouse.move_to(self.win.chat.random_point(), mouseSpeed="slow", knotsCount=2)

        while not self.is_bank_open():
            time.sleep(1)

        self.deposit()
        return True
