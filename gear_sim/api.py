from __future__ import absolute_import, annotations

from collections import defaultdict
from functools import lru_cache
from random import choice
from typing import Dict, List, Set

import yaml


PRICES = {
    # item: (num books, kind of book)
    'weapon': (8, 4),
    'head': (6, 2),
    'chest': (8, 4),
    'hands': (6, 2),
    'legs': (8, 3),
    'feet': (6, 2),
    'earring': (4, 1),
    'neck': (4, 1),
    'wrist': (4, 1),
    'ring': (4, 1),
    'glaze': (4, 2),
    'twine': (4, 3),
}
TWINE = {'head', 'chest', 'hands', 'legs', 'feet'}
GLAZE = {'earring', 'neck', 'wrist', 'ring'}


@lru_cache(maxsize=None)
def _cached_load(filename: str) -> Dict[str, Dict[str, str]]:
    with open(filename) as fp:
        return yaml.safe_load(fp)


def load(filename: str = 'bis.yaml') -> List[Player]:
    return [Player(k, v) for k, v in _cached_load(filename).items()]


def _adjust_name(item: str) -> str:
    if item in {'ring_r', 'ring_l'}:
        return 'ring'
    return item


class Player:
    BUY = False

    def __init__(self, name: str, bis: Dict[str, str]) -> None:
        self.name = name
        self.books: Dict[int, int] = defaultdict(int)
        self.needed_raid = {_adjust_name(k) for k, v in bis.items() if v == 'raid'}
        self.needed_glaze = sum(_adjust_name(f) in GLAZE for f in bis if bis[f] == 'tome')
        self.needed_twine = sum(_adjust_name(f) in TWINE for f in bis if bis[f] == 'tome')

    def _get_needed_books(self) -> Dict[int, int]:
        needed_books = {k: 0 for k in (1, 2, 3, 4)}
        for item in self.needed_raid:
            num, kind = PRICES[item]
            needed_books[kind] += num
        num, kind = PRICES['glaze']
        needed_books[kind] += num * self.needed_glaze
        num, kind = PRICES['twine']
        needed_books[kind] += num * self.needed_twine
        return needed_books

    def _can_buy_rest_of_bis(self) -> bool:
        needed_books = self._get_needed_books()
        for k in needed_books:
            if needed_books[k] > self.books[k]:
                return False
        return True

    def _book_bis_buy_missing_pct(self) -> float:
        needed_books = self._get_needed_books()
        total = 0
        missing = 0
        for k in needed_books:
            total += needed_books[k]
            missing += max(0, needed_books[k] - self.books[k])
        if total == 0:
            return 1.0
        return float(missing) / float(total)


    def is_bis(self) -> bool:
        return (
            (not any((self.needed_raid, self.needed_glaze, self.needed_twine)))
            or self._can_buy_rest_of_bis()
        )

    def pct_bis(self) -> float:
        book_pct = self._book_bis_buy_missing_pct()
        missing_loot = float(len(self.needed_raid) + self.needed_twine + self.needed_glaze) * book_pct
        return 1.0 - missing_loot / 11.0

    def give_book(self, fight: int) -> None:
        self.books[fight] += 1
        if not self.BUY:
            return
        options: List[str] = []
        for item, (count, kind) in PRICES.items():
            if self.needs(item) and self.books[kind] >= count:
                options.append(item)
        if options:
            purchased = choice(options)
            count, kind = PRICES[purchased]
            self.books[kind] -= count
            self.give(purchased)

    def needs(self, item: str) -> bool:
        if item == 'glaze':
            return self.needed_glaze > 0
        if item == 'twine':
            return self.needed_twine > 0
        return item in self.needed_raid

    def give(self, item: str) -> None:
        if item == 'glaze':
            if self.needed_glaze == 0:
                raise ValueError('bad glaze')
            self.needed_glaze -= 1
        elif item == 'twine':
            if self.needed_twine == 0:
                raise ValueError('bad twine')
            self.needed_twine -= 1
        else:
            if item not in self.needed_raid:
                raise ValueError(f'bad {item}')
            self.needed_raid.remove(item)
