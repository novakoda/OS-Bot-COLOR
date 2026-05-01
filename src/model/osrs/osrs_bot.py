from abc import ABCMeta
import time

from model.runelite_bot import RuneLiteBot, RuneLiteWindow
from model.osrs.common_navigation import get_opposite_direction


class OSRSBot(RuneLiteBot, metaclass=ABCMeta):
    win: RuneLiteWindow = None

    def __init__(self, bot_title, description) -> None:
        super().__init__("OSRS", bot_title, description)

    def deposit_and_optionally_return(
        self,
        *,
        color,
        minimap_direction: str = None,
        skip_slots=None,
        return_wait_seconds: float = 2.0,
    ) -> bool:
        """Common bank deposit wrapper used by multiple scripts."""
        if not self.deposit_to_bank(color=color, skip_slots=skip_slots, minimap_direction=minimap_direction):
            return False
        if minimap_direction:
            opposite_direction = get_opposite_direction(minimap_direction)
            if opposite_direction:
                self.walk_to_minimap_location(direction=opposite_direction)
                time.sleep(return_wait_seconds)
        return True
