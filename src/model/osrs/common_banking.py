import random
import time
from typing import List, Optional, Tuple, Union

import utilities.color as clr

from model.osrs.common_navigation import get_opposite_direction

ColorLike = Union[clr.Color, List[clr.Color]]


def withdraw_tagged_item_from_bank_precise(
    bot,
    *,
    color: Optional[ColorLike] = None,
    keep_open: bool = True,
    max_attempts: int = 3,
    retry_sleep: float = 0.2,
    post_click_sleep: Tuple[float, float] = (0.15, 0.35),
    fallback_to_generic_withdraw: bool = True,
    mouse_speed: str = "fast",
) -> bool:
    """
    Clicks the best-matching bank highlighter tag inside bank slots (closest contour center to slot center),
    then optionally falls back to ``bot.withdraw_item(color, keep_open=...)``.

    Use this when random clicks on a whole bank slot miss the tagged item outline.

    Args:
        bot: Bot instance (``RuneliteBot`` / ``OSRSJagexAccountBot``) with ``get_all_tagged_in_rect``,
            ``is_bank_open``, ``win.bank_slots``, ``withdraw_item``, ``mouse``.
        color: One ``clr.Color`` or a list (e.g. ``[clr.RED, clr.DARK_RED]``). Default ``clr.RED``.
        keep_open: Passed to ``withdraw_item`` when using fallback.
        max_attempts: Scan/click retries before optional fallback.
        retry_sleep: Delay between scan attempts when no tag is found.
        post_click_sleep: ``(min, max)`` seconds to sleep after a successful precise click.
        fallback_to_generic_withdraw: If True, call ``withdraw_item`` when precise targeting fails.
        mouse_speed: Mouse speed for the precise move (see ``mouse.move_to``).

    Returns:
        True if a click was performed (precise) or fallback succeeded; False otherwise.
    """
    if color is None:
        color = clr.RED

    if not bot.is_bank_open():
        return False

    if not bot.win.bank_slots:
        if not bot.win.locate_bank_slots(bot.win.rectangle()):
            return False

    lo, hi = post_click_sleep
    if lo > hi:
        lo, hi = hi, lo

    for _ in range(max_attempts):
        best_target = None
        best_distance = float("inf")

        for slot_rect in bot.win.bank_slots:
            tagged_objects = bot.get_all_tagged_in_rect(slot_rect, color)
            bot.log_msg(f"Tagged objects: {tagged_objects}")
            if not tagged_objects:
                continue

            slot_center = slot_rect.get_center()
            for obj in tagged_objects:
                target = obj.center()
                distance = ((target.x - slot_center.x) ** 2 + (target.y - slot_center.y) ** 2) ** 0.5
                if distance < best_distance:
                    best_distance = distance
                    best_target = target

        if not best_target:
            time.sleep(retry_sleep)
            continue

        bot.mouse.move_to((best_target.x, best_target.y), mouseSpeed=mouse_speed)
        bot.mouse.click()
        time.sleep(random.uniform(lo, hi))
        return True

    if fallback_to_generic_withdraw:
        colors = color if isinstance(color, list) else [color]
        for c in colors:
            if bot.withdraw_item(c, keep_open=keep_open):
                return True
        return False

    return False


def deposit_and_optionally_return(
    bot,
    *,
    color,
    minimap_direction: str = None,
    skip_slots=None,
    return_wait_seconds: float = 2.0,
) -> bool:
    """
    Shared bank deposit wrapper with optional minimap return step.
    """
    if not bot.deposit_to_bank(color=color, skip_slots=skip_slots, minimap_direction=minimap_direction):
        return False

    if minimap_direction:
        opposite_direction = get_opposite_direction(minimap_direction)
        if opposite_direction:
            bot.log_msg(f"Returning to activity location ({opposite_direction})...")
            bot.walk_to_minimap_location(direction=opposite_direction)
            time.sleep(return_wait_seconds)

    return True
