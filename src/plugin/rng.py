"""A seeded generator built on sha256, so a case never depends on the Python version."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from typing import TypeVar

T = TypeVar("T")


class Rng:
    def __init__(self, key: str) -> None:
        self.key = key
        self.count = 0

    def below(self, limit: int) -> int:
        self.count += 1
        digest = hashlib.sha256(f"{self.key}:{self.count}".encode()).digest()
        return int.from_bytes(digest, "big") % limit

    def between(self, low: int, high: int) -> int:
        return low + self.below(high - low + 1)

    def pick(self, items: Sequence[T]) -> T:
        return items[self.below(len(items))]

    def shuffled(self, items: Sequence[T]) -> list[T]:
        result = list(items)
        for index in range(len(result) - 1, 0, -1):
            other = self.below(index + 1)
            result[index], result[other] = result[other], result[index]
        return result
