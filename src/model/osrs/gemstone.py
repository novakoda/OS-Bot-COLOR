import time
import random

import utilities.color as clr
import utilities.random_util as rd
from model.osrs.jagex_account_bot import OSRSJagexAccountBot
from utilities.geometry import RuneLiteObject


class OSRSGemstone(OSRSJagexAccountBot):
    def __init__(self):
        bot_title = "Gemstone"
        description = (
            "Tag the gemstone crab with CYAN (alive) or GREEN (spawn location). The bot will attack the crab and click it randomly every 3-6 minutes while alive."
        )
        super().__init__(bot_title=bot_title, description=description, debug=False)
        self.running_time = 1
        self.take_breaks = False

    def create_options(self):
        self.options_builder.add_slider_option("running_time", "How long to run (minutes)?", 1, 500)
        self.options_builder.add_checkbox_option("take_breaks", "Take breaks?", [" "])
        # self.options_builder.add_text_edit_option("skip_slots", "Skip Slots (space seperated)", "0 1 2")
    def save_options(self, options: dict):
        for option in options:
            if option == "running_time":
                self.running_time = options[option]
            elif option == "take_breaks":
                self.take_breaks = options[option] != []
            # elif option == "skip_slots":
            #     self.skip_slots = [int(slot) for slot in options[option].split()] if options[option].strip() else []
            else:
                self.log_msg(f"Unknown option: {option}")
                print("Developer: ensure that the option keys are correct, and that options are being unpacked correctly.")
                self.options_set = False
                return
        self.log_msg(f"Running time: {self.running_time} minutes.")
        self.log_msg(f"Bot will{' ' if self.take_breaks else ' not '}take breaks.")
        # self.log_msg(f"Skipping Slots: {self.skip_slots} when dropping items.")
        self.log_msg("Options set successfully.")
        self.options_set = True

    def main_loop(self):
        self.log_msg("Starting gemstone crab bot...")

        failed_searches = 0
        last_click_time = 0  # Track when we last clicked the crab
        next_random_click_time = 0  # When to do the next random click (3-6 minutes from last click)
        current_state = None  # Track current state: "cyan" (attacking), "green" (moving), or None
        click_count = 0
        max_clicks = random.randint(2, 4)

        # Main loop
        start_time = time.time()
        end_time = self.running_time * 60
        while time.time() - start_time < end_time:
            # 5% chance to take a break
            if rd.random_chance(probability=0.05) and self.take_breaks:
                self.take_break(max_seconds=30, fancy=True)

            current_time = time.time()
            
            # Check if we need to do a random click (every 3-6 minutes while crab is alive)
            if current_state == "cyan":
                # Check if CYAN tag is still visible (crab is still alive)            
                cyan_tags = self.get_all_tagged_in_rect(self.win.game_view, clr.CYAN)
                if cyan_tags and click_count < max_clicks:
                    print(f"click_count: {click_count}, max_clicks: {max_clicks}")
                    cyan_tags_sorted = sorted(cyan_tags, key=RuneLiteObject.distance_from_rect_center)
                    nearest_cyan = cyan_tags_sorted[0]
                    self.mouse.move_to(nearest_cyan.random_point(), mouseSpeed="fast")
                    time.sleep(random.uniform(0.25, 3))
                    self.mouse.click()
                    time.sleep(random.uniform(1, 3))
                    click_count += 1
                    continue
                elif current_time >= next_random_click_time and last_click_time > 0 and click_count >= max_clicks:
                    print("in greater than max clicks loop, resetting click count")
                    click_count = 0
                    max_clicks = random.randint(2, 4)
                    last_click_time = current_time
                    # Set next random click time to 3-6 minutes from now
                    next_random_click_time = current_time + random.uniform(120, 240)  # 2-4 minutes
                    self.log_msg("Random click on crab (2-4 min interval)")
                    continue

            # Search for either CYAN (alive crab) or GREEN (spawn location) tags
            cyan_tags = self.get_all_tagged_in_rect(self.win.game_view, clr.CYAN)
            green_tags = self.get_all_tagged_in_rect(self.win.game_view, clr.LIME_GREEN)

            # Determine new state
            new_state = None
            tags_to_use = None
            
            if cyan_tags:
                new_state = "cyan"
                tags_to_use = cyan_tags
            elif green_tags:
                new_state = "green"
                tags_to_use = green_tags

            # Only click if state has changed (new tag appeared)
            if new_state != current_state and tags_to_use:
                # Sort tags by distance and click the nearest one
                tags_sorted = sorted(tags_to_use, key=RuneLiteObject.distance_from_rect_center)
                nearest_tag = tags_sorted[0]
                
                # Move mouse to the tag and click
                self.mouse.move_to(nearest_tag.random_point(), mouseSpeed="fast")
                time.sleep(0.3)
                self.mouse.click()
                time.sleep(random.randint(6, 10))
                
                # Update state and tracking
                current_state = new_state
                last_click_time = current_time
                
                # If we clicked a CYAN tag (crab is alive), set next random click time
                if new_state == "cyan":
                    next_random_click_time = current_time + random.uniform(12, 30)
                    self.log_msg("Clicked CYAN tag - attacking crab")
                elif new_state == "green":
                    self.log_msg("Clicked GREEN tag - moving to spawn location")
                    # Reset state after clicking green (wait for cyan to reappear)
                    current_state = None
                
                failed_searches = 0
            elif not tags_to_use:
                # No tags found - might be between states
                failed_searches += 1
                if failed_searches % 10 == 0:
                    self.log_msg("Waiting for gemstone crab tags...")
                if failed_searches > 60:
                    # If we've been searching for a whole minute...
                    self.__logout("No gemstone crab tags found. Logging out.")
                # Reset state if we've been waiting too long
                if failed_searches > 30:
                    current_state = None
            
            # Wait before checking again
            time.sleep(1)
            self.update_progress((time.time() - start_time) / end_time)

        self.update_progress(1)
        self.__logout("Finished.")

    def __logout(self, msg):
        self.log_msg(msg)
        self.logout()
        self.stop()




