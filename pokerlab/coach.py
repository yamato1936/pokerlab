"""Explainable limited post-hand feedback based on local rollouts.

These figures are NOT GTO regrets or solver EVs; no future street modeling.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

from .equity import simulate_equity
from .engine import HeadsUpHand


@dataclass
class Decision:
    street: str
    hand: list[int]
    board: list[int]
    choice: str
    pot: int
    to_call: int
    equity: float
    low: float
    high: float
    pot_odds: float | None
    call_ev: float | None
    note: str

    def as_dict(self):
        from .equity import format_card
        return {'street': self.street,
                'hand': [format_card(c) for c in self.hand],
                'board': [format_card(c) for c in self.board],
                'choice': self.choice, 'pot': self.pot, 'to_call': self.to_call,
                'equity': round(self.equity, 4), 'low': round(self.low, 4),
                'high': round(self.high, 4),
                'pot_odds': self.pot_odds,
                'call_ev': round(self.call_ev, 2) if self.call_ev is not None else None,
                'note': self.note}


class Coach:
    def __init__(self, trials: int = 550):
        self.trials = trials
        self.decisions: list[Decision] = []

    def observe(self, hand: HeadsUpHand, actor: int, kind: str):
        """Called *before* the human act; private rival cards never used."""
        legal = hand.legal(actor)
        pot, owed = hand.pot, legal['to_call']
        known = hand.holes[actor][:]
        board = hand.board[:]
        stats = simulate_equity(known, board, self.trials, seed=911 + len(self.decisions) * 7919)
        equity = stats['equity']
        odds = owed / (pot + owed) if owed > 0 else None
        ev = equity * (pot + owed) - owed if owed > 0 else None
        if owed:
            if stats['low'] > odds:
                note = 'ランダムレンジへの単純コールEVはプラス。ただし相手レンジと将来のベットは未考慮。'
            elif stats['high'] < odds:
                note = 'ランダムレンジへの単純コールEVはマイナス。相手が強いほどさらに不利になり得る。'
            else:
                note = 'コールの単純EVは推定誤差の範囲内。より多くの試行・相手レンジが必要。'
        else:
            note = '無料でチェック可能。ベットする価値は相手のフォールド率・コールレンジで変わる。'
        if kind == 'raise':
            note += ' レイズEVはこのモデルでは評価していない。'
        self.decisions.append(Decision(hand.street, known, board, kind, pot, owed,
                                       equity, stats['low'], stats['high'], odds, ev, note))

    def report(self):
        return [d.as_dict() for d in self.decisions]
