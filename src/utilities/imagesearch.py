from pathlib import Path
from typing import Union
import numpy as np

import cv2

from typing import List
from utilities.geometry import Point, Rectangle, RuneLiteObject

# --- Paths to Image folders ---
__PATH = Path(__file__).parent.parent
IMAGES = __PATH.joinpath("images")
BOT_IMAGES = IMAGES.joinpath("bot")


def __imagesearcharea(template: Union[cv2.Mat, str, Path], im: cv2.Mat, confidence: float) -> Rectangle:
    """
    Locates an image within another image.
    Args:
        template: The image to search for.
        im: The image to search in.
        confidence: The confidence level of the search in range 0 to 1, where 0 is a perfect match.
    Returns:
        A Rectangle outlining the found template inside the image.
    """
    # If image doesn't have an alpha channel, convert it from BGR to BGRA
    if len(template.shape) < 3 or template.shape[2] != 4:
        template = cv2.cvtColor(template, cv2.COLOR_BGR2BGRA)
    # Get template dimensions
    hh, ww = template.shape[:2]
    # Extract base image and alpha channel
    base = template[:, :, 0:3]
    alpha = template[:, :, 3]
    alpha = cv2.merge([alpha, alpha, alpha])

    correlation = cv2.matchTemplate(im, base, cv2.TM_SQDIFF_NORMED, mask=alpha)
    min_val, _, min_loc, _ = cv2.minMaxLoc(correlation)
    if min_val < confidence:
        # print('found match under conf ', min_val, confidence)
        return Rectangle.from_points(Point(min_loc[0], min_loc[1]), Point(min_loc[0] + ww, min_loc[1] + hh))
    return None


def search_img_in_rect(image: Union[cv2.Mat, str, Path], rect: Union[Rectangle, cv2.Mat], confidence=0.2) -> Rectangle:
    """
    Searches for an image in a rectangle. This function works with images containing transparency (sprites).
    Args:
        image: The image to search for (can be a path or matrix).
        rect: The Rectangle to search in (can be a Rectangle or a matrix).
        confidence: The confidence level of the search in range 0 to 1, where 0 is a perfect match.
    Returns:
        A Rectangle outlining the found image relative to the container, or None.
    Notes:
        If a matrix is supplied for the `rect` argument instead of a Rectangle, and the image is found within this matrix,
        the returned Rectangle will be relative to the top-left corner of the matrix. In other words, the returned
        Rectangle is not suitable for use with mouse movement/clicks, as it will not be relative to the game window.
        However, you will still be able to confirm if the image was found or not. This is useful in cases where you take a static
        screenshot and want to search for a series of images to verify that they are present.
    Examples:
        >>> deposit_all_btn = search_img_in_rect(BOT_IMAGES.joinpath("bank", "deposit.png"), self.win.game_view)
        >>> if deposit_all_btn:
        >>>     # Deposit all button was found
    """
    if isinstance(image, str):
        image = cv2.imread(image, cv2.IMREAD_UNCHANGED)
    elif isinstance(image, Path):
        image = cv2.imread(str(image), cv2.IMREAD_UNCHANGED)
    im = rect.screenshot() if isinstance(rect, Rectangle) else rect

    if found_rect := __imagesearcharea(image, im, confidence):
        if isinstance(rect, Rectangle):
            found_rect.left += rect.left
            found_rect.top += rect.top
        return found_rect
    else:
        return None

def __imagesearcharea_list(template: Union[cv2.Mat, str, Path], im: cv2.Mat, confidence: float) -> List[RuneLiteObject]:
    # If image doesn't have an alpha channel, convert it from BGR to BGRA
    if len(template.shape) < 3 or template.shape[2] != 4:
        template = cv2.cvtColor(template, cv2.COLOR_BGR2BGRA)

    # Get template dimensions
    hh, ww = template.shape[:2]

    # Extract base image and alpha channel
    base = template[:, :, 0:3]
    alpha = template[:, :, 3]
    alpha = cv2.merge([alpha, alpha, alpha])

    # Get correlation matrix
    correlation = cv2.matchTemplate(im, base, cv2.TM_SQDIFF_NORMED, mask=alpha)

    # Find all matches under confidence threshold
    matches = np.where(correlation <= confidence)

    found_objects = []
    for y, x in zip(*matches):
        # Create the Rectangle with integer coordinates
        x, y = int(x), int(y)
        rect = Rectangle(left=x, top=y, width=ww, height=hh)

        # Set all values as integers
        x_max = x + ww
        y_max = y + hh
        center = Point((x + x_max) // 2, (y + y_max) // 2)

        # Create axis points array
        axis = np.array([[x, y], [x_max, y], [x_max, y_max], [x, y_max]])

        # Create RuneLiteObject with integer values and axis
        obj = RuneLiteObject(rect, x_max, y, y_max, ww, hh, center, axis)
        obj._x_min = x
        obj._y_min = y
        obj._width = ww
        obj._height = hh

        found_objects.append(obj)

    return found_objects

def search_all_img_in_rect(image: Union[cv2.Mat, str, Path], rect: Union[Rectangle, cv2.Mat], confidence=0.15) -> List[RuneLiteObject]:
    if isinstance(image, str):
        image = cv2.imread(image, cv2.IMREAD_UNCHANGED)
    elif isinstance(image, Path):
        image = cv2.imread(str(image), cv2.IMREAD_UNCHANGED)
    im = rect.screenshot() if isinstance(rect, Rectangle) else rect

    found_objects = __imagesearcharea_list(image, im, confidence)

    # Only adjust coordinates if we're working with a Rectangle
    if isinstance(rect, Rectangle) and found_objects:
        for obj in found_objects:
            if obj and obj.rect:
                obj.rect.left += rect.left
                obj.rect.top += rect.top

    return found_objects


