import time

import utilities.api.item_ids as ids
import utilities.color as clr
import utilities.random_util as rd
from model.osrs.jagex_account_bot import OSRSJagexAccountBot
from model.runelite_bot import BotStatus
from utilities.api.morg_http_client import MorgHTTPSocket
from utilities.api.status_socket import StatusSocket
from utilities.geometry import RuneLiteObject


class OSRSRunner(OSRSJagexAccountBot):
    def __init__(self):
        bot_title = "Runner"
        description = (
            "This bot runs the agility course"
        )
        super().__init__(bot_title=bot_title, description=description, debug=False)
        self.running_time = 1
        self.take_breaks = False
        self.skip_slots = []

    def create_options(self):
        self.options_builder.add_slider_option("running_time", "How long to run (minutes)?", 1, 500)
        self.options_builder.add_checkbox_option("take_breaks", "Take breaks?", [" "])

    def save_options(self, options: dict):
        for option in options:
            if option == "running_time":
                self.running_time = options[option]
            elif option == "take_breaks":
                self.take_breaks = options[option] != []
            else:
                self.log_msg(f"Unknown option: {option}")
                print("Developer: ensure that the option keys are correct, and that options are being unpacked correctly.")
                self.options_set = False
                return
        self.log_msg(f"Running time: {self.running_time} minutes.")
        self.log_msg(f"Bot will{' ' if self.take_breaks else ' not '}take breaks.")
        self.log_msg("Options set successfully.")
        self.options_set = True

    def main_loop(self):
        self.logs = 0
        failed_searches = 0
        actions = ["Jump", "Climb", "Take", "Vault", "Cross", "Grab", "Leap", "Cross"]

        # Main loop
        start_time = time.time()
        end_time = self.running_time * 60
        while time.time() - start_time < end_time:
            # 3% chance to take a break between tree searches
            if rd.random_chance(probability=0.03) and self.take_breaks:
                self.take_break(max_seconds=12, fancy=True)

            # If our mouse isn't hovering over a tree, and we can't find another tree...
            print(self.mouseover_text(color=clr.OFF_GREEN))
            print(self.mouseover_text())
            if not self.mouseover_text(contains=actions, color=clr.OFF_WHITE) and not self.move_mouse_to_nearest_item(clr.GREEN):
                failed_searches += 1
                if failed_searches % 10 == 0:
                    self.log_msg("Searching for agility course...")
                if failed_searches > 60:
                    # If we've been searching for a whole minute...
                    self.__logout("No agility course found. Logging out.")
                time.sleep(1)
                continue
            failed_searches = 0  # If code got here, a place was found

            if not self.mouseover_text(contains=actions, color=clr.OFF_WHITE) or self.mouseover_text(contains=["Ladder", "Staircase"], color=clr.OFF_GREEN):
                continue
            self.mouse.click()
            time.sleep(4)

            self.update_progress((time.time() - start_time) / end_time)

        self.update_progress(1)
        self.__logout("Finished.")

    def __logout(self, msg):
        self.log_msg(msg)
        self.logout()
        self.stop()

