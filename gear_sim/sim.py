#!/usr/bin/env python
from collections import defaultdict
from random import choice
from statistics import mean, pstdev
from typing import Dict, List, Type

from gear_sim.api import load, Player


DROP_TABLE = {
    1: (('earring', 'neck', 'ring', 'wrist'), ()),
    2: (('head', 'hands', 'feet'), ('glaze',)),
    3: (('head', 'hands', 'feet', 'legs'), ('twine',)),
    4: ((), ('weapon', 'chest')),
}
ITEM_COUNT = 3


def get_random_drop(fight: int) -> List[str]:
    random, ensured = DROP_TABLE[fight]
    drops = list(ensured)
    while len(drops) < ITEM_COUNT:
        options = [x for x in random if drops.count(x) < 2]
        if not options:
            break
        drops.append(choice(options))
    return drops


class LootRules:
    def __init__(self, party: List[Player]) -> None:
        self.party = party

    def how_many_bis(self) -> int:
        return sum(player.is_bis() for player in self.party)

    def pct_bis(self) -> float:
        return mean([player.pct_bis() for player in self.party])

    def is_party_bis(self) -> bool:
        return self.how_many_bis() == len(self.party)

    def give_books(self, fight: int) -> None:
        for player in self.party:
            player.give_book(fight)

    def distribute(self, item: str) -> bool:
        raise NotImplementedError


class NeedIfBis(LootRules):
    def distribute(self, item: str) -> bool:
        options = [player for player in self.party if player.needs(item)]
        if options:
            choice(options).give(item)
        return bool(options)


class RoundRobin(LootRules):
    GROUPS: Dict[str, int] = {}

    def __init__(self, party: List[Player]) -> None:
        super().__init__(party=party)
        self.counts: Dict[int, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

    def _give(self, player: Player, item: str) -> None:
        self.counts[self.GROUPS.get(item, -1)][player.name] += 1
        player.give(item)

    def _maybe_give(self, options: List[Player], item: str) -> bool:
        if options:
            self._give(choice(options), item)
            return True
        return False

    def distribute(self, item: str) -> bool:
        options = [player for player in self.party if player.needs(item)]
        if not options:
            return False
        cat_counts = self.counts[self.GROUPS.get(item, -1)]
        min_count = min(cat_counts[player.name] for player in options)
        options = [player for player in options if cat_counts[player.name] == min_count]
        return self._maybe_give(options, item)


class GranularRoundRobin(RoundRobin):
    GROUPS: Dict[str, int] = {
        'head': 0,
        'hands': 0,
        'feet': 0,
        'chest': 1,
        'legs': 1,
        'weapon': 2,
        'earring': 3,
        'neck': 3,
        'wrist': 3,
        'ring': 3,
        'glaze': 4,
        'twine': 5,
    }


class LessGranularRoundRobin(RoundRobin):
    GROUPS: Dict[str, int] = {
        'head': 0,
        'hands': 0,
        'feet': 0,
        'chest': 0,
        'legs': 0,
        'weapon': 1,
        'earring': 2,
        'neck': 2,
        'wrist': 2,
        'ring': 2,
        'glaze': 2,
        'twine': 0,
    }


class _EarlyGlazeTwineMixin:
    DO_GLAZE = True
    DO_TWINE = True

    def distribute(self, item: str) -> bool:
        if self.DO_GLAZE and item == 'glaze':
            options = [player for player in self.party if player.needed_glaze > 2]
            res = self._maybe_give(options, item)
            if res:
                return True
        if self.DO_TWINE and item == 'twine':
            options = [player for player in self.party if player.needed_twine > 2]
            res = self._maybe_give(options, item)
            if res:
                return True
        return super().distribute(item=item)


class GranularEarlyGlazeTwine(_EarlyGlazeTwineMixin, GranularRoundRobin):
    pass


class GranularEarlyGlaze(_EarlyGlazeTwineMixin, GranularRoundRobin):
    DO_TWINE = False


class LessGranularEarlyGlazeTwine(_EarlyGlazeTwineMixin, LessGranularRoundRobin):
    pass


RULESETS = [
    NeedIfBis,
    RoundRobin,
    GranularRoundRobin,
    LessGranularRoundRobin,
    GranularEarlyGlaze,
    GranularEarlyGlazeTwine,
    LessGranularEarlyGlazeTwine,
]


class LootSummary:
    def __init__(self, ruleset: LootRules) -> None:
        self.weeks = 0
        self.bis_by_week = []
        self.player_bis_per_week = defaultdict(list)
        self.per_item_drop = defaultdict(int)
        self.ruleset = ruleset

    def record_bis(self) -> None:
        for player in self.ruleset.party:
            self.player_bis_per_week[player.name].append(player.pct_bis())
        self.bis_by_week.append(self.ruleset.pct_bis())

    @property
    def total_dropped(self) -> int:
        return sum(self.per_item_drop.values())


def _accumulate(player_bis_per_week_a, player_bis_per_week_b, m=1.0) -> Dict[str, List[float]]:
    if player_bis_per_week_a is None:
        return player_bis_per_week_b
    ret = {}
    for k in player_bis_per_week_a:
        ret[k] = [
            a * m + b
            for a, b in zip(player_bis_per_week_a[k], player_bis_per_week_b[k])
        ]
    return ret


def _delta_player_helper(name_a, name_b, player_bis_per_week_a, player_bis_per_week_b, factor=1) -> None:
    print('{} (-) vs {} (+)\n'.format(name_a, name_b))
    weeks = len(tuple(player_bis_per_week_b.values())[0])
    week_str = ''.join(map('{:>6}'.format, range(weeks)))
    print('{:10} {}'.format('Week', week_str))
    accumulated = [0.0] * weeks
    delta_map = _accumulate(player_bis_per_week_a, player_bis_per_week_b, m=-1.0)
    for player, deltas in delta_map.items():
        formatted = []
        for i, delta in enumerate(deltas):
            accumulated[i] += delta
            formatted.append('{: 1.2f}'.format(delta / factor))
        print('{:10}: {}'.format(player, ' '.join(formatted)))
    formatted = []
    for i, acc in enumerate(accumulated):
        formatted.append('{: 1.2f}'.format(acc / (len(accumulated) * factor)))
    print('\n{:10}: {}'.format('total', ' '.join(formatted)))


def delta_player_per_week_bis(summary_a, summary_b) -> None:
    _delta_player_helper(
        type(summary_a.ruleset).__name__,
        type(summary_b.ruleset).__name__,
        summary_a.player_bis_per_week,
        summary_b.player_bis_per_week,
    )


def sample_weeks_to_bis(ruleset: Type[LootRules], week_limit=100) -> LootSummary:
    lootmaster = ruleset(load())
    summary = LootSummary(lootmaster)

    while summary.weeks < week_limit and not lootmaster.is_party_bis():
        for fight in DROP_TABLE:
            for item in get_random_drop(fight):
                if not lootmaster.distribute(item):
                    summary.per_item_drop[item] += 1
            lootmaster.give_books(fight)
        summary.weeks += 1
        summary.record_bis()
    return summary


def test_ruleset(cls, rounds: int = 1000) -> None:
    print(cls.__name__)
    weeks, dropped = [], []
    sum_bis_pcts = [0.0 for _ in range(10)]
    for _ in range(rounds):
        summary = sample_weeks_to_bis(cls)
        weeks.append(summary.weeks)
        dropped.append(summary.total_dropped)
        for i, x in enumerate(summary.bis_by_week):
            if i < len(sum_bis_pcts):
                sum_bis_pcts[i] += x
    sum_bis_pcts = [x / rounds for x in sum_bis_pcts]
    print(' Weeks   mean={:1.2f} pstdev={:1.2f}'.format(mean(weeks), pstdev(weeks)))
    print(' Dropped mean={:1.2f} pstdev={:1.2f}'.format(mean(dropped), pstdev(dropped)))
    print(' ' + ', '.join(map('{:1.2f}'.format, sum_bis_pcts)))
    print(' Weeks max: {}, over 8 total: {}'.format(max(weeks), len([x for x in weeks if x > 8])))


def test_all_rulesets(rounds: int = 1000) -> None:
    for cls in RULESETS:
        test_ruleset(cls, rounds)
        print('')
    print(f'Done with {rounds} per ruleset')


def test_head_to_head(ruleset_a: Type[LootRules], ruleset_b: Type[LootRules], rounds: int = 1000) -> None:
    state_a = None
    state_b = None
    for _ in range(rounds):
        summary_a = sample_weeks_to_bis(ruleset_a)
        summary_b = sample_weeks_to_bis(ruleset_b)
        state_a = _accumulate(state_a, summary_a.player_bis_per_week)
        state_b = _accumulate(state_b, summary_b.player_bis_per_week)
    _delta_player_helper(ruleset_a.__name__, ruleset_b.__name__, state_a, state_b, factor=rounds)
    print(f'aggregate over {rounds} rounds')


if __name__ == '__main__':
    test_all_rulesets()
