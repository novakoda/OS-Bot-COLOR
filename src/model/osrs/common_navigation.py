from dataclasses import dataclass


def get_opposite_direction(direction: str) -> str:
    """Return opposite minimap direction or None."""
    if not direction:
        return None

    opposite_map = {
        "north": "south",
        "south": "north",
        "east": "west",
        "west": "east",
        "northeast": "southwest",
        "northwest": "southeast",
        "southeast": "northwest",
        "southwest": "northeast",
    }
    return opposite_map.get(direction.lower())


@dataclass
class SearchRetry:
    """Track repeated search failures and timing-based actions."""

    failures: int = 0

    def fail(self) -> int:
        self.failures += 1
        return self.failures

    def reset(self) -> None:
        self.failures = 0

    def every(self, interval: int) -> bool:
        return interval > 0 and self.failures > 0 and self.failures % interval == 0

    def exceeded(self, maximum: int) -> bool:
        return self.failures > maximum
