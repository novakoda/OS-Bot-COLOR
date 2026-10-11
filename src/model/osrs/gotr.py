import time

import utilities.color as clr
import utilities.imagesearch as imsearch
import utilities.random_util as rd
import utilities.runelite_cv as rcv
from model.osrs.common_interactions import try_hover_target
from model.osrs.common_navigation import SearchRetry
from model.osrs.jagex_account_bot import OSRSJagexAccountBot
from utilities.geometry import Point, RuneLiteObject

REGULAR_ACTIONS = ["Enter", "Craft", "Power", "Place", "Mine", "Work", "Take", "Repair", "Use", "Altar"]
URGENT_ACTIONS = ["Enter", "Deposit", "Repair"]
CLIMB_ACTIONS = ["Climb"]
MOUSEOVER_COLORS = [clr.OFF_WHITE, clr.OFF_CYAN, clr.OFF_YELLOW, clr.OFF_GREEN]
HIGHLIGHT = clr.TAG_CYAN
URGENT = clr.GOTR_URGENT
# Autopilot panel + GOTR 10/10 HUD sit in the top-left of the game view.
HUD_MAX_X = 280
HUD_MAX_Y = 240
STILL_PIXELS = 14


class OSRSGotr(OSRSJagexAccountBot):
    def __init__(self):
        bot_title = "GOTR"
        description = (
            "Plays Guardians of the Rift using the GOTR Autopilot plugin outlines.\n\n"
            "Plugin colours:\n"
            "  Regular highlight = CYAN (Enter, Craft, Power, Place, Mine, Work)\n"
            "  Urgent highlight = #FF5050 (Enter, Deposit)\n"
            "Tag climb rubble PINK (Climb) with entity highlighter.\n\n"
            "If cyan rocks cannot be reached, the bot climbs pink first. "
            "After mining it climbs pink to reach the workbench."
        )
        super().__init__(bot_title=bot_title, description=description, debug=False)
        self.running_time = 60
        self.take_breaks = False
        self._tags_before_click = None

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
        self.log_msg("Selecting inventory...")
        self.mouse.move_to(self.win.cp_tabs[3].random_point())
        self.mouse.click()
        time.sleep(0.4)

        search_retry = SearchRetry()
        start_time = time.time()
        end_time = self.running_time * 60

        while time.time() - start_time < end_time:
            if rd.random_chance(probability=0.03) and self.take_breaks:
                self.take_break(max_seconds=20, fancy=True)

            # Urgent highlight always wins (portal enter, deposit).
            if self._click_tagged(URGENT, URGENT_ACTIONS):
                search_retry.reset()
                self._wait_travel()
                if self._climb_if_tags_still():
                    self.log_msg("Tags did not move, climbing...")
                self.update_progress((time.time() - start_time) / end_time)
                continue

            hovered = self._hover_tagged(HIGHLIGHT, REGULAR_ACTIONS)
            if hovered == "Mine":
                search_retry.reset()
                if not self.active_message("Mining"):
                    self._click_and_remember_tags()
                self._mine_while_cyan()
                self.update_progress((time.time() - start_time) / end_time)
                continue

            if hovered == "Work":
                search_retry.reset()
                self._click_and_remember_tags()
                self.mouse.move_to(self.win.chat.random_point(), mouseSpeed="fast", knotsCount=2)
                self._wait_while_crafting()
                self.update_progress((time.time() - start_time) / end_time)
                continue

            if hovered == "Craft":
                search_retry.reset()
                self._click_and_remember_tags()
                self.mouse.move_to(self.win.chat.random_point(), mouseSpeed="fast", knotsCount=2)
                self._wait_until_cyan_leaves("Craft")
                self.update_progress((time.time() - start_time) / end_time)
                continue

            if hovered:
                search_retry.reset()
                self._click_and_remember_tags()
                self._wait_travel()
                if self._climb_if_tags_still():
                    self.log_msg("Tags did not move, climbing...")
                self.update_progress((time.time() - start_time) / end_time)
                continue

            # Climb only when pink sits between the player and the cyan target.
            if self._climb():
                search_retry.reset()
                self.log_msg("Climbing to reach cyan action...")
                continue

            search_retry.fail()
            if search_retry.every(10):
                self.log_msg("Waiting for GOTR Autopilot highlights...")
            if search_retry.exceeded(180):
                self.__logout("No GOTR highlights found. Logging out.")
            time.sleep(0.8)
            self.update_progress((time.time() - start_time) / end_time)

        self.update_progress(1)
        self.__logout("Finished.")

    def _mine_while_cyan(self):
        """Keep mining until Autopilot's cyan target is no longer the rocks."""
        mine_pos = self._tag_center(HIGHLIGHT)
        missed_starts = 0
        while True:
            if self._nearest_thin_tag(URGENT):
                return
            hovered = self._hover_cyan_destination()
            if hovered != "Mine":
                return
            dest = self._farthest_thin_tag(HIGHLIGHT)
            if mine_pos and dest:
                center = dest.center()
                if abs(center.x - mine_pos[0]) > 70 or abs(center.y - mine_pos[1]) > 70:
                    return
            if self.active_message("Mining"):
                missed_starts = 0
                time.sleep(0.35)
                continue
            self._click_and_remember_tags()
            self.mouse.move_to(self.win.chat.random_point(), mouseSpeed="fast", knotsCount=2)
            started = self._wait_status_start("Mining", start_timeout=6.5)
            if self._nearest_thin_tag(URGENT):
                return
            if self._hover_cyan_destination() != "Mine":
                return
            if started:
                missed_starts = 0
                continue
            missed_starts += 1
            if self._climb_if_tags_still() or (missed_starts >= 2 and self._climb()):
                self.log_msg("Cyan rocks not reachable, climbing...")
                missed_starts = 0

    def _wait_status_start(self, status: str, start_timeout: float) -> bool:
        tstart = time.time()
        while time.time() - tstart < start_timeout:
            if self._nearest_thin_tag(URGENT):
                return False
            if self.active_message(status):
                return True
            time.sleep(0.4)
        return False

    def _hover_has(self, actions: list[str]) -> bool:
        return self.mouseover_text(contains=actions, color=MOUSEOVER_COLORS)

    def _current_action(self, actions: list[str]) -> str | None:
        for action in actions:
            if self.mouseover_text(contains=action, color=MOUSEOVER_COLORS):
                return action
        return None

    def _is_path_line(self, obj: RuneLiteObject) -> bool:
        short = max(min(obj._width, obj._height), 1)
        long = max(obj._width, obj._height)
        return long / short > 6 and short < 36

    def _hud_bounds(self, rect) -> tuple[int, int]:
        width = min(HUD_MAX_X, int(rect.width * 0.36))
        height = min(HUD_MAX_Y, int(rect.height * 0.34))
        return width, height

    def _is_hud_tag(self, obj: RuneLiteObject) -> bool:
        if obj.rect is not self.win.game_view:
            return False
        hud_w, hud_h = self._hud_bounds(obj.rect)
        return obj._center[0] <= hud_w and obj._center[1] <= hud_h

    def _is_inventory_tag(self, obj: RuneLiteObject) -> bool:
        panel = self.win.control_panel
        if not panel:
            return False
        point = obj.center()
        return (
            panel.left <= point.x <= panel.left + panel.width
            and panel.top <= point.y <= panel.top + panel.height
        )

    def _mask_hud(self, isolated, rect):
        if rect is not self.win.game_view:
            return isolated
        hud_w, hud_h = self._hud_bounds(rect)
        masked = isolated.copy()
        masked[0:hud_h, 0:hud_w] = 0
        return masked

    def _thin_tags(self, color: clr.Color, rect=None) -> list[RuneLiteObject]:
        rect = rect or self.win.game_view
        image = rect.screenshot()
        if color is URGENT:
            isolated = clr.isolate_gotr_urgent(image)
        else:
            isolated = clr.isolate_colors(image, color)
        isolated = self._mask_hud(isolated, rect)
        objs = rcv.extract_thin_objects(isolated)
        world_objs = []
        for obj in objs:
            obj.set_rectangle_reference(rect)
            if not self._is_hud_tag(obj) and not self._is_inventory_tag(obj):
                world_objs.append(obj)
        return world_objs

    def _nearest_thin_tag(self, color: clr.Color, next_nearest: bool = False):
        objs = self._thin_tags(color)
        if not objs:
            return None
        compact = [obj for obj in objs if not self._is_path_line(obj)]
        candidates = compact or objs
        candidates = sorted(candidates, key=RuneLiteObject.distance_from_rect_center)
        if next_nearest:
            return candidates[1] if len(candidates) > 1 else None
        return candidates[0]

    def _farthest_thin_tag(self, color: clr.Color):
        objs = self._thin_tags(color)
        if not objs:
            return None
        compact = [obj for obj in objs if not self._is_path_line(obj)]
        candidates = compact or objs
        candidates = sorted(candidates, key=RuneLiteObject.distance_from_rect_center, reverse=True)
        return candidates[0]

    def _hover_cyan_destination(self) -> str | None:
        """
        Always move to the cyan Autopilot target (the far outline, not the path
        at the player's feet) before reading hover text.
        """
        tag = self._farthest_thin_tag(HIGHLIGHT)
        if not tag:
            return None
        self.mouse.move_to(self._tag_aim_point(tag), mouseSpeed="fast")
        time.sleep(0.15)
        return self._current_action(REGULAR_ACTIONS)

    def _tag_aim_point(self, obj: RuneLiteObject) -> Point:
        """
        Click the outlined object. If the blob is a path (or path+object merged),
        aim at the end farthest from the player instead of the path underfoot.
        """
        short = max(min(obj._width, obj._height), 1)
        long = max(obj._width, obj._height)
        huge_or_long = long / short > 2.4 or (obj._width * obj._height > 12000)
        if not huge_or_long:
            return obj.random_point()
        axis = obj._axis
        if axis is None or len(axis) == 0:
            return obj.center()
        player_x = obj.rect.width // 2
        player_y = obj.rect.height // 2
        dist_sq = (axis[:, 0] - player_x) ** 2 + (axis[:, 1] - player_y) ** 2
        x, y = axis[int(dist_sq.argmax())]
        return Point(int(x) + obj.rect.left, int(y) + obj.rect.top)

    def _move_to_thin_tag(self, color: clr.Color, next_nearest: bool = False) -> bool:
        tag = self._nearest_thin_tag(color, next_nearest=next_nearest)
        if not tag:
            return False
        if color is HIGHLIGHT or color is URGENT:
            self.mouse.move_to(self._tag_aim_point(tag), mouseSpeed="fast")
        else:
            self.mouse.move_to(tag.random_point(), mouseSpeed="fast")
        return True

    def _hover_tagged(self, color, actions: list[str]) -> str | None:
        moved = try_hover_target(
            move_mouse=lambda: self._move_to_thin_tag(color),
            is_valid_hover=lambda: self._hover_has(actions),
        )
        if moved:
            return self._current_action(actions)
        if self._move_to_thin_tag(color, next_nearest=True):
            time.sleep(0.15)
            if self._hover_has(actions):
                return self._current_action(actions)
        return None

    def _click_tagged(self, color, actions: list[str]) -> bool:
        if not self._hover_tagged(color, actions):
            return False
        self._click_and_remember_tags()
        return True

    def _tag_center(self, color: clr.Color):
        tag = self._nearest_thin_tag(color)
        if not tag:
            return None
        point = tag.center()
        return (point.x, point.y)

    def _snapshot_tags(self) -> dict:
        return {
            "cyan": self._tag_center(HIGHLIGHT),
            "pink": self._tag_center(clr.PINK),
            "urgent": self._tag_center(URGENT),
        }

    def _same_point(self, before, after) -> bool:
        if before is None or after is None:
            return False
        return abs(before[0] - after[0]) <= STILL_PIXELS and abs(before[1] - after[1]) <= STILL_PIXELS

    def _tags_unmoved(self, before: dict) -> bool:
        after = self._snapshot_tags()
        cyan_still = self._same_point(before.get("cyan"), after.get("cyan"))
        urgent_still = self._same_point(before.get("urgent"), after.get("urgent"))
        return cyan_still or urgent_still

    def _click_and_remember_tags(self):
        self._tags_before_click = self._snapshot_tags()
        self.mouse.click()

    def _climb_nearest_pink(self) -> bool:
        tag = self._nearest_thin_tag(clr.PINK)
        if not tag:
            return False
        self.mouse.move_to(tag.random_point(), mouseSpeed="fast")
        time.sleep(0.12)
        if not self._hover_has(CLIMB_ACTIONS):
            return False
        self.mouse.click()
        time.sleep(rd.fancy_normal_sample(2.4, 3.8))
        self._tags_before_click = None
        return True

    def _climb_if_tags_still(self) -> bool:
        before = getattr(self, "_tags_before_click", None)
        if not before:
            return False
        if not self._tags_unmoved(before):
            return False
        return self._climb_nearest_pink()

    def _pink_is_between_player_and_cyan(self, pink: RuneLiteObject, cyan: RuneLiteObject) -> bool:
        player_x = self.win.game_view.get_center().x
        pink_x = pink.center().x
        cyan_x = cyan.center().x
        if pink_x < player_x and cyan_x < pink_x:
            return True
        if pink_x > player_x and cyan_x > pink_x:
            return True
        return False

    def _climb_tag(self) -> RuneLiteObject | None:
        cyan = self._nearest_thin_tag(HIGHLIGHT)
        if not cyan:
            return None
        pinks = [obj for obj in self._thin_tags(clr.PINK) if not self._is_path_line(obj)]
        between = [pink for pink in pinks if self._pink_is_between_player_and_cyan(pink, cyan)]
        if not between:
            return None
        return sorted(between, key=RuneLiteObject.distance_from_rect_center)[0]

    def _climb(self) -> bool:
        tag = self._climb_tag()
        if not tag:
            return False
        self.mouse.move_to(tag.random_point(), mouseSpeed="fast")
        time.sleep(0.12)
        if not self._hover_has(CLIMB_ACTIONS):
            return False
        self.mouse.click()
        time.sleep(rd.fancy_normal_sample(2.4, 3.8))
        return True

    def _empty_slot_count(self) -> int:
        empty_img = imsearch.BOT_IMAGES.joinpath("ui_templates", "empty_slot.png")
        count = 0
        for slot in self.win.inventory_slots:
            if imsearch.search_img_in_rect(empty_img, slot, confidence=0.05):
                count += 1
        return count

    def _wait_while_crafting(self):
        """
        Workbench crafting has no status text. Wait while empty slots fill.
        Stop when the inventory is full, cyan leaves Work/Craft, or an urgent tag appears.
        """
        last_empty = self._empty_slot_count()
        no_progress = 0
        filling = False
        while True:
            if self._nearest_thin_tag(URGENT):
                return
            empty = self._empty_slot_count()
            if empty == 0:
                return
            hovered = self._hover_cyan_destination()
            if hovered not in (None, "Work", "Craft"):
                return
            if empty < last_empty:
                last_empty = empty
                filling = True
                no_progress = 0
            else:
                no_progress += 1
            stall_limit = 12 if filling else 20
            if no_progress >= stall_limit:
                if self._climb_if_tags_still() or self._climb():
                    self.log_msg("Crafting did not fill inventory, climbing...")
                return
            time.sleep(0.5)

    def _wait_until_cyan_leaves(self, action: str):
        """Wait at an altar (or similar) until cyan is no longer that action or urgent appears."""
        while True:
            if self._nearest_thin_tag(URGENT):
                return
            hovered = self._hover_cyan_destination()
            if hovered != action:
                return
            time.sleep(0.5)

    def _wait_travel(self):
        self.mouse.move_to(self.win.chat.random_point(), mouseSpeed="fast", knotsCount=2)
        time.sleep(rd.fancy_normal_sample(2.2, 3.6))

    def __logout(self, msg):
        self.log_msg(msg)
        self.logout()
        self.stop()
