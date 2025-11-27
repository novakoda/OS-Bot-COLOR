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
            "This bot power-mines ore. Position your character near some trees, tag them, and press Play.\n\nLog Actions:\nDeposit in bank - Requires bank to be tagged blue\nLight on fire: Requires tinderbox and firemaking level for logs\nDrop: Drops the logs"
        )
        super().__init__(bot_title=bot_title, description=description, debug=False)
        self.running_time = 1
        self.take_breaks = False
        self.skip_slots = [0]
        self.bank_minimap_direction = None  # Optional: direction to walk on minimap if bank is off-screen (e.g., "north", "south", "east", "west")

    def create_options(self):
        self.options_builder.add_slider_option("running_time", "How long to run (minutes)?", 1, 500)
        self.options_builder.add_checkbox_option("take_breaks", "Take breaks?", [" "])
        self.options_builder.add_dropdown_option("ore_action", "When full inventory:", ["Drop ore", "Smelt ore", "Deposit ore to bank"])
        self.options_builder.add_dropdown_option("ore_type", "Ore type:", ["Iron", "Silver","Coal", "Gold"])
        self.options_builder.add_dropdown_option("bank_minimap_direction", "Bank direction (if off-screen):", ["None", "North", "South", "East", "West", "Northeast", "Northwest", "Southeast", "Southwest"])

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
            elif option == "bank_minimap_direction":
                self.bank_minimap_direction = None if options[option] == "None" else options[option].lower()
            else:
                self.log_msg(f"Unknown option: {option}")
                print("Developer: ensure that the option keys are correct, and that options are being unpacked correctly.")
                self.options_set = False
                return
        self.log_msg(f"Running time: {self.running_time} minutes.")
        self.log_msg(f"Bot will{' ' if self.take_breaks else ' not '}take breaks.")
        self.log_msg(f"{self.ore_action} when inventory is full.")
        self.log_msg(f"{self.ore_type} will be mined.")
        if self.bank_minimap_direction:
            self.log_msg(f"Bank minimap direction: {self.bank_minimap_direction}")
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
            if pick_slot == -1:
                pick_slot = self.get_item_slot("Adamant_pickaxe")
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
                        self.log_msg("Failed to deposit to bank. Continuing...")
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
            if not self.mouseover_text(contains=self.ore_type, color=clr.OFF_GREEN) and not self.move_mouse_to_nearest_item(clr.PINK, speed="fast"):
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

    def __get_nearest_bank_filtered(self):
        """
        Helper method to find the nearest bank, filtering out small blue objects (pie timers).
        Pie timers are typically much smaller than banks, so we filter by size.
        """
        all_blue = self.get_all_tagged_in_rect(self.win.game_view, clr.BLUE)
        if not all_blue:
            return None
        
        # Filter out small objects (pie timers are typically < 30x30 pixels)
        # Banks are typically much larger
        MIN_BANK_SIZE = 30  # Minimum width or height for a bank
        banks = [obj for obj in all_blue if obj._width >= MIN_BANK_SIZE or obj._height >= MIN_BANK_SIZE]
        
        if not banks:
            # If no large objects found, try without filter (fallback)
            banks = all_blue
        
        # Sort by distance and get the nearest
        banks_sorted = sorted(banks, key=RuneLiteObject.distance_from_rect_center)
        return banks_sorted[0]

    def find_tagged_object_with_camera_rotation(self, color: clr.Color, max_rotations: int = 4) -> RuneLiteObject:
        """
        Override to filter out small blue objects (pie timers) when searching for banks.
        """
        # If searching for blue (banks), use filtered search
        if color == clr.BLUE:
            # First try to find it on screen with filtering
            obj = self.__get_nearest_bank_filtered()
            if obj:
                return obj
            
            # If not found, try rotating the camera
            rotation_angle = 90  # Rotate 90 degrees each time
            for i in range(max_rotations):
                self.log_msg(f"Rotating camera to search for bank... ({i+1}/{max_rotations})")
                self.move_camera(horizontal=rotation_angle)
                time.sleep(0.5)  # Wait for camera to settle
                
                obj = self.__get_nearest_bank_filtered()
                if obj:
                    return obj
            
            return None
        else:
            # For other colors, use parent class method
            return super().find_tagged_object_with_camera_rotation(color, max_rotations)

    def move_mouse_to_bank(self, use_camera_rotation: bool = True, use_minimap: bool = False, minimap_direction: str = None):
        """
        Override to filter out small blue objects (pie timers) when searching for banks.
        Pie timers are typically much smaller than banks, so we filter by size.
        """
        # First try to find banks on screen, filtering out small objects
        bank = self.__get_nearest_bank_filtered()
        if bank:
            self.mouse.move_to(bank.random_point(), mouseSpeed="slow", knotsCount=2)
            return True
        
        # If no bank found on screen, try camera rotation with filtering
        if use_camera_rotation:
            bank = self.find_tagged_object_with_camera_rotation(clr.BLUE)
            if bank:
                self.mouse.move_to(bank.random_point(), mouseSpeed="slow", knotsCount=2)
                return True
        
        # Try minimap walking if enabled
        if use_minimap and minimap_direction:
            if self.walk_to_minimap_location(minimap_direction):
                # Wait a bit and try to find the bank again with filtering
                time.sleep(2)
                bank = self.__get_nearest_bank_filtered()
                if bank:
                    self.mouse.move_to(bank.random_point(), mouseSpeed="slow", knotsCount=2)
                    return True
        
        return False

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

        if not self.mouseover_text(contains=f"Climb-{dir}", color=clr.OFF_WHITE):
            return False

        self.mouse.click()
        self.mouse.move_to(self.win.chat.random_point(), mouseSpeed="slow", knotsCount=2)
        time.sleep(4)
        return True

    def __get_opposite_direction(self, direction: str) -> str:
        """
        Returns the opposite direction for minimap navigation.
        Args:
            direction: The original direction (e.g., "north", "south", "east", "west", etc.)
        Returns:
            The opposite direction
        """
        direction_map = {
            "north": "south",
            "south": "north",
            "east": "west",
            "west": "east",
            "northeast": "southwest",
            "northwest": "southeast",
            "southeast": "northwest",
            "southwest": "northeast",
        }
        return direction_map.get(direction.lower(), direction)

    def __deposit_to_bank(self) -> bool:
        """
        Handles finding and interacting with the bank when inventory is full.
        Uses camera rotation and optionally minimap to find banks that are off-screen.
        After depositing, walks back to mining area if bank_minimap_direction is set.
        Returns:
            True if banking was successful, False if bank couldn't be found
        """
        # Move mouse away from mining area to avoid blue pie timers interfering with bank search
        self.mouse.move_to(self.win.chat.random_point(), mouseSpeed="fast", knotsCount=1)
        time.sleep(0.5)  # Wait a moment for any pie timers to potentially disappear
        
        # If there's a ladder, climb it first
        if self.get_all_tagged_in_rect(self.win.game_view, clr.RED):
            if not self.__climb_ladder():
                return False
            print("after climb ladder")
            # Move mouse away again after climbing ladder
            self.mouse.move_to(self.win.chat.random_point(), mouseSpeed="fast", knotsCount=1)
            time.sleep(0.3)
        
        # Try to deposit to bank with camera rotation enabled
        # If bank_minimap_direction is set, use minimap walking as a fallback
        use_minimap = self.bank_minimap_direction is not None
        if not self.deposit_to_bank(use_camera_rotation=True, skip_slots=self.skip_slots, use_minimap=use_minimap, minimap_direction=self.bank_minimap_direction):
            return False

        # If there's a ladder, climb back down
        if self.get_all_tagged_in_rect(self.win.game_view, clr.BLUE):
            if not self.__climb_ladder("down", clr.BLUE):
                return False

        # Walk back to mining area if bank_minimap_direction is set
        if self.bank_minimap_direction:
            opposite_direction = self.__get_opposite_direction(self.bank_minimap_direction)
            self.log_msg(f"Walking back to mining area ({opposite_direction})...")
            self.__walk_back_to_mining_area(opposite_direction)
        else:
            time.sleep(2)  # Wait a bit before returning to mining
        
        return True

    def __walk_back_to_mining_area(self, direction: str):
        """
        Walks back to the mining area while rotating camera to search for rocks.
        Continues walking in the same direction if no rocks are found.
        Args:
            direction: The direction to walk (opposite of bank direction)
        """
        max_attempts = 10  # Maximum number of walking attempts
        attempt = 0
        
        while attempt < max_attempts:
            # Start walking in the direction
            self.walk_to_minimap_location(direction)
            time.sleep(1.5)  # Wait a moment for walking to start
            
            # Rotate camera to search for rocks while walking
            rotation_angle = 90
            rocks_found = False
            
            # Check for rocks before rotating
            rocks = self.get_all_tagged_in_rect(self.win.game_view, clr.PINK)
            if rocks:
                self.log_msg("Rocks found! Returning to mining...")
                rocks_found = True
                break
            
            # Rotate camera and check for rocks at each rotation
            for rotation in range(3):  # Try 3 more rotations (total 4 positions)
                self.move_camera(horizontal=rotation_angle)
                time.sleep(0.8)  # Wait for camera to settle and check while walking
                
                # Check if rocks are visible
                rocks = self.get_all_tagged_in_rect(self.win.game_view, clr.PINK)
                if rocks:
                    self.log_msg("Rocks found! Returning to mining...")
                    rocks_found = True
                    break
            
            if rocks_found:
                break
            
            # If no rocks found, continue walking in the same direction
            attempt += 1
            if attempt < max_attempts:
                self.log_msg(f"No rocks found, continuing to walk {direction}... (attempt {attempt + 1}/{max_attempts})")
                # Continue walking - don't wait too long, just keep moving
                time.sleep(0.5)  # Brief pause before next walk attempt
            else:
                self.log_msg("Max attempts reached. Returning to main loop to search for rocks.")
        
        time.sleep(1)  # Final wait after reaching mining area
