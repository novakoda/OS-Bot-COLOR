from typing import List, Union

import cv2
import numpy as np


class Color:
    def __init__(self, lower: List[int], upper: List[int] = None):
        """
        Defines a color or range of colors. This class converts RGB colors to BGR to satisfy OpenCV's color format.
        Args:
            lower: The lower bound of the color range [R, G, B].
            upper: The upper bound of the color range [R, G, B]. Exclude this arg if you're defining a solid color.
        """
        self.lower = np.array(lower[::-1])
        self.upper = np.array(upper[::-1]) if upper else np.array(lower[::-1])


def isolate_colors(image: cv2.Mat, colors: Union[Color, List[Color]]) -> cv2.Mat:
    """
    Isolates ranges of colors within an image and saves a new resulting image.
    Args:
        image: The image to process.
        colors: A Color or list of Colors.
    Returns:
        The image with the isolated colors (all shown as white).
    """
    if not isinstance(colors, list):
        colors = [colors]
    # Generate masks for each color
    masks = [cv2.inRange(image, color.lower, color.upper) for color in colors]
    # Create black mask
    h, w = image.shape[:2]
    mask = np.zeros([h, w, 1], dtype=np.uint8)
    # Combine masks
    for mask_ in masks:
        mask = cv2.bitwise_or(mask, mask_)
    return mask


"""Solid colors"""
BLACK = Color([0, 0, 0])
BLUE = Color([0, 0, 255])
CYAN = Color([0, 255, 255])
GREEN = Color([0, 255, 0])
ORANGE = Color([255, 144, 64])
PINK = Color([255, 0, 231])
PURPLE = Color([170, 0, 255])
RED = Color([255, 0, 0])
WHITE = Color([255, 255, 255])
YELLOW = Color([255, 255, 0])
LIME_GREEN = Color([0, 90, 0], [100, 255, 100])  # For gemstone crab tags

"""Mastering Mixology lever tags (Runelite entity highlight ranges)"""
MIXOLOGY_AGA = Color([0, 200, 70], [80, 255, 140])    # A = Green ~RGB(0, 255, 106)
MIXOLOGY_MOX = Color([0, 150, 170], [80, 230, 255])   # M = Blue ~RGB(0, 192, 255)
MIXOLOGY_LYE = Color([180, 10, 50], [255, 80, 120])   # L = Red ~RGB(255, 41, 81)
MIXOLOGY_VESSEL = Color([0, 220, 220], [80, 255, 255])  # Mixing vessel
MIXOLOGY_PROCESSOR = Color([200, 0, 200], [255, 60, 255])  # Retort / agitator / alembic
MIXOLOGY_CONVEYOR = Color([180, 180, 0], [255, 255, 80])  # Conveyor belt

"""Mastering Mixology HUD abbreviation text (anti-aliased ranges)"""
MIXOLOGY_HUD_AGA = Color([0, 180, 60], [120, 255, 140])
MIXOLOGY_HUD_MOX = Color([0, 120, 160], [120, 240, 255])
MIXOLOGY_HUD_LYE = Color([100, 0, 25], [255, 120, 150])
MIXOLOGY_HUD_LYE_PINK = Color([80, 0, 60], [255, 90, 255])


"""Colors for use with semi-transparent text"""
OFF_CYAN = Color([0, 200, 200], [70, 255, 255])
OFF_GREEN = Color([0, 100, 0], [30, 255, 255])
OFF_ORANGE = Color([180, 100, 30], [255, 166, 103])
OFF_WHITE = Color([190, 190, 190], [255, 255, 255])
OFF_YELLOW = Color([90, 90, 0], [255, 255, 120])

"""Colors for use with minimap orb text"""
ORB_GREEN = Color([0, 255, 0], [255, 255, 0])
ORB_RED = Color([255, 0, 0], [255, 255, 0])

"""Colors for use with menu text"""
BANK_ORANGE = Color([255, 152, 31])
COOK_BROWN = Color([64, 48, 32])


"""Dark colors for tags"""
DARK_YELLOW = Color([40, 40, 0])
DARK_RED = Color([40, 0, 0])
DARK_GREEN = Color([0, 40, 0])
DARK_PINK = Color([21, 0, 19])

"""Wider range for thin/outline green tags (e.g. Runelite entity highlights)"""
TAG_GREEN = Color([0, 120, 0], [100, 255, 120])
