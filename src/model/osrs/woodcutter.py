import time

import utilities.api.item_ids as ids
import utilities.color as clr
import utilities.random_util as rd
from model.osrs.common_interactions import try_hover_target
from model.osrs.common_banking import deposit_and_optionally_return
from model.osrs.common_navigation import SearchRetry, get_opposite_direction
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
        self.bank_minimap_direction = None

    def create_options(self):
        self.options_builder.add_slider_option("running_time", "How long to run (minutes)?", 1, 500)
        self.options_builder.add_checkbox_option("take_breaks", "Take breaks?", [" "])
        self.options_builder.add_dropdown_option("log_action", "When full inventory:", ["Deposit logs in bank", "Light logs on fire", "Drop logs"])
        self.options_builder.add_dropdown_option(
            "bank_minimap_direction", "Bank direction (if off-screen):",
            ["None", "North", "South", "East", "West", "Northeast", "Northwest", "Southeast", "Southwest"]
        )

    def save_options(self, options: dict):
        for option in options:
            if option == "running_time":
                self.running_time = options[option]
            elif option == "take_breaks":
                self.take_breaks = options[option] != []
            elif option == "log_action":
                self.log_action = options[option]
            elif option == "bank_minimap_direction":
                self.bank_minimap_direction = None if options[option] == "None" else options[option].lower()
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
        search_retry = SearchRetry()

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
            hovered_tree = try_hover_target(
                move_mouse=lambda: self.move_mouse_to_nearest_item(clr.PINK),
                is_valid_hover=lambda: self.mouseover_text(contains="Chop", color=clr.OFF_WHITE),
            )
            if not hovered_tree:
                search_retry.fail()
                if search_retry.every(10):
                    self.log_msg("Searching for trees...")
                if search_retry.exceeded(60):
                    # If we've been searching for a whole minute...
                    self.__logout("No tagged trees found. Logging out.")
                time.sleep(1)
                continue
            search_retry.reset()
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

    def __get_opposite_direction(self, direction: str) -> str:
        """
        Returns the opposite direction for minimap navigation.
        Args:
            direction: The original direction (e.g., "north", "south", etc.)
        Returns:
            The opposite direction string, or None if direction is None
        """
        return get_opposite_direction(direction)

    def __deposit_to_bank(self) -> bool:
        """
        Handles finding and interacting with the bank when inventory is full.
        Returns:
            True if banking was successful, False if bank couldn't be found
        """
        if not deposit_and_optionally_return(
            self,
            color=clr.YELLOW,
            minimap_direction=self.bank_minimap_direction,
            return_wait_seconds=2,
        ):
            return False

        # Continue walking until we are back at tagged trees.
        if self.bank_minimap_direction:
            opposite_direction = get_opposite_direction(self.bank_minimap_direction)
            if opposite_direction:
                max_walk_attempts = 10
                walk_attempts = 0
                while walk_attempts < max_walk_attempts:
                    # Check if trees are found
                    if self.move_mouse_to_nearest_item(clr.PINK):
                        # Give the client a moment to update hover text
                        time.sleep(0.5)
                        if self.mouseover_text(contains="Chop", color=clr.OFF_WHITE):
                            self.log_msg("Found trees, returning to woodcutting...")
                            self.mouse.click()
                            time.sleep(1)
                            break
                        else:
                            # Hovered object wasn't a tree, keep searching
                            self.log_msg("Tagged object found but not a tree, continuing search...")

                    # No trees found (or not a valid tree), walk further in the same direction
                    walk_attempts += 1
                    self.log_msg(f"Trees not found, continuing to walk {opposite_direction} ({walk_attempts}/{max_walk_attempts})...")
                    self.walk_to_minimap_location(direction=opposite_direction)
                    time.sleep(10)  # Wait for character to walk
        
        return True
