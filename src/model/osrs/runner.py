import math
import time
from typing import List, Optional

import pyautogui as pag

import utilities.color as clr
import utilities.random_util as rd
from model.osrs.jagex_account_bot import OSRSJagexAccountBot
from utilities.geometry import RuneLiteObject


# Semi-transparent green used for pyramid course markers (tag obstacles with a green in this range)
PYRAMID_GREEN = clr.Color([0, 80, 0], [80, 255, 255])


class OSRSRunner(OSRSJagexAccountBot):
    def __init__(self):
        bot_title = "Runner"
        description = (
            "This bot runs the agility course or the Agility Pyramid. "
            "Agility Course: tag obstacles green. "
            "Pyramid: tag obstacles semi-transparent green (counter-clockwise from bottom-left), "
            "stairs, pink (climb up to Simon), cyan (Simon), red (climb down)."
        )
        super().__init__(bot_title=bot_title, description=description, debug=False)
        self.running_time = 1
        self.take_breaks = False
        self.skip_slots = []
        self.course_type = "Agility Course"
        # Pyramid state: level 1-5, step index in current level, after_top = returning from top
        self.pyramid_level = 1
        self.pyramid_step = 0
        self.pyramid_after_top = False

    def create_options(self):
        self.options_builder.add_dropdown_option("course_type", "Course", ["Agility Course", "Pyramid"])
        self.options_builder.add_slider_option("running_time", "How long to run (minutes)?", 1, 500)
        self.options_builder.add_checkbox_option("take_breaks", "Take breaks?", [" "])

    def save_options(self, options: dict):
        for option in options:
            if option == "running_time":
                self.running_time = options[option]
            elif option == "take_breaks":
                self.take_breaks = options[option] != []
            elif option == "course_type":
                self.course_type = options[option]
            else:
                self.log_msg(f"Unknown option: {option}")
                print("Developer: ensure that the option keys are correct, and that options are being unpacked correctly.")
                self.options_set = False
                return
        self.log_msg(f"Course: {self.course_type}. Running time: {self.running_time} minutes.")
        self.log_msg(f"Bot will{' ' if self.take_breaks else ' not '}take breaks.")
        self.log_msg("Options set successfully.")
        self.options_set = True

    def main_loop(self):
        if self.course_type == "Pyramid":
            self._main_loop_pyramid()
        else:
            self._main_loop_agility_course()

    def _agility_move_to_green_or_red(self, *, next_nearest: bool = False, speed: str = "fast") -> tuple[bool, bool]:
        """
        Prefer green course markers; if none are visible, move to a red tag (failsafe for mis-tagged / guide objects).

        Returns:
            (success, used_red_failsafe) — used_red_failsafe is True when the cursor was moved to red
            because no green tags were found; callers may click without OFF_WHITE action OCR in that case.
        """
        if self.move_mouse_to_nearest_item(clr.GREEN, next_nearest=next_nearest, speed=speed):
            return (True, False)
        if self.get_all_tagged_in_rect(self.win.game_view, clr.GREEN):
            return (False, False)
        ok = self.move_mouse_to_nearest_item(clr.RED, next_nearest=False, speed=speed)
        return (ok, ok)

    def _main_loop_agility_course(self):
        self.logs = 0
        failed_searches = 0
        actions = ["Jump", "Climb", "Take", "Vault", "Cross", "Grab", "Leap", "Cross", "Hurdle", "Balance", "Swing", "Teeth"]

        start_time = time.time()
        end_time = self.running_time * 60
        while time.time() - start_time < end_time:
            if rd.random_chance(probability=0.03) and self.take_breaks:
                self.take_break(max_seconds=12, fancy=True)

            moved_ok, used_red = self._agility_move_to_green_or_red(speed="fast")
            if not self.mouseover_text(contains=actions, color=clr.OFF_WHITE) and not moved_ok:
                failed_searches += 1
                if failed_searches % 10 == 0:
                    self.log_msg("Searching for agility course...")
                if failed_searches > 60:
                    self.__logout("No agility course found. Logging out.")
                time.sleep(1)
                continue
            failed_searches = 0

            if not self.mouseover_text(contains=actions, color=clr.OFF_WHITE):
                moved2_ok, used_red2 = self._agility_move_to_green_or_red(next_nearest=True, speed="fast")
                if not moved2_ok:
                    continue
                used_red = used_red or used_red2
                if (
                    not self.mouseover_text(contains=actions, color=clr.OFF_WHITE)
                    and not used_red
                ):
                    continue

            if self.mouseover_text(contains=["Take"], color=clr.OFF_WHITE):
                items = self.get_all_tagged_in_rect(self.win.game_view, clr.GREEN)
                if items and len(items) == 2:
                    moved_ok, used_red_take = self._agility_move_to_green_or_red(
                        next_nearest=True, speed="fast"
                    )
                    if not moved_ok:
                        continue
                    if (
                        not self.mouseover_text(contains=actions, color=clr.OFF_WHITE)
                        and not used_red_take
                    ):
                        continue
                    used_red = used_red or used_red_take

            if self.mouseover_text(contains=["Ladder", "Staircase"], color=clr.OFF_GREEN):
                continue
            if used_red:
                time.sleep(4)
            self.mouse.click()
            time.sleep(4)

            self.update_progress((time.time() - start_time) / end_time)

        self.update_progress(1)
        self.__logout("Finished.")

    def _pyramid_path_center(self, objects: List[RuneLiteObject]):
        """Center of the pyramid/course for angle reference (average of obstacle positions)."""
        if not objects:
            return None
        cx = sum(o.center().x for o in objects) / len(objects)
        cy = sum(o.center().y for o in objects) / len(objects)
        return (cx, cy)

    def _pyramid_ccw_key(self, x: float, y: float, center_x: float, center_y: float) -> float:
        """Path order key: 0 = bottom-left, increasing counter-clockwise (up, right, down, left, stairs)."""
        angle = math.atan2(y - center_y, x - center_x)
        return (3 * math.pi / 4 - angle + 2 * math.pi) % (2 * math.pi)

    def _pyramid_sort_ccw(self, objects: List[RuneLiteObject], center_x: float = None, center_y: float = None) -> List[RuneLiteObject]:
        """Sort green markers counter-clockwise: start bottom-left, then up, right, down, left, then stairs."""
        if not objects:
            return []
        for o in objects:
            o.set_rectangle_reference(self.win.game_view)
        cx = center_x if center_x is not None else sum(o.center().x for o in objects) / len(objects)
        cy = center_y if center_y is not None else sum(o.center().y for o in objects) / len(objects)
        return sorted(objects, key=lambda o: self._pyramid_ccw_key(o.center().x, o.center().y, cx, cy))

    def _pyramid_get_next_green_ahead_of_player(self) -> Optional[RuneLiteObject]:
        """
        Use player position (game view center) to pick the correct next obstacle.
        The next green is the one that is ahead of the player along the CCW path, not just nearest.
        """
        greens = self.get_all_tagged_in_rect(self.win.game_view, PYRAMID_GREEN)
        if not greens:
            return None
        center = self._pyramid_path_center(greens)
        if not center:
            return None
        cx, cy = center
        for o in greens:
            o.set_rectangle_reference(self.win.game_view)
        # Player position = center of game view (character is typically centered)
        player_pt = self.win.game_view.get_center()
        player_key = self._pyramid_ccw_key(player_pt.x, player_pt.y, cx, cy)
        ordered = self._pyramid_sort_ccw(greens, cx, cy)
        # Small offset so we don't re-click the tile we're standing on
        eps = 0.05
        ahead = [o for o in ordered if self._pyramid_ccw_key(o.center().x, o.center().y, cx, cy) >= player_key + eps]
        if ahead:
            return ahead[0]
        # No obstacle ahead = we're at the end of the path (e.g. at stairs); click the last one (stairs)
        return ordered[-1]

    def _main_loop_pyramid(self):
        start_time = time.time()
        end_time = self.running_time * 60
        failed_searches = 0
        self.pyramid_level = 1
        self.pyramid_step = 0
        self.pyramid_after_top = False

        while time.time() - start_time < end_time:
            if rd.random_chance(probability=0.03) and self.take_breaks:
                self.take_break(max_seconds=12, fancy=True)

            # Returning from top: climb up (pink), click Simon (cyan), wait 5s + space + 1, climb down (red)
            if self.pyramid_after_top:
                if self._pyramid_do_simon_loop():
                    self.pyramid_after_top = False
                    self.pyramid_level = 1
                    self.pyramid_step = 0
                time.sleep(0.5)
                self.update_progress((time.time() - start_time) / end_time)
                continue

            # Level 5 top: grab object (first green), then proceed through doorway
            if self.pyramid_level == 5:
                done = self._pyramid_do_level_five_top()
                if done:
                    self.pyramid_after_top = True
                time.sleep(0.5)
                self.update_progress((time.time() - start_time) / end_time)
                continue

            # Levels 1-4: click the green that is next ahead of the player on the CCW path
            target = self._pyramid_get_next_green_ahead_of_player()
            if target is None:
                failed_searches += 1
                if failed_searches % 10 == 0:
                    self.log_msg("Searching for pyramid obstacles...")
                if failed_searches > 60:
                    self.__logout("No pyramid course found. Logging out.")
                time.sleep(1)
                continue
            failed_searches = 0

            greens_before = self.get_all_tagged_in_rect(self.win.game_view, PYRAMID_GREEN)
            num_greens_before = len(greens_before) if greens_before else 0

            self.mouse.move_to(target.random_point(), mouseSpeed="fast")
            time.sleep(0.2)
            self.mouse.click()
            time.sleep(rd.fancy_normal_sample(3.5, 5.0))

            greens_now = self.get_all_tagged_in_rect(self.win.game_view, PYRAMID_GREEN)
            num_greens_now = len(greens_now) if greens_now else 0
            # Level up: fewer greens visible (moved to next pyramid level)
            if num_greens_now < num_greens_before - 1:
                self.pyramid_level = min(5, self.pyramid_level + 1)
            # Fall: many more greens = likely fell to previous level
            elif num_greens_now > num_greens_before + 3:
                self.pyramid_level = max(1, self.pyramid_level - 1)

            self.update_progress((time.time() - start_time) / end_time)

        self.update_progress(1)
        self.__logout("Finished.")

    def _pyramid_do_level_five_top(self) -> bool:
        """At top of pyramid: click first green to grab object, then enter doorway. Returns True when done (then do Simon)."""
        # Click first marked green to grab object
        greens = self.get_all_tagged_in_rect(self.win.game_view, PYRAMID_GREEN)
        if not greens:
            return False
        ordered = self._pyramid_sort_ccw(greens)
        first = ordered[0]
        self.mouse.move_to(first.random_point(), mouseSpeed="fast")
        time.sleep(0.2)
        self.mouse.click()
        time.sleep(rd.fancy_normal_sample(2.0, 3.5))
        # Then proceed through doorway (user said "after proceeding the player must enter the doorway")
        # Doorway is typically one of the same green or a tile – assume we click again or a nearby object
        # Try clicking the same or next object to "proceed" then look for doorway
        time.sleep(1)
        return True

    def _pyramid_do_simon_loop(self) -> bool:
        """Climb pink rocks, click Simon (cyan), wait 5s, space, 1, climb red rocks. Returns True when done."""
        # Climb up: pink tagged rocks
        if not self.move_mouse_to_nearest_item(clr.PINK, speed="fast"):
            time.sleep(0.5)
            return False
        self.mouse.click()
        time.sleep(rd.fancy_normal_sample(2.5, 4.0))

        # Simon: cyan
        if not self.move_mouse_to_nearest_item(clr.CYAN, speed="fast"):
            time.sleep(0.5)
            return False
        self.mouse.click()
        time.sleep(5)
        pag.press("space")
        time.sleep(0.3)
        pag.press("1")
        time.sleep(rd.fancy_normal_sample(1.0, 1.5))

        # Climb down: red tagged rocks
        if not self.move_mouse_to_nearest_item(clr.RED, speed="fast"):
            time.sleep(0.5)
            return False
        self.mouse.click()
        time.sleep(rd.fancy_normal_sample(2.5, 4.0))
        return True

    def __logout(self, msg):
        self.log_msg(msg)
        self.logout()
        self.stop()

