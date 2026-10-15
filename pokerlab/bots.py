"""Swappable bot interface. No GTO/optimality claims for these baselines."""
from __future__ import annotations

from dataclasses import dataclass
from random import Random
from typing import Protocol

from .engine import HeadsUpHand
from .equity import simulate_equity


@dataclass(frozen=True)
class Move:
    kind: str
    raise_to: int | None = None


class Bot(Protocol):
    def decide(self, hand: HeadsUpHand, seat: int) -> Move: ...


class EquityBot:
    """Rule-based equity-informed opponent, *not* a trained / GTO agent.

    Rollout estimates equity against uniform random two-card range. It uses
    conservative adjustments to avoid treating showdown equity as a perfect
    measure of realized future-street value. Raise sizes are discretized.
    """

    def __init__(self, seed: int = 42, trials: int = 220):
        self.rng = Random(seed)
        self.trials = trials

    def decide(self, hand: HeadsUpHand, seat: int) -> Move:
        legal = hand.legal(seat)
        if not legal['actions']:
            raise RuntimeError('not our turn')
        equity = simulate_equity(hand.holes[seat], hand.board, self.trials,
                                 self.rng.randrange(1 << 30))['equity']
        owed = legal['to_call']
        # equity realization discount on earlier streets; an experiment knob.
        realization = (0.83, 0.89, 0.95, 1.0)[hand.street_index]
        estimated = equity * realization
        pot = hand.pot
        odds = owed / (pot + owed) if owed else 0.0
        can_raise = 'raise' in legal['actions']
        # Small randomization avoids an easily memorized deterministic policy.
        roll = self.rng.random()
        if owed:
            if estimated + 0.035 < odds:
                return Move('fold')
            if can_raise and (estimated > (0.67 if hand.street_index == 0 else 0.76)) and roll < 0.55:
                target = self._raise_target(hand, legal, conservative=True)
                return Move('raise', target)
            # Very rare semi-bluff to avoid always giving away bet strength.
            if can_raise and estimated > 0.34 and roll < 0.035:
                return Move('raise', self._raise_target(hand, legal, conservative=False))
            return Move('call')
        if can_raise and (estimated > 0.59 or (estimated > 0.36 and roll < 0.10)):
            return Move('raise', self._raise_target(hand, legal, conservative=estimated < 0.70))
        return Move('check')

    def _raise_target(self, hand: HeadsUpHand, legal: dict, conservative: bool) -> int:
        # raise_to is TOTAL commitment on current street, NOT 'raise by'.
        # When facing a bet, pot-size-based increase includes amount to call.
        owed = legal['to_call']
        fraction = 0.52 if conservative else 0.83
        increased = max(2, round((hand.pot + owed) * fraction))
        target = hand.current_bet + increased
        return max(legal['min_raise_to'], min(target, legal['max_raise_to']))


class RandomBot:
    """Weak but legal benchmark opponent, not strategy-optimal."""
    def __init__(self, seed: int = 1):
        self.rng = Random(seed)

    def decide(self, hand: HeadsUpHand, seat: int) -> Move:
        legal = hand.legal(seat)
        choices = legal['actions']
        if 'raise' in choices and self.rng.random() < 0.27:
            lo = legal['min_raise_to']
            hi = legal['max_raise_to']
            amount = min(hi, max(lo, hand.current_bet + max(2, hand.pot // 2)))
            return Move('raise', amount)
        if 'fold' in choices and self.rng.random() < 0.3:
            return Move('fold')
        return Move('call' if 'call' in choices else 'check')
