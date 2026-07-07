import random
import re
import time
from pathlib import Path

import cv2
import numpy as np

import utilities.color as clr
import utilities.ocr as ocr
import utilities.random_util as rd
from model.osrs.jagex_account_bot import OSRSJagexAccountBot
from model.runelite_bot import BotStatus
from utilities.geometry import Rectangle

VALID_POTION_CODES = frozenset({
    "AAA", "MMM", "LLL", "MMA", "MML", "AAM", "ALA", "MLL", "ALL", "MAL",
})

# Unique substrings — checked first; avoids false find_text hits (e.g. MML on Aqualux rows).
POTION_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("ALA", ("aqualux",)),
    ("MML", ("marley", "moonlight")),
    ("MMA", ("mysticmana", "mystic")),
    ("AAA", ("alco", "augmentator", "augment")),
    ("MMM", ("mammoth",)),
    ("LLL", ("liplack", "liquor")),
    ("AAM", ("azure",)),
    ("MLL", ("megalite",)),
    ("ALL", ("antileech", "leech")),
    ("MAL", ("mixalot",)),
)

# (code, display name, OCR search terms)
POTIONS = (
    ("AAA", "Alco-AugmentAtor", ("Alco", "Augment", "AugmentAtor", "augmentator")),
    ("MMM", "Mammoth-Might Mix", ("Mammoth", "Might", "MightMix")),
    ("LLL", "LipLack Liquor", ("LipLack", "Liplack", "Liquor", "lipLack")),
    ("MMA", "Mystic Mana Amalgam", ("MysticMana", "Mystic", "Mana")),
    ("MML", "Marley's MoonLight", ("MarleysMoonLight", "Marley", "MoonLight", "Moonlight")),
    ("AAM", "Azure Aura Mix", ("AzureAura", "Azure", "Aura")),
    ("ALA", "AquaLux Amalgam", ("AquaLux", "Aqualux", "AqualuxAmalgam")),
    ("MLL", "MegaLite Liquid", ("MegaLite", "Megalite", "Liquid")),
    ("ALL", "Anti-Leech Lotion", ("Anti", "Leech", "Lotion", "AntiLeech")),
    ("MAL", "MixALot", ("MixALot", "Mixalot", "Mixa")),
)

HUD_DOT_COLORS = {
    "A": (0, 255, 0),
    "M": (255, 0, 0),
    "L": (0, 0, 255),
}

# BGR reference colors for abbreviation letter classification.
ABBREV_LETTER_REFS = {
    "A": (
        np.array([106.0, 255.0, 0.0]),
        np.array([80.0, 220.0, 20.0]),
    ),
    "M": (
        np.array([255.0, 192.0, 0.0]),
        np.array([230.0, 170.0, 30.0]),
    ),
    "L": (
        np.array([81.0, 41.0, 255.0]),
        np.array([70.0, 55.0, 200.0]),
        np.array([110.0, 65.0, 175.0]),
        np.array([140.0, 80.0, 160.0]),
        np.array([160.0, 90.0, 140.0]),
        np.array([120.0, 100.0, 180.0]),
        np.array([100.0, 85.0, 165.0]),
        np.array([90.0, 75.0, 150.0]),
    ),
}
MAX_CLASSIFY_DISTANCE = 160.0

LETTER_TO_COLOR = {
    "A": clr.MIXOLOGY_AGA,
    "M": clr.MIXOLOGY_MOX,
    "L": clr.MIXOLOGY_LYE,
}

DEBUG_OVERLAY_PATH = Path(__file__).parent.parent.parent.joinpath(
    "images", "temp", "mixology_debug_overlay.png"
)


class OSRSMixology(OSRSJagexAccountBot):
    ORDERS_TOP_OFFSET = 22
    ORDERS_HEIGHT = 88
    ORDERS_SCAN_HEIGHT = 72
    ORDER_ROW_COUNT = 3
    NAME_MAX_X_RATIO = 0.62
    ABBREV_MIN_X_RATIO = 0.29
    NAME_ROW_INSET_Y = 4
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
                while processed < 3 and self.get_nearest_tag(clr.MIXOLOGY_PROCESSOR):
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

    def __order_row_height(self) -> int:
        return self.ORDERS_SCAN_HEIGHT // self.ORDER_ROW_COUNT

    def __order_name_row_rect(self, row_idx: int) -> Rectangle:
        """Left side of an order row — white potion name text only (excludes abbreviations)."""
        orders_rect = self.__mixology_orders_rect()
        row_height = self.__order_row_height()
        name_height = max(row_height - self.NAME_ROW_INSET_Y, 8)
        return Rectangle(
            left=orders_rect.left,
            top=orders_rect.top + row_idx * row_height + self.NAME_ROW_INSET_Y // 2,
            width=int(orders_rect.width * self.NAME_MAX_X_RATIO),
            height=name_height,
        )

    def __extract_row_name_text(self, row_idx: int) -> str:
        row_rect = self.__order_name_row_rect(row_idx)
        for font in (ocr.PLAIN_11, ocr.BOLD_12):
            text = ocr.extract_text(row_rect, font, clr.OFF_WHITE)
            if text:
                return text
        return ""

    @staticmethod
    def __normalize_potion_text(text: str) -> str:
        return re.sub(r"[^A-Za-z]", "", text).lower()

    @staticmethod
    def __code_from_potion_name(name: str) -> str:
        return "".join(char for char in name if char in "AML")

    def __match_keyword_code(self, text: str) -> str | None:
        haystack = self.__normalize_potion_text(text)
        if not haystack:
            return None
        for code, keywords in POTION_KEYWORDS:
            if any(keyword in haystack for keyword in keywords):
                return code
        return None

    def __match_potion_code_from_text(self, text: str) -> str | None:
        if code := self.__match_keyword_code(text):
            return code

        haystack = self.__normalize_potion_text(text)
        if not haystack:
            return None

        best_code = None
        best_len = 0
        for code, name, search_terms in POTIONS:
            for term in (name, *search_terms):
                norm = self.__normalize_potion_text(term)
                if not norm:
                    continue
                if norm in haystack or haystack in norm:
                    if len(norm) > best_len:
                        best_len = len(norm)
                        best_code = code

        if best_code:
            return best_code

        derived = self.__code_from_potion_name(text)
        if derived in VALID_POTION_CODES:
            return derived
        return None

    def __read_row_from_ocr(self, row_idx: int) -> tuple[str | None, bool]:
        """
        Read potion name via extract_text only (no find_text — too many false positives).
        Returns (code, matched_exclusive_keyword).
        """
        text = self.__extract_row_name_text(row_idx)
        if keyword_code := self.__match_keyword_code(text):
            return keyword_code, True
        if code := self.__match_potion_code_from_text(text):
            return code, False
        return None, False

    def __read_row_order(
        self, row_idx: int, letter_blobs: list[tuple[int, int, str]]
    ) -> tuple[str | None, bool]:
        """Prefer colored abbreviations; use name OCR only when color is incomplete."""
        color_code = self.__read_row_from_colors(row_idx, letter_blobs)
        name_code, keyword_match = self.__read_row_from_ocr(row_idx)

        if color_code and name_code:
            if color_code == name_code:
                return color_code, keyword_match
            if keyword_match:
                self.log_msg(
                    f"Row {row_idx + 1}: color read {color_code}, name read {name_code} — using name"
                )
                return name_code, True
            return color_code, False

        if color_code:
            return color_code, False
        if name_code:
            return name_code, True
        return None, False

    def __read_row_from_colors(
        self, row_idx: int, letter_blobs: list[tuple[int, int, str]]
    ) -> str | None:
        row_height = self.__order_row_height()
        row_blobs = [
            (x_pos, letter)
            for y_pos, x_pos, letter in letter_blobs
            if row_idx * row_height <= y_pos < (row_idx + 1) * row_height
        ]
        if len(row_blobs) < 3:
            return None

        row_blobs.sort(key=lambda item: item[0])
        code = "".join(letter for _, letter in row_blobs[-3:])
        if code in VALID_POTION_CODES:
            return code
        return None

    def __expand_blob_to_letters(
        self, img: np.ndarray, x: int, y: int, width: int, height: int, letter: str
    ) -> list[tuple[int, int, str]]:
        """Split a wide blob and re-classify each segment independently."""
        center_y = y + height // 2
        if width <= self.MAX_SINGLE_LETTER_WIDTH:
            char = self.__classify_abbrev_letter(img, x, y, width, height) or letter
            return [(center_y, x + width // 2, char)]

        count = min(3, max(1, round(width / self.APPROX_LETTER_WIDTH)))
        results: list[tuple[int, int, str]] = []
        for index in range(count):
            seg_x = x + int(index * width / count)
            seg_w = max(1, int(width / count))
            char = self.__classify_abbrev_letter(img, seg_x, y, seg_w, height) or letter
            results.append((center_y, seg_x + seg_w // 2, char))
        return results

    def __abbrev_hsv_mask(self, hsv: np.ndarray) -> np.ndarray:
        masks = [
            cv2.inRange(hsv, np.array([35, 40, 50]), np.array([92, 255, 255])),
            cv2.inRange(hsv, np.array([90, 40, 50]), np.array([135, 255, 255])),
            cv2.inRange(hsv, np.array([0, 12, 35]), np.array([18, 255, 255])),
            cv2.inRange(hsv, np.array([160, 12, 35]), np.array([180, 255, 255])),
        ]
        mask = masks[0]
        for channel_mask in masks[1:]:
            mask = cv2.bitwise_or(mask, channel_mask)
        return cv2.dilate(mask, np.ones((2, 2), np.uint8), iterations=1)

    def __classify_abbrev_letter(self, img: np.ndarray, x: int, y: int, width: int, height: int) -> str | None:
        roi = img[y : y + height, x : x + width]
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        sat_channel = hsv[:, :, 1].astype(np.float32)
        val_channel = hsv[:, :, 2].astype(np.float32)
        colored = sat_channel > 6
        if not np.any(colored):
            return None

        # Thin red L sits between two green A's — scan center column before peak-sat heuristic.
        if width <= 9:
            cx = width // 2
            col = hsv[:, max(0, cx - 1) : min(width, cx + 2)]
            for hue, sat, val in zip(
                col[:, :, 0].ravel(),
                col[:, :, 1].ravel(),
                col[:, :, 2].ravel(),
            ):
                if (hue <= 18 or hue >= 160) and sat >= 6 and val >= 25:
                    return "L"

        colored_h = hsv[:, :, 0][colored]
        colored_s = sat_channel[colored]
        colored_v = val_channel[colored]
        peak = int(np.argmax(colored_s))
        hue, sat, val = colored_h[peak], colored_s[peak], colored_v[peak]

        # Skip orange "Potion Orders" title pixels.
        if 8 <= hue <= 28 and sat > 70:
            return None

        if (hue <= 18 or hue >= 160) and sat >= 6 and val >= 25:
            return "L"
        if 35 <= hue <= 88 and sat >= 40:
            return "A"
        if 95 <= hue <= 135 and sat >= 40:
            return "M"

        bright = roi.reshape(-1, 3).astype(np.float32)
        bright = bright[bright.max(axis=1) > 45]
        if len(bright) < 2:
            return None
        mean_bgr = bright.mean(axis=0)

        best_letter = None
        best_distance = float("inf")
        for letter, refs in ABBREV_LETTER_REFS.items():
            for ref in refs:
                distance = float(np.linalg.norm(mean_bgr - ref))
                if distance < best_distance:
                    best_distance = distance
                    best_letter = letter

        if best_distance > MAX_CLASSIFY_DISTANCE:
            return None
        return best_letter

    def __find_hud_letter_blobs(self, rect: Rectangle) -> list[tuple[int, int, str]]:
        """
        Finds colored HUD abbreviation letters within a rectangle.
        Scans three fixed row bands (one per order line) so the paste counter row is ignored.
        Coordinates are relative to rect.
        """
        img = rect.screenshot()
        min_x = int(rect.width * self.ABBREV_MIN_X_RATIO)
        row_height = self.ORDERS_SCAN_HEIGHT // self.ORDER_ROW_COUNT
        letter_blobs: list[tuple[int, int, str]] = []

        for row_idx in range(self.ORDER_ROW_COUNT):
            y_start = row_idx * row_height
            y_end = y_start + row_height
            row_img = img[y_start:y_end]
            row_hsv = cv2.cvtColor(row_img, cv2.COLOR_BGR2HSV)
            mask = self.__abbrev_hsv_mask(row_hsv)

            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for contour in contours:
                x, y, width, height = cv2.boundingRect(contour)
                if width * height < self.MIN_LETTER_AREA:
                    continue
                if height > self.MAX_LETTER_HEIGHT or width > self.MAX_BLOB_WIDTH:
                    continue
                if x < min_x:
                    continue

                letter = self.__classify_abbrev_letter(row_img, x, y, width, height)
                if letter is None:
                    continue
                for cy, cx, char in self.__expand_blob_to_letters(row_img, x, y, width, height, letter):
                    letter_blobs.append((y_start + cy, cx, char))

        return letter_blobs

    def __read_potion_orders(self) -> list[str]:
        """
        Reads the three current potion orders from the mixology HUD.
        Tries colored abbreviation letters first, then white potion name OCR per row.
        """
        orders_rect = self.__mixology_orders_rect()
        letter_blobs = self.__find_hud_letter_blobs(orders_rect)

        if len(letter_blobs) < 9:
            panel_blobs = self.__find_hud_letter_blobs(self.win.info_panel)
            letter_blobs = self.__filter_blobs_to_order_lines(panel_blobs)

        orders: list[str] = []
        used_ocr_fallback = False

        for row_idx in range(self.ORDER_ROW_COUNT):
            code, used_name = self.__read_row_order(row_idx, letter_blobs)
            if not code:
                return []
            if used_name:
                used_ocr_fallback = True
            orders.append(code)

        if used_ocr_fallback:
            self.log_msg(f"Name OCR fallback: {', '.join(orders)}")

        return orders

    def __filter_blobs_to_order_lines(
        self, letter_blobs: list[tuple[int, int, str]]
    ) -> list[tuple[int, int, str]]:
        min_y = self.ORDERS_TOP_OFFSET
        max_y = self.ORDERS_TOP_OFFSET + self.ORDERS_SCAN_HEIGHT
        min_x = int(self.win.info_panel.width * self.ABBREV_MIN_X_RATIO)
        return [
            blob for blob in letter_blobs
            if min_y <= blob[0] <= max_y and blob[1] >= min_x
        ]

    def __parse_orders_from_blobs(self, letter_blobs: list[tuple[int, int, str]]) -> list[str]:
        row_height = self.ORDERS_SCAN_HEIGHT // self.ORDER_ROW_COUNT
        rows: list[list[tuple[int, str]]] = [[] for _ in range(self.ORDER_ROW_COUNT)]

        for y_pos, x_pos, letter in letter_blobs:
            row_idx = min(y_pos // max(row_height, 1), self.ORDER_ROW_COUNT - 1)
            rows[row_idx].append((x_pos, letter))

        orders: list[str] = []
        for row in rows:
            row.sort(key=lambda item: item[0])
            if len(row) < 3:
                continue
            code = "".join(letter for _, letter in row[-3:])
            if code in VALID_POTION_CODES:
                orders.append(code)

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

        scan_x1 = orders_rect.left - game_view.left
        scan_x2 = scan_x1 + orders_rect.width
        scan_y = orders_rect.top - game_view.top + self.ORDERS_SCAN_HEIGHT
        cv2.line(image, (scan_x1, scan_y), (scan_x2, scan_y), (255, 255, 0), 1)

        row_height = self.ORDERS_SCAN_HEIGHT // self.ORDER_ROW_COUNT
        for row_idx in range(1, self.ORDER_ROW_COUNT):
            row_y = orders_rect.top - game_view.top + row_idx * row_height
            cv2.line(image, (scan_x1, row_y), (scan_x2, row_y), (255, 255, 0), 1)

        min_x = orders_rect.left - game_view.left + int(orders_rect.width * self.ABBREV_MIN_X_RATIO)
        cv2.line(
            image,
            (min_x, orders_rect.top - game_view.top),
            (min_x, scan_y),
            (255, 255, 0),
            1,
        )

        detected_codes = self.__read_potion_orders()
        color_codes = self.__parse_orders_from_blobs(letter_blobs)
        ocr_codes = []
        ocr_texts = []
        for i in range(self.ORDER_ROW_COUNT):
            code, _ = self.__read_row_from_ocr(i)
            ocr_codes.append(code or "?")
            ocr_texts.append(self.__extract_row_name_text(i) or "?")

        for row_idx in range(self.ORDER_ROW_COUNT):
            name_rect = self.__order_name_row_rect(row_idx)
            x1 = name_rect.left - game_view.left
            y1 = name_rect.top - game_view.top
            cv2.rectangle(
                image,
                (x1, y1),
                (x1 + name_rect.width, y1 + name_rect.height),
                (255, 128, 0),
                1,
            )

        for y_pos, x_pos, letter in letter_blobs:
            cx = orders_rect.left - game_view.left + x_pos
            cy = orders_rect.top - game_view.top + y_pos
            dot_color = HUD_DOT_COLORS.get(letter, (0, 255, 255))
            cv2.circle(image, (cx, cy), 4, dot_color, -1)
            cv2.putText(
                image,
                letter,
                (cx + 6, cy + 4),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                dot_color,
                1,
                cv2.LINE_AA,
            )

        cv2.putText(
            image,
            (
                f"color: {', '.join(color_codes) or '?'} | "
                f"ocr: {', '.join(ocr_codes)} | "
                f"final: {', '.join(detected_codes) or '?'}"
            ),
            (10, image.shape[0] - 24),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (0, 255, 255),
            1,
            cv2.LINE_AA,
        )
        cv2.putText(
            image,
            f"ocr text: {' | '.join(ocr_texts)}",
            (10, image.shape[0] - 8),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            (0, 255, 255),
            1,
            cv2.LINE_AA,
        )

        DEBUG_OVERLAY_PATH.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(DEBUG_OVERLAY_PATH), image)
        self.log_msg(f"Debug overlay saved: {DEBUG_OVERLAY_PATH}")
        print(f"Debug overlay saved: {DEBUG_OVERLAY_PATH}")

    def __get_nearest_tag_in_region(
        self, color: clr.Color, max_center_y: int = None, min_center_y: int = None
    ):
        tags = self.get_all_tagged_in_rect(self.win.game_view, color)
        if not tags:
            return None

        for tag in tags:
            tag.set_rectangle_reference(self.win.game_view)

        if max_center_y is not None:
            tags = [tag for tag in tags if tag.center().y <= max_center_y]
        if min_center_y is not None:
            tags = [tag for tag in tags if tag.center().y >= min_center_y]
        if not tags:
            return None

        return sorted(tags, key=lambda tag: tag.distance_from_rect_center())[0]

    def __click_lever(self, letter: str) -> bool:
        color = LETTER_TO_COLOR[letter]
        game_view = self.win.game_view
        max_y = game_view.top + int(game_view.height * 0.42)
        tag = self.get_nearest_tag(color)
        if not tag:
            self.log_msg(f"{letter} lever not found - tag it {self.__lever_color_name(letter)}.")
            return False

        self.mouse.move_to(tag.random_point(), mouseSpeed="fast")
        time.sleep(random.uniform(0.3, 0.6))
        self.mouse.click()
        return True

    def __click_station(self, color: clr.Color, label: str, min_y_ratio: float = 0.35) -> bool:
        game_view = self.win.game_view
        min_y = game_view.top + int(game_view.height * min_y_ratio)
        tag = self.__get_nearest_tag_in_region(color, min_center_y=min_y)
        if not tag:
            self.log_msg(f"{label} not found.")
            return False

        self.mouse.move_to(tag.random_point(), mouseSpeed="fast")
        time.sleep(random.uniform(0.3, 0.6))
        self.mouse.click()
        return True

    @staticmethod
    def __lever_color_name(letter: str) -> str:
        return {"A": "GREEN", "M": "BLUE", "L": "RED"}.get(letter, letter)

    def __make_base_potion(self, code: str) -> bool:
        if not self.__click_lever(code[0]):
            return False
        time.sleep(random.uniform(4, 6))

        if not self.__click_lever(code[1]):
            return False
        time.sleep(random.uniform(1.1, 1.9))

        if not self.__click_lever(code[2]):
            return False
        time.sleep(random.uniform(1.1, 2.9))

        if not self.__click_station(clr.MIXOLOGY_VESSEL, "Mixing vessel - tag it CYAN", min_y_ratio=0.25):
            return False
        time.sleep(random.uniform(2.4, 3.9))
        return True

    def __process_potion(self) -> bool:
        if not self.__click_tagged_object(clr.MIXOLOGY_PROCESSOR):
            self.log_msg("Processing machine not found - tag it PINK.")
            return False
        wait = random.uniform(17, 19.5)
        self.log_msg(f"Waiting {wait:.1f}s for processing...")
        time.sleep(wait)
        return True

    def __deposit_to_conveyor(self) -> bool:
        game_view = self.win.game_view
        min_y = game_view.top + int(game_view.height * 0.55)
        tag = self.__get_nearest_tag_in_region(clr.MIXOLOGY_CONVEYOR, min_center_y=min_y)
        if not tag:
            self.log_msg("Conveyor belt not found - tag it YELLOW.")
            return False
        self.mouse.move_to(tag.random_point(), mouseSpeed="slow")
        time.sleep(random.uniform(0.3, 0.6))
        self.mouse.click()
        time.sleep(random.uniform(3.2, 4.5))
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
