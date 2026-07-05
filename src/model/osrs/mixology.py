import random
import time
from pathlib import Path

import cv2
import numpy as np

import utilities.color as clr
import utilities.random_util as rd
from model.osrs.jagex_account_bot import OSRSJagexAccountBot
from model.runelite_bot import BotStatus
from utilities.geometry import Rectangle

VALID_POTION_CODES = frozenset({
    "AAA", "MMM", "LLL", "MMA", "MML", "AAM", "ALA", "MLL", "ALL", "MAL",
})

HUD_LETTERS = (
    (clr.MIXOLOGY_HUD_AGA, "A"),
    (clr.MIXOLOGY_HUD_MOX, "M"),
    (clr.MIXOLOGY_HUD_LYE, "L"),
)

LETTER_TO_COLOR = {
    "A": clr.MIXOLOGY_AGA,
    "M": clr.MIXOLOGY_MOX,
    "L": clr.MIXOLOGY_LYE,
}

DEBUG_OVERLAY_PATH = Path(__file__).parent.parent.parent.joinpath(
    "images", "temp", "mixology_debug_overlay.png"
)


class OSRSMixology(OSRSJagexAccountBot):
    ORDERS_TOP_OFFSET = 16
    ORDERS_HEIGHT = 78
    ORDER_ROW_Y_THRESHOLD = 10
    ABBREV_MIN_X_RATIO = 0.35
    MIN_LETTER_AREA = 4
    MAX_LETTER_HEIGHT = 18
    MAX_SINGLE_LETTER_WIDTH = 11
    APPROX_LETTER_WIDTH = 7
    MAX_BLOB_WIDTH = 40

    def __init__(self):
        bot_title = "Mixology"
        description = (
            "Automates the Mastering Mixology minigame.\n\n"
            "Tag levers:\n"
            "  Aga (A) = GREEN (0, 255, 106)\n"
            "  Mox (M) = BLUE (0, 192, 255)\n"
            "  Lye (L) = RED (255, 41, 81)\n"
            "Tag mixing vessel CYAN, processing machine PINK, conveyor belt YELLOW.\n\n"
            "Stand in the lab with the order HUD visible in the top-left.\n"
            "On start, saves a debug overlay to src/images/temp/mixology_debug_overlay.png"
        )
        super().__init__(bot_title=bot_title, description=description, debug=False)
        self.running_time = 60
        self.take_breaks = False

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
        time.sleep(0.5)

        self.__save_mixology_debug_overlay()

        start_time = time.time()
        end_time = self.running_time * 60
        failed_reads = 0

        while time.time() - start_time < end_time:
            if rd.random_chance(probability=0.03) and self.take_breaks:
                self.take_break(max_seconds=30, fancy=True)

            orders = self.__read_potion_orders()
            if len(orders) < 3:
                failed_reads += 1
                if failed_reads == 1:
                    self.__save_mixology_debug_overlay()
                if failed_reads % 10 == 0:
                    self.log_msg("Waiting for mixology order HUD...")
                if failed_reads > 120:
                    self.__logout("Could not read potion orders from HUD.")
                time.sleep(1)
                continue
            failed_reads = 0
            self.log_msg(f"Orders: {', '.join(orders)}")

            for i, code in enumerate(orders, start=1):
                self.log_msg(f"Making base potion {i}/3 ({code})...")
                if not self.__make_base_potion(code):
                    self.log_msg(f"Failed to make base potion {code}, retrying cycle...")
                    break
            else:
                processed = 0
                while processed < 3 and self.get_nearest_tag(clr.PINK):
                    processed += 1
                    self.log_msg(f"Processing potion {processed}/3...")
                    if not self.__process_potion():
                        self.log_msg("Failed to process potion, retrying cycle...")
                        break
                else:
                    self.log_msg("Depositing potions on conveyor belt...")
                    if self.__deposit_to_conveyor():
                        self.update_progress((time.time() - start_time) / end_time)
                        continue

            time.sleep(1)

        self.update_progress(1)
        self.__logout("Finished.")

    def __mixology_orders_rect(self) -> Rectangle:
        panel = self.win.info_panel
        return Rectangle(
            left=panel.left,
            top=panel.top + self.ORDERS_TOP_OFFSET,
            width=panel.width,
            height=self.ORDERS_HEIGHT,
        )

    def __expand_blob_to_letters(
        self, x: int, y: int, width: int, height: int, letter: str
    ) -> list[tuple[int, int, str]]:
        """Split a wide color blob into individual letter positions (e.g. AAA as one blob)."""
        center_y = y + height // 2
        if width <= self.MAX_SINGLE_LETTER_WIDTH:
            return [(center_y, x + width // 2, letter)]

        count = min(3, max(1, round(width / self.APPROX_LETTER_WIDTH)))
        return [
            (center_y, x + int((index + 0.5) * width / count), letter)
            for index in range(count)
        ]

    def __find_hud_letter_blobs(self, rect: Rectangle) -> list[tuple[int, int, str]]:
        """
        Finds colored HUD abbreviation letters within a rectangle.
        Uses direct contour detection instead of tag extraction, which erodes small text away.
        Coordinates are relative to rect.
        """
        img = rect.screenshot()
        min_x = int(rect.width * self.ABBREV_MIN_X_RATIO)
        letter_blobs: list[tuple[int, int, str]] = []

        for color, letter in HUD_LETTERS:
            mask = clr.isolate_colors(img, color)
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for contour in contours:
                x, y, width, height = cv2.boundingRect(contour)
                if width * height < self.MIN_LETTER_AREA:
                    continue
                if height > self.MAX_LETTER_HEIGHT or width > self.MAX_BLOB_WIDTH:
                    continue
                if x < min_x:
                    continue
                letter_blobs.extend(self.__expand_blob_to_letters(x, y, width, height, letter))

        return letter_blobs

    def __read_potion_orders(self) -> list[str]:
        """
        Reads the three current potion orders from the mixology HUD.
        Each order ends with a color-coded abbreviation like (MML): green=A, blue=M, red=L.
        """
        orders_rect = self.__mixology_orders_rect()
        letter_blobs = self.__find_hud_letter_blobs(orders_rect)

        if len(letter_blobs) < 9:
            letter_blobs = self.__find_hud_letter_blobs(self.win.info_panel)

        if len(letter_blobs) < 9:
            return []

        letter_blobs.sort(key=lambda blob: (blob[0], blob[1]))

        rows: list[list[tuple[int, str]]] = []
        current_row: list[tuple[int, str]] = []
        row_y = None

        for y_pos, x_pos, letter in letter_blobs:
            if row_y is None or abs(y_pos - row_y) <= self.ORDER_ROW_Y_THRESHOLD:
                current_row.append((x_pos, letter))
                row_y = y_pos if row_y is None else (row_y + y_pos) // 2
            else:
                if current_row:
                    rows.append(current_row)
                current_row = [(x_pos, letter)]
                row_y = y_pos

        if current_row:
            rows.append(current_row)

        orders: list[str] = []
        for row in rows:
            row.sort(key=lambda item: item[0])
            if len(row) < 3:
                continue
            code = "".join(letter for _, letter in row[-3:])
            if code in VALID_POTION_CODES:
                orders.append(code)
            if len(orders) == 3:
                break

        return orders

    def __save_mixology_debug_overlay(self) -> None:
        """Screenshot the game view with info_panel and orders_rect overlays."""
        game_view = self.win.game_view
        info_panel = self.win.info_panel
        orders_rect = self.__mixology_orders_rect()
        letter_blobs = self.__find_hud_letter_blobs(orders_rect)

        image = np.ascontiguousarray(game_view.screenshot().copy())

        def draw_rect(rect: Rectangle, color_bgr: tuple[int, int, int], label: str) -> None:
            x1 = rect.left - game_view.left
            y1 = rect.top - game_view.top
            x2 = x1 + rect.width
            y2 = y1 + rect.height
            cv2.rectangle(image, (x1, y1), (x2, y2), color_bgr, 2)
            cv2.putText(
                image,
                label,
                (x1, max(y1 - 6, 14)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                color_bgr,
                1,
                cv2.LINE_AA,
            )

        draw_rect(info_panel, (0, 255, 0), "info_panel")
        draw_rect(orders_rect, (255, 0, 0), "orders_rect")

        for y_pos, x_pos, letter in letter_blobs:
            cx = orders_rect.left - game_view.left + x_pos
            cy = orders_rect.top - game_view.top + y_pos
            cv2.circle(image, (cx, cy), 4, (0, 255, 255), -1)
            cv2.putText(
                image,
                letter,
                (cx + 6, cy + 4),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                (0, 255, 255),
                1,
                cv2.LINE_AA,
            )

        cv2.putText(
            image,
            f"letters found: {len(letter_blobs)} (need 9)",
            (10, image.shape[0] - 12),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (0, 255, 255),
            1,
            cv2.LINE_AA,
        )

        DEBUG_OVERLAY_PATH.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(DEBUG_OVERLAY_PATH), image)
        self.log_msg(f"Debug overlay saved: {DEBUG_OVERLAY_PATH}")
        print(f"Debug overlay saved: {DEBUG_OVERLAY_PATH}")

    def __make_base_potion(self, code: str) -> bool:
        colors = [LETTER_TO_COLOR[letter] for letter in code]
        print(colors)
        if not self.__click_tagged_object(colors[0]):
            return False
        time.sleep(random.uniform(4, 6))

        if not self.__click_tagged_object(colors[1]):
            return False
        time.sleep(random.uniform(0.5, 1.2))

        if not self.__click_tagged_object(colors[2]):
            return False
        time.sleep(random.uniform(0.3, 0.6))

        if not self.__click_tagged_object(clr.CYAN):
            self.log_msg("Mixing vessel not found - tag it CYAN.")
            return False
        time.sleep(random.uniform(0.5, 1.0))
        return True

    def __process_potion(self) -> bool:
        if not self.__click_tagged_object(clr.PINK):
            return False
        wait = random.uniform(12, 15)
        self.log_msg(f"Waiting {wait:.1f}s for processing...")
        time.sleep(wait)
        return True

    def __deposit_to_conveyor(self) -> bool:
        if not self.__click_tagged_object(clr.YELLOW, speed="slow"):
            self.log_msg("Conveyor belt not found - tag it YELLOW.")
            return False
        time.sleep(random.uniform(1.5, 2.5))
        return True

    def __click_tagged_object(self, color: clr.Color, speed: str = "fast") -> bool:
        if not self.move_mouse_to_nearest_item(color, speed=speed):
            return False
        time.sleep(random.uniform(0.2, 0.5))
        self.mouse.click()
        return True

    def __logout(self, msg: str):
        self.log_msg(msg)
        self.logout(msg)
        self.set_status(BotStatus.STOPPED)
