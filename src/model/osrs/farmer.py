from itertools import count
import time

import utilities.color as clr
import utilities.random_util as rd
from model.osrs.jagex_account_bot import OSRSJagexAccountBot
from model.runelite_bot import BotStatus
from utilities.api.morg_http_client import MorgHTTPSocket
from utilities.api.status_socket import StatusSocket
from utilities.geometry import RuneLiteObject


class OSRSFarmer(OSRSJagexAccountBot):
    def __init__(self):
        bot_title = "Farmer"
        description = (
            "For the Tithe Farm minigame."
        )
        super().__init__(bot_title=bot_title, description=description, debug=False)
        self.running_time = 1
        self.take_breaks = False
        self.seed_slot = 0
        self.water_slot = 0
        self.skip_slots = []

    def create_options(self):
        self.options_builder.add_slider_option("running_time", "How long to run (minutes)?", 1, 500)
        self.options_builder.add_checkbox_option("take_breaks", "Take breaks?", [" "])
        self.options_builder.add_slider_option("seed_slot", "Seed slot in inventory (0-27):", 0, 27)
        self.options_builder.add_slider_option("water_slot", "Watering can slot in inventory (0-27):", 0, 27)

    def save_options(self, options: dict):
        for option in options:
            if option == "running_time":
                self.running_time = options[option]
            elif option == "take_breaks":
                self.take_breaks = options[option] != []
            elif option == "seed_slot":
                self.seed_slot = options[option]
            elif option == "water_slot":
                self.water_slot = options[option]
            else:
                self.log_msg(f"Unknown option: {option}")
                print("Developer: ensure that the option keys are correct, and that options are being unpacked correctly.")
                self.options_set = False
                return
        self.log_msg(f"Running time: {self.running_time} minutes.")
        self.log_msg(f"Bot will{' ' if self.take_breaks else ' not '}take breaks.")
        self.log_msg(f"Seed slot: {self.seed_slot}.")
        self.log_msg(f"Watering can slot: {self.water_slot}.")
        self.log_msg("Options set successfully.")
        self.options_set = True

    def main_loop(self):
        self.log_msg("Selecting inventory...")
        self.mouse.move_to(self.win.cp_tabs[3].random_point())
        self.mouse.click()
        self.used_water = 0

        start_time = time.time()
        end_time = self.running_time * 60
        while time.time() - start_time < end_time:
            if rd.random_chance(probability=0.05) and self.take_breaks:
                self.take_break(max_seconds=30, fancy=True)

            if self.used_water > 95:
                # Refill watering cans if more than 95 waterings are done
                green_tag = self.get_nearest_tag([clr.GREEN, clr.DARK_GREEN])
                if green_tag:
                    self.__refill_water(green_tag)

            # Planting phase
            plant_tag = self.get_nearest_tag([clr.RED, clr.DARK_RED, clr.YELLOW, clr.DARK_YELLOW])
            if plant_tag:
                # Combine all yellow and red tags
                yellow_tags = self.get_all_tagged_in_rect(self.win.game_view, [clr.YELLOW, clr.DARK_YELLOW])
                red_tags = self.get_all_tagged_in_rect(self.win.game_view, [clr.RED, clr.DARK_RED])
                all_tags = yellow_tags + red_tags

                print(f"Found {len(all_tags)} plot tags")

                if all_tags:
                    all_tags_sorted = sorted(all_tags, key=RuneLiteObject.distance_from_rect_center)
                    tagged = all_tags_sorted[0]
                    self.__plant_seed(tagged)
                    continue

            # Watering/Harvesting phase
            pink_tag = self.get_nearest_tag([clr.PINK, clr.DARK_PINK])
            if pink_tag:
                self.__water_plant(pink_tag)
            else:
                # Refill watering cans if no pink tags are found
                green_tag = self.get_nearest_tag([clr.GREEN, clr.DARK_GREEN])
                if green_tag:
                    self.__refill_water(green_tag)

            self.update_progress((time.time() - start_time) / end_time)

        self.update_progress(1)
        self.__logout("Finished.")

    def __plant_seed(self, yellow_tag: RuneLiteObject):
        """Plant seeds in the nearest yellow-tagged plot."""
        self.log_msg("Planting seeds...")
        self.mouse.move_to(self.win.inventory_slots[self.seed_slot].random_point())
        self.mouse.click()
        self.mouse.move_to(yellow_tag.random_point())
        self.mouse.click()
        time.sleep(3)  # Wait for planting animation

        # Wait for pink_tag to appear
        pink_tag = None
        while not pink_tag:
            pink_tag = self.get_nearest_tag([clr.PINK, clr.DARK_PINK])
            if not pink_tag:
                time.sleep(1)  # Wait briefly before checking again
                continue

        self.__water_plant(pink_tag)
        time.sleep(0.3)
        

    def __water_plant(self, pink_tag: RuneLiteObject):
        """Water or harvest the nearest pink-tagged plot."""
        self.log_msg("Watering plant...")
        self.mouse.move_to(pink_tag.random_point())
        self.mouse.click()
        time.sleep(2)  # Wait for watering/harvesting animation
        self.used_water += 1
        print('used water: ', self.used_water)

    def __refill_water(self, green_tag: RuneLiteObject):
        """Refill watering cans at the red-tagged water container."""
        self.log_msg("Refilling watering cans...")
        self.mouse.move_to(self.win.inventory_slots[self.water_slot].random_point())
        self.mouse.click()
        self.mouse.move_to(green_tag.random_point())
        self.mouse.click()
        time.sleep(17)  # Wait for refill animation
        self.used_water = 0
        print('used water: ', self.used_water)

    def __logout(self, msg):
        self.log_msg(msg)
        self.logout()
        self.stop()
