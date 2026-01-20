import time

import utilities.api.item_ids as ids
import utilities.color as clr
import utilities.random_util as rd
import pyautogui as pag
import utilities.ocr as ocr
import utilities.imagesearch as imsearch
from model.osrs.jagex_account_bot import OSRSJagexAccountBot
from model.runelite_bot import BotStatus
from utilities.api.morg_http_client import MorgHTTPSocket
from utilities.api.status_socket import StatusSocket
from utilities.geometry import RuneLiteObject


class OSRSFisher(OSRSJagexAccountBot):
    def __init__(self):
        bot_title = "Fisher"
        description = (
            "This bot fishes. Position your character near some fishing spots, tag them, and press Play.\n\nLog Actions:\nDeposit in bank - Requires bank to be tagged blue\nCook and drop: Requires cooking place to be marked green\nDrop: Drops the fish"
        )
        super().__init__(bot_title=bot_title, description=description, debug=False)
        self.running_time = 1
        self.take_breaks = False
        self.skip_slots = []
        self.bank_minimap_direction = None

    def create_options(self):
        self.options_builder.add_slider_option("running_time", "How long to run (minutes)?", 1, 500)
        self.options_builder.add_dropdown_option("fish_type", "What are you fishing?", ["Raw_salmon", "Raw_lobster"])
        self.options_builder.add_checkbox_option("take_breaks", "Take breaks?", [" "])
        self.options_builder.add_dropdown_option("fish_action", "When full inventory:", ["Cook fish", "Drop fish", "Deposit fish in bank", "Cook and deposit"])
        self.options_builder.add_dropdown_option("bank_minimap_direction", "Bank direction (if off-screen):", ["None", "North", "South", "East", "West", "Northeast", "Northwest", "Southeast", "Southwest"])

    def save_options(self, options: dict):
        for option in options:
            if option == "running_time":
                self.running_time = options[option]
            elif option == "fish_type":
                self.fish_type = options[option]
            elif option == "take_breaks":
                self.take_breaks = options[option] != []
            elif option == "fish_action":
                self.fish_action = options[option]
            elif option == "bank_minimap_direction":
                self.bank_minimap_direction = None if options[option] == "None" else options[option].lower()
            else:
                self.log_msg(f"Unknown option: {option}")
                print("Developer: ensure that the option keys are correct, and that options are being unpacked correctly.")
                self.options_set = False
                return
        self.log_msg(f"Running time: {self.running_time} minutes.")
        self.log_msg(f"Fishing type: {self.fish_type}.")
        self.log_msg(f"Bot will{' ' if self.take_breaks else ' not '}take breaks.")
        self.log_msg(f"{self.fish_action} when inventory is full.")
        self.log_msg("Options set successfully.")
        self.options_set = True

    def main_loop(self):
        self.log_msg("Selecting inventory...")
        self.mouse.move_to(self.win.cp_tabs[3].random_point())
        self.mouse.click()

        self.logs = 0
        failed_searches = 0

        # Set skip slots based on fish type
        if self.fish_type == "Raw_salmon":
            feather_slot = self.get_item_slot("Feather")
            if feather_slot != -1 and self.skip_slots.count(feather_slot) == 0:
                self.skip_slots.append(feather_slot)

            rod_slot = self.get_item_slot("Fly_fishing_rod")
            if rod_slot != -1  and self.skip_slots.count(rod_slot) == 0:
                self.skip_slots.append(rod_slot)
        elif self.fish_type == "Raw_lobster":
            pot_slot = self.get_item_slot("Lobster_pot")
            if pot_slot != -1 and self.skip_slots.count(pot_slot) == 0:
                self.skip_slots.append(pot_slot)

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

            if self.is_inventory_full():
                print('inventory is full')
                if self.fish_action == "Deposit fish in bank":
                    if not self.__deposit_to_bank():
                        continue
                elif self.fish_action == "Cook fish":
                    if not self.__cook_fish():
                        continue
                    self.log_msg("Dropping cooked fish...")
                    self.drop_all(skip_slots=self.skip_slots)
                elif self.fish_action == "Cook and deposit":
                    if not self.__cook_and_deposit():
                        continue
                elif self.fish_action == "Drop fish":
                    self.log_msg("Dropping fish...")
                    self.drop_all(skip_slots=self.skip_slots)
                    continue

            # Determine fishing action text and item name based on fish type
            action_text = "Cage" if self.fish_type == "Raw_lobster" else "Lure"
            item_name = self.fish_type

            # If our mouse isn't hovering over a fishing spot, and we can't find another spot...
            if not self.mouseover_text(contains=action_text, color=clr.OFF_WHITE) and not self.move_mouse_to_nearest_item(item_name):
                failed_searches += 1
                if failed_searches > 5:
                    # Try to find and click red tag as fallback
                    red_tag = self.get_nearest_tag(clr.RED)
                    if red_tag:
                        self.log_msg("Using red tag fallback to find fishing spot...")
                        self.mouse.move_to(red_tag.random_point(), mouseSpeed="fast")
                        time.sleep(0.5)
                        self.mouse.click()
                        time.sleep(1)
                        failed_searches = 0  # Reset counter after clicking red tag
                        continue
                if failed_searches % 10 == 0:
                    self.log_msg("Searching for fishing spots...")
                if failed_searches > 60:
                    # If we've been searching for a whole minute...
                    self.__logout("No fishing spots found. Logging out.")
                time.sleep(1)
                continue
            failed_searches = 0  # If code got here, a fishing spot was found

            # Click if the mouseover text assures us we're clicking a fishing spot
            if not self.mouseover_text(contains=action_text, color=clr.OFF_WHITE):
                continue
            self.mouse.click()
            time.sleep(1)

            # While the player is fishing (or moving), wait
            probability = 0.10
            while not self.idle_message('NOTfishing') and self.active_message('Fishing'):
                # Every second there is a chance to move the mouse to the next fishing spot, lessen the chance as time goes on
                if rd.random_chance(probability):
                    self.move_mouse_to_nearest_item(item_name, next_nearest=True)
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

    def __move_mouse_to_fireplace(self):
        """
        Locates the nearest cooking location and moves the mouse to it.
        Returns:
            True if success, False otherwise.
        """

        fire = self.get_nearest_tag(clr.GREEN)
        if not fire:
            return False
        self.mouse.move_to(fire.random_point(), mouseSpeed="slow", knotsCount=2)
        return True

    def __get_opposite_direction(self, direction: str) -> str:
        """
        Returns the opposite direction for minimap navigation.
        Args:
            direction: The original direction (e.g., "north", "south", etc.)
        Returns:
            The opposite direction string, or None if direction is None
        """
        if not direction:
            return None
        
        opposite_map = {
            "north": "south",
            "south": "north",
            "east": "west",
            "west": "east",
            "northeast": "southwest",
            "northwest": "southeast",
            "southeast": "northwest",
            "southwest": "northeast",
        }
        
        return opposite_map.get(direction.lower())

    def __cook_fish(self):
        """
        Cooks fish at the cooking location.
        Returns:
            True if success, False otherwise.
        """
        if self.active_message("Cooking"):
            return False

        failed_searches = 0
        if not self.mouseover_text(contains="Cook", color=clr.OFF_WHITE) and not self.__move_mouse_to_fireplace():
            failed_searches += 1
            if failed_searches % 10 == 0:
                self.log_msg("Searching for cooking location...")
            if failed_searches > 60:
                # If we've been searching for a whole minute...
                self.__logout("No tagged cooking locations found. Logging out.")
            time.sleep(1)
            return False

        if not self.mouseover_text(contains="Cook", color=clr.OFF_WHITE):
            return False
        self.mouse.click()

        secs = 0
        while not self.is_cook_menu_open():
            secs += 1
            if secs > 29:
                # If we've been searching for 30 seconds...
                return True
            time.sleep(1)

        pag.press("space")
        time.sleep(3)
        if not self.active_message("Cooking"):
                return True

        while not self.idle_message('NOTcooking'):
                return False

        self.__cook_fish()
        return True

    def __cook_and_deposit(self) -> bool:
        """
        Cooks fish at yellow tagged location, drops burnt fish, deposits to blue bank,
        then returns to fishing location using opposite bank_minimap_direction.
        Returns:
            True if successful, False otherwise.
        """
        # Cook fish at yellow tagged location
        if not self.__cook_fish():
            return False
        
        # Wait for cooking to complete
        while self.active_message("Cooking"):
            time.sleep(1)
        
        # Drop all burnt fish (Burnt_lobster for lobsters, Burnt_salmon for salmon)
        burnt_item = "Burnt_lobster" if self.fish_type == "Raw_lobster" else "Burnt_salmon"
        burnt_slots = []
        
        # Find all slots containing burnt items
        img = imsearch.BOT_IMAGES.joinpath("items", f"{burnt_item}.png")
        for i, slot in enumerate(self.win.inventory_slots):
            if imsearch.search_img_in_rect(img, slot, confidence=0.2):
                burnt_slots.append(i)
        
        # Drop all burnt items
        if burnt_slots:
            self.log_msg(f"Dropping {len(burnt_slots)} {burnt_item}(s)...")
            pag.keyDown("shift")
            for slot in burnt_slots:
                self.click_inventory_slot(slot, wait=0.1)
            pag.keyUp("shift")
            time.sleep(0.5)
        
        # Deposit to bank (blue tag)
        if not self.deposit_to_bank(color=clr.BLUE, skip_slots=self.skip_slots, minimap_direction=self.bank_minimap_direction):
            return False
        
        # Return to fishing location using opposite direction
        if self.bank_minimap_direction:
            opposite_direction = self.__get_opposite_direction(self.bank_minimap_direction)
            if opposite_direction:
                self.log_msg(f"Returning to fishing location ({opposite_direction})...")
                self.walk_to_minimap_location(direction=opposite_direction)
                time.sleep(2)  # Wait for character to walk back
        
        return True

    def __deposit_to_bank(self) -> bool:
        """
        Handles finding and interacting with the bank when inventory is full.
        Uses yellow tag for bank (for backward compatibility with existing "Deposit fish in bank" action).
        Returns:
            True if banking was successful, False if bank couldn't be found
        """
        return self.deposit_to_bank(color=clr.YELLOW, minimap_direction=self.bank_minimap_direction)
