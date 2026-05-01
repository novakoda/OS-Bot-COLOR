from typing import Callable


def try_hover_target(
    move_mouse: Callable[[], bool],
    is_valid_hover: Callable[[], bool],
) -> bool:
    """
    Ensure the mouse is hovering a valid target.

    Returns True when the hover is valid after checking current hover or
    attempting to move to the nearest target.
    """
    if is_valid_hover():
        return True
    if not move_mouse():
        return False
    return is_valid_hover()
