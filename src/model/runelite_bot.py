"""
The RuneLiteBot class contains properties and functions that are common across all RuneLite-based clients. This class
can be inherited by additional abstract classes representing all bots for a specific game (E.g., OSNRBot, AloraBot, etc.).

To determine Thresholds for finding contours: https://pinetools.com/threshold-image

For converting RGB to HSV:
    https://stackoverflow.com/questions/10948589/choosing-the-correct-upper-and-lower-hsv-boundaries-for-color-detection-withcv/48367205#48367205

Item ID Database:
    https://www.runelocus.com/tools/osrs-item-id-list/
"""
import time
from abc import ABCMeta
from typing import List, Union

import pyautogui as pag
import pytweening
from deprecated import deprecated

import utilities.color as clr
import utilities.debug as debug
import utilities.imagesearch as imsearch
import utilities.ocr as ocr
import utilities.runelite_cv as rcv
from model.bot import Bot, BotStatus
from utilities.geometry import Point, Rectangle, RuneLiteObject
from utilities.window import Window


class RuneLiteWindow(Window):
    current_action: Rectangle = None  # https://i.imgur.com/fKXuIyO.png
    hp_bar: Rectangle = None  # https://i.imgur.com/2lCovGV.png
    prayer_bar: Rectangle = None

    def __init__(self, window_title: str) -> None:
        """
        RuneLiteWindow is an extensions of the Window class, which allows for locating and interacting with key
        UI elements on screen.
        """
        super().__init__(window_title, padding_top=26, padding_left=0)

    # Override
    def initialize(self) -> bool:
        """
        Overrirde of Window.initialize(). This function is called when the bot is started.
        """
        if not super().initialize():
            return False
        self.__locate_hp_prayer_bars()
        self.current_action = Rectangle(
            left=10 + self.game_view.left,
            top=25 + self.game_view.top,
            width=128,
            height=20,
        )
        return True

    def __locate_hp_prayer_bars(self) -> None:
        """
        Creates Rectangles for the HP and Prayer bars on either side of the control panel, storing it in the
        class property.
        """
        bar_w, bar_h = 18, 250  # dimensions of the bars
        self.hp_bar = Rectangle(
            left=self.control_panel.left + 7,
            top=self.control_panel.top + 42,
            width=bar_w,
            height=bar_h,
        )
        self.prayer_bar = Rectangle(
            left=self.control_panel.left + 217,
            top=self.control_panel.top + 42,
            width=bar_w,
            height=bar_h,
        )

    # Override
    def resize(self, width: int = 773, height: int = 534) -> None:
        """
        Resizes the client window. Default size is 773x534 (minsize of fixed layout).
        Args:
            width: The width to resize the window to.
            height: The height to resize the window to.
        """
        if client := self.window:
            client.size = (width, height)


class RuneLiteBot(Bot, metaclass=ABCMeta):
    win: RuneLiteWindow = None

    def __init__(self, game_title, bot_title, description, window: Window = RuneLiteWindow("RuneLite")) -> None:
        super().__init__(game_title, bot_title, description, window)

    # --- OCR Functions ---
    @deprecated(reason="This is a slow way of checking if you are in combat. Consider using an API function instead.")
    def is_in_combat(self) -> bool:
        """
        Returns whether the player is in combat. This is achieved by checking if text exists in the RuneLite opponent info
        section in the game view, and if that text indicates an NPC is out of HP.
        """
        if ocr.extract_text(self.win.current_action, ocr.PLAIN_12, clr.WHITE):
            return True

    def is_player_doing_action(self, action: str):
        """
        Returns whether the player character is doing a given action. This works by checking the text in the current action
        region of the game view.
        Args:
            action: The action to check for (E.g., "Woodcutting" - case sensitive).
        Returns:
            True if the player is doing the given action, False otherwise.
        """
        return ocr.find_text(action, self.win.current_action, ocr.PLAIN_12, clr.GREEN)

    def pick_up_loot(self, items: Union[str, List[str]], supress_warning=True) -> bool:
        """
        Attempts to pick up a single purple loot item off the ground. It is your responsibility to ensure you have
        enough inventory space to pick up the item. The item closest to the game view center is picked up first.
        Args:
            item: The name(s) of the item(s) to pick up (E.g. -> "Coins", or "coins, bones", or ["Coins", "Dragon bones"]).
        Returns:
            True if the item was clicked, False otherwise.
        """
        # Capitalize each item name
        if isinstance(items, list):
            for i, item in enumerate(items):
                item = item.capitalize()
                items[i] = item
        else:
            items = self.capitalize_loot_list(items, to_list=True)
        # Locate Ground Items text
        if item_text := ocr.find_text(items, self.win.game_view, ocr.PLAIN_11, clr.PURPLE):
            for item in item_text:
                item.set_rectangle_reference(self.win.game_view)
            sorted_by_closest = sorted(item_text, key=Rectangle.distance_from_center)
            self.mouse.move_to(sorted_by_closest[0].get_center())
            for _ in range(5):
                if self.mouseover_text(contains=["Take"] + items, color=[clr.OFF_WHITE, clr.OFF_ORANGE]):
                    break
                self.mouse.move_rel(0, 3, 1, mouseSpeed="fastest")
            self.mouse.right_click()
            # search the right-click menu
            if take_text := ocr.find_text(
                items,
                self.win.game_view,
                ocr.BOLD_12,
                [clr.WHITE, clr.PURPLE, clr.ORANGE],
            ):
                self.mouse.move_to(take_text[0].random_point(), mouseSpeed="medium")
                self.mouse.click()
                return True
            else:
                self.log_msg(f"Could not find 'Take {items}' in right-click menu.")
                return False
        elif not supress_warning:
            self.log_msg(f"Could not find {items} on the ground.")
            return False

    def capitalize_loot_list(self, loot: str, to_list: bool):
        """
        Takes a comma-separated string of loot items and capitalizes each item.
        Args:
            loot_list: A comma-separated string of loot items.
            to_list: Whether to return a list of capitalized loot items (or keep it as a string).
        Returns:
            A list of capitalized loot items.
        """
        if not loot:
            return ""
        phrases = loot.split(",")
        capitalized_phrases = []
        for phrase in phrases:
            stripped_phrase = phrase.strip()
            capitalized_phrase = stripped_phrase.capitalize()
            capitalized_phrases.append(capitalized_phrase)
        return capitalized_phrases if to_list else ", ".join(capitalized_phrases)

    # --- NPC/Object Detection ---
    def get_nearest_tagged_NPC(self, include_in_combat: bool = False) -> RuneLiteObject:
        # sourcery skip: use-next
        """
        Locates the nearest tagged NPC, optionally including those in combat.
        Args:
            include_in_combat: Whether to include NPCs that are already in combat.
        Returns:
            A RuneLiteObject object or None if no tagged NPCs are found.
        """
        game_view = self.win.game_view
        img_game_view = game_view.screenshot()
        # Isolate colors in image
        img_npcs = clr.isolate_colors(img_game_view, clr.CYAN)
        img_fighting_entities = clr.isolate_colors(img_game_view, [clr.GREEN, clr.RED])
        # Locate potential NPCs in image by determining contours
        objs = rcv.extract_objects(img_npcs)
        if not objs:
            print("No tagged NPCs found.")
            return None
        for obj in objs:
            obj.set_rectangle_reference(self.win.game_view)
        # Sort shapes by distance from player
        objs = sorted(objs, key=RuneLiteObject.distance_from_rect_center)
        if include_in_combat:
            return objs[0]
        for obj in objs:
            if not rcv.is_point_obstructed(obj._center, img_fighting_entities):
                return obj
        return None

    def get_all_tagged_in_rect(self, rect: Rectangle, color: clr.Color) -> List[RuneLiteObject]:
        """
        Finds all contours on screen of a particular color and returns a list of Shapes.
        Args:
            rect: A reference to the Rectangle that this shape belongs in (E.g., Bot.win.control_panel).
            color: The clr.Color to search for.
        Returns:
            A list of RuneLiteObjects or empty list if none found.
        """
        img_rect = rect.screenshot()
        isolated_colors = clr.isolate_colors(img_rect, color)
        objs = rcv.extract_objects(isolated_colors)
        for obj in objs:
            obj.set_rectangle_reference(rect)
        return objs

    def get_img_in_rect(self, rect: Rectangle, item: str) -> List[RuneLiteObject]:
        """
        Finds all contours on screen of a particular color and returns a list of Shapes.
        Args:
            rect: A reference to the Rectangle that this shape belongs in (E.g., Bot.win.control_panel).
            color: The clr.Color to search for.
        Returns:
            A list of RuneLiteObjects or empty list if none found.
        """
        img = imsearch.BOT_IMAGES.joinpath("items", f"{item}.png")
        return imsearch.search_img_in_rect(img, rect, confidence=0.1)

    def get_all_img_in_rect(self, rect: Rectangle, item: str) -> List[RuneLiteObject]:
        """
        Finds all contours on screen of a particular color and returns a list of Shapes.
        Args:
            rect: A reference to the Rectangle that this shape belongs in (E.g., Bot.win.control_panel).
            color: The clr.Color to search for.
        Returns:
            A list of RuneLiteObjects or empty list if none found.
        """
        img = imsearch.BOT_IMAGES.joinpath("items", f"{item}.png")
        return imsearch.search_all_img_in_rect(img, rect, confidence=0.1)

    def get_nearest_tag(self, color: clr.Color) -> RuneLiteObject:
        """
        Finds the nearest outlined object of a particular color within the game view and returns it as a RuneLiteObject.
        Args:
            color: The clr.Color to search for.
        Returns:
            The nearest outline to the character as a RuneLiteObject, or None if none found.
        """
        if shapes := self.get_all_tagged_in_rect(self.win.game_view, color):
            shapes_sorted = sorted(shapes, key=RuneLiteObject.distance_from_rect_center)
            return shapes_sorted[0]
        else:
            return None

    def is_inventory_full(self) -> bool:
        """
        Checks if the inventory is full by searching for empty slots.
        Returns:
            True if inventory is full (28/28 slots occupied), False otherwise.
        """
        empty_img = imsearch.BOT_IMAGES.joinpath("ui_templates", "empty_slot.png")
        empty_slots = 0

        # Check each inventory slot
        for slot in self.win.inventory_slots:
            if imsearch.search_img_in_rect(empty_img, slot, confidence=0.05):
                empty_slots += 1

        return empty_slots == 0

    def move_mouse_to_nearest_item(self, search_item: Union[str, clr.Color], next_nearest=False, speed="slow"):
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
        items = (self.get_all_tagged_in_rect(self.win.game_view, search_item)
            if isinstance(search_item, clr.Color)
            else self.get_all_img_in_rect(self.win.game_view, search_item))

        if not items:
            return False

        # Set rectangle reference for each item
        for item in items:
            item.set_rectangle_reference(self.win.game_view)

        # If we are looking for the next nearest tree, we need to make sure trees has at least 2 elements
        if next_nearest and len(items) < 2:
            return False

        items = sorted(items, key=RuneLiteObject.distance_from_rect_center)
        item = items[1] if next_nearest else items[0]

        if next_nearest:
            self.mouse.move_to(item.random_point(), mouseSpeed=speed, knotsCount=2)
        else:
            self.mouse.move_to(item.random_point(), mouseSpeed=speed)
        return True

    def move_mouse_to_bank(self, use_camera_rotation: bool = True, use_minimap: bool = False, minimap_direction: str = None):
        """
        Locates the nearest bank and moves the mouse to it. This code is used multiple times in this script,
        so it's been abstracted into a function.
        Args:
            use_camera_rotation: Whether to rotate camera to search for the bank if not found on screen.
            use_minimap: Whether to use minimap walking if bank still not found.
            minimap_direction: Direction to walk on minimap if use_minimap is True (e.g., "north", "south", "east", "west").
        Returns:
            True if success, False otherwise.
        """
        return self.navigate_to_tagged_object(clr.YELLOW, use_camera_rotation, use_minimap, minimap_direction)

    def find_tagged_object_with_camera_rotation(self, color: clr.Color, max_rotations: int = 4) -> RuneLiteObject:
        """
        Searches for a tagged object by rotating the camera if not found on screen.
        Args:
            color: The color to search for.
            max_rotations: Maximum number of 90-degree rotations to try.
        Returns:
            A RuneLiteObject if found, None otherwise.
        """
        # First try to find it on screen
        obj = self.get_nearest_tag(color)
        if obj:
            return obj
        
        # If not found, try rotating the camera
        rotation_angle = 90  # Rotate 90 degrees each time
        for i in range(max_rotations):
            self.log_msg(f"Rotating camera to search for tagged object... ({i+1}/{max_rotations})")
            self.move_camera(horizontal=rotation_angle)
            time.sleep(0.5)  # Wait for camera to settle
            
            obj = self.get_nearest_tag(color)
            if obj:
                return obj
        
        return None

    def walk_to_minimap_location(self, direction: str = "north", distance: int = 50) -> bool:
        """
        Walks to a location by clicking on the minimap in a specific direction.
        The compass is set to north first to ensure the minimap is properly oriented.
        Args:
            direction: Direction to walk ("north", "south", "east", "west", "northeast", "northwest", "southeast", "southwest").
            distance: Distance in pixels from center of minimap to click (default 50).
        Returns:
            True if successful, False otherwise.
        """
        if not self.win.minimap:
            self.log_msg("Minimap not found. Cannot walk.")
            return False
        
        # Set compass to north first so minimap is properly oriented
        self.set_compass_north()
        time.sleep(0.3)  # Wait for compass to update
        
        center = self.win.minimap.get_center()
        
        # Calculate click position based on direction
        direction_map = {
            "north": (0, -distance),
            "south": (0, distance),
            "east": (distance, 0),
            "west": (-distance, 0),
            "northeast": (distance * 0.7, -distance * 0.7),
            "northwest": (-distance * 0.7, -distance * 0.7),
            "southeast": (distance * 0.7, distance * 0.7),
            "southwest": (-distance * 0.7, distance * 0.7),
        }
        
        if direction.lower() not in direction_map:
            self.log_msg(f"Invalid direction: {direction}")
            return False
        
        offset_x, offset_y = direction_map[direction.lower()]
        click_point = (center.x + int(offset_x), center.y + int(offset_y))
        
        # Ensure click point is within minimap bounds
        minimap_rect = self.win.minimap
        click_point = (
            max(minimap_rect.left, min(minimap_rect.left + minimap_rect.width, click_point[0])),
            max(minimap_rect.top, min(minimap_rect.top + minimap_rect.height, click_point[1]))
        )
        
        self.log_msg(f"Walking {direction} using minimap...")
        self.mouse.move_to(click_point, mouseSpeed="medium", knotsCount=2)
        self.mouse.click()
        time.sleep(1)  # Wait for character to start walking
        return True

    def navigate_to_tagged_object(self, color: clr.Color, use_camera_rotation: bool = True, use_minimap: bool = False, minimap_direction: str = None) -> bool:
        """
        Navigates to a tagged object that may be off-screen.
        First tries to find it on screen, then rotates camera, and optionally uses minimap.
        Args:
            color: The color of the tagged object to find.
            use_camera_rotation: Whether to rotate camera to search for the object.
            use_minimap: Whether to use minimap walking if object still not found.
            minimap_direction: Direction to walk on minimap if use_minimap is True.
        Returns:
            True if object was found and navigated to, False otherwise.
        """
        # First try to find it on screen
        obj = self.get_nearest_tag(color)
        if obj:
            self.mouse.move_to(obj.random_point(), mouseSpeed="slow", knotsCount=2)
            return True
        
        # Try camera rotation if enabled
        if use_camera_rotation:
            obj = self.find_tagged_object_with_camera_rotation(color)
            if obj:
                self.mouse.move_to(obj.random_point(), mouseSpeed="slow", knotsCount=2)
                return True
        
        # Try minimap walking if enabled
        if use_minimap and minimap_direction:
            if self.walk_to_minimap_location(minimap_direction):
                # Wait a bit and try to find the object again
                time.sleep(4)
                obj = self.get_nearest_tag(color)
                if obj:
                    self.mouse.move_to(obj.random_point(), mouseSpeed="slow", knotsCount=2)
                    return True
        
        return False

    def deposit(self, skip_slots: List[int] = None, keep_open: bool = False) -> None:
        """
        Shift-clicks inventory slots to drop items.
        Args:
            slots: The indices of slots to drop.
        """
        self.log_msg("Depositing items to bank...")
        empty_img = imsearch.BOT_IMAGES.joinpath("ui_templates", "empty_slot.png")
        if skip_slots is None:
            skip_slots = []

        for i, slot in enumerate(self.win.inventory_slots):
            if i in skip_slots or imsearch.search_img_in_rect(empty_img, slot, confidence=0.1):
                continue
            p = slot.random_point()
            self.mouse.move_to(
                (p[0], p[1]),
                mouseSpeed="fastest",
                knotsCount=1,
                offsetBoundaryY=40,
                offsetBoundaryX=40,
                tween=pytweening.easeInOutQuad,
            )
            self.mouse.click()
        time.sleep(1)

        if not keep_open:
            pag.press("esc")

    def deposit_to_bank(self, skip_slots: List[int] = None, keep_open: bool = False, use_camera_rotation: bool = True, use_minimap: bool = False, minimap_direction: str = None) -> bool:
        """
        Handles finding and interacting with the bank when inventory is full.
        Args:
            skip_slots: List of inventory slots to skip when depositing.
            keep_open: Whether to keep the bank open after depositing.
            use_camera_rotation: Whether to rotate camera to search for the bank if not found on screen.
            use_minimap: Whether to use minimap walking if bank still not found.
            minimap_direction: Direction to walk on minimap if use_minimap is True (e.g., "north", "south", "east", "west").
        Returns:
            True if banking was successful, False if bank couldn't be found
        """
        print("in function depositing to bank")
        failed_searches = 0
        max_attempts = 10
        
        # Try to find and navigate to the bank
        while not self.mouseover_text(contains="Bank", color=clr.OFF_WHITE):
            if not self.move_mouse_to_bank(use_camera_rotation, use_minimap, minimap_direction):
                failed_searches += 1
                if failed_searches % 5 == 0:
                    self.log_msg("Searching for bank...")
                if failed_searches > max_attempts:
                    # If we've been searching for too long...
                    self.log_msg("No tagged banks found after multiple attempts.")
                    return False
                time.sleep(1)
            else:
                # Found bank, check if mouseover text is correct
                time.sleep(0.5)  # Give time for mouseover text to update
                if self.mouseover_text(contains="Bank", color=clr.OFF_WHITE):
                    break

        if not self.mouseover_text(contains="Bank", color=clr.OFF_WHITE):
            return False

        self.mouse.click()
        self.mouse.move_to(self.win.chat.random_point(), mouseSpeed="slow", knotsCount=2)

        while not self.is_bank_open():
            print("waiting for bank to open")
            time.sleep(1)

        print('depositing')

        self.deposit(skip_slots, keep_open)
        return True

    def withdraw_item(self, item: Union[str, int] = '', keep_open: bool = False, conf: float = 0.2) -> bool:
        """
        Withdraws an item from the bank either by item name (image search) or by bank slot index.
        Args:
            item: The name of the item to withdraw (str), or the bank slot index (int).
            keep_open: Whether to keep the bank open after withdrawing.
            conf: Confidence for image search (if using item name).
        Returns:
            True if withdrawal was successful, False otherwise.
        """
        if isinstance(item, int):
            # Withdraw by slot index
            if 0 <= item < len(self.win.bank_slots):
                slot_rect = self.win.bank_slots[item]
                self.mouse.move_to(slot_rect.random_point())
                self.mouse.click()
                result = True
            else:
                print(f"Invalid bank slot index: {item}")
                result = False
        else:
            # Withdraw by item name (old behavior)
            slot = imsearch.search_img_in_rect(imsearch.BOT_IMAGES.joinpath("items", f"{item}.png"), self.win.game_view, conf)
            if slot:
                self.mouse.move_to(slot.random_point())
                self.mouse.click()
                result = True
            else:
                result = False

        if not keep_open:
            time.sleep(1)
            pag.press("esc")
        return result

    # --- Client Settings ---
    @deprecated(reason="This method is no longer needed for RuneLite games that can launch with arguments through the OSBC client.")
    def logout_runelite(self):
        """
        Identifies the RuneLite logout button and clicks it.
        """
        self.log_msg("Logging out of RuneLite...")
        rl_login_icon = imsearch.search_img_in_rect(
            imsearch.BOT_IMAGES.joinpath("settings", "runelite_logout.png"),
            self.win.rectangle(),
            confidence=0.9,
        )
        if rl_login_icon is not None:
            self.mouse.move_to(rl_login_icon.random_point())
            self.mouse.click()
            time.sleep(0.2)
            pag.press("enter")
            time.sleep(1)
