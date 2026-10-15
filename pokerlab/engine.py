"""Minimal auditable heads-up no-limit hold'em engine.

Scope: two players, fixed blinds 1/2, 200 chip stacks per hand,
no antes, no rake, no side pots. All-in runouts are automatic.
Raises are capped at the effective (matchable) stack.
"""
from __future__ import annotations

from dataclasses import dataclass
from random import Random
from typing import Any

from .equity import DECK, HAND_NAMES, format_card, hand_score

STREETS = ('preflop', 'flop', 'turn', 'river')


@dataclass(frozen=True)
class Action:
    actor: int
    street: str
    kind: str
    amount: int  # chips ADDED on this action, not total bet
    pot_after: int

    def as_dict(self) -> dict[str, Any]:
        return vars(self).copy()


class HeadsUpHand:
    def __init__(self, seed: int = 0, button: int = 0, starting_stack: int = 200,
                 deck: list[int] | None = None):
        if button not in (0, 1) or starting_stack < 3:
            raise ValueError('button must be 0/1; starting_stack >= 3')
        self.button = button  # button == small blind; acts first preflop
        self.bb = 1 - button
        self.stacks = [starting_stack, starting_stack]
        self.starting_stack = starting_stack
        self.deck = (deck[:] if deck is not None else Random(seed).sample(DECK, len(DECK)))
        if len(self.deck) != 52 or set(self.deck) != set(DECK):
            raise ValueError('deck must be a permutation of 52 cards')
        self.holes = [self._deal(2), self._deal(2)]
        self.board: list[int] = []
        self.street_index = 0
        self.contrib = [0, 0]  # current street only
        self.total_committed = [0, 0]
        self.current_bet = 0
        self.last_full_raise = 2
        self.actions: list[Action] = []
        self.finished = False
        self.winner: int | None = None
        self.result_reason: str | None = None
        self.showdown = False
        self.payouts = [0, 0]
        self._commit(self.button, 1)
        self._commit(self.bb, 2)
        self.current_bet = 2
        self.pending = [self.button, self.bb]
        self._assert_chips()

    def _deal(self, n: int) -> list[int]:
        dealt = self.deck[:n]
        del self.deck[:n]
        return dealt

    @property
    def street(self) -> str:
        return STREETS[self.street_index]

    @property
    def pot(self) -> int:
        return sum(self.total_committed)

    @property
    def to_act(self) -> int | None:
        return None if self.finished or not self.pending else self.pending[0]

    def _commit(self, actor: int, amount: int):
        if amount < 0 or amount > self.stacks[actor]:
            raise ValueError('invalid chip commitment')
        self.stacks[actor] -= amount
        self.contrib[actor] += amount
        self.total_committed[actor] += amount

    def _assert_chips(self):
        assert sum(self.stacks) + self.pot == self.starting_stack * 2
        assert min(self.stacks) >= 0

    def legal(self, actor: int | None = None) -> dict[str, Any]:
        actor = self.to_act if actor is None else actor
        if self.finished or actor != self.to_act:
            return {'actions': []}
        rival = 1 - actor
        to_call = min(self.current_bet - self.contrib[actor], self.stacks[actor])
        # In heads-up, unmatched chips are never wagered. Cap raises at the
        # amount the opponent could cover on this street.
        max_to = min(self.contrib[actor] + self.stacks[actor],
                     self.contrib[rival] + self.stacks[rival])
        can_raise = self.stacks[actor] > to_call and self.stacks[rival] > 0 and max_to > self.current_bet
        full_min = self.current_bet + self.last_full_raise if self.current_bet else 2
        min_to = min(full_min, max_to) if can_raise else None
        actions = ['check' if to_call == 0 else 'call']
        if to_call:
            actions.insert(0, 'fold')
        if can_raise:
            actions.append('raise')
        return {'actions': actions, 'to_call': to_call,
                'min_raise_to': min_to, 'max_raise_to': max_to if can_raise else None,
                'is_short_all_in_only': bool(can_raise and max_to < full_min),
                'current_bet': self.current_bet, 'street_contribution': self.contrib[actor]}

    def act(self, actor: int, kind: str, raise_to: int | None = None):
        legal = self.legal(actor)
        if kind not in legal['actions']:
            raise ValueError(f'illegal {kind!r} for player {actor}: {legal}')
        street_before = self.street
        if kind == 'fold':
            self.pending.clear()
            self._award(1 - actor, 'fold', showdown=False)
            amount = 0
        elif kind in ('check', 'call'):
            amount = legal['to_call']
            self._commit(actor, amount)
            self.pending.pop(0)
        else:
            if type(raise_to) is not int or not (legal['min_raise_to'] <= raise_to <= legal['max_raise_to']):
                raise ValueError(f'raise_to must be integer in [{legal["min_raise_to"]}, {legal["max_raise_to"]}]')
            amount = raise_to - self.contrib[actor]
            raise_size = raise_to - self.current_bet
            if raise_size >= self.last_full_raise:
                self.last_full_raise = raise_size
            self._commit(actor, amount)
            self.current_bet = raise_to
            self.pending = [1 - actor]
        self.actions.append(Action(actor, street_before, kind, amount, self.pot))
        if not self.finished and not self.pending:
            self._advance()
        self._assert_chips() if not self.finished else None

    def _advance(self):
        # If either player has no chips left after matching, immediately run
        # out the board. There are no side pots in heads-up play.
        if 0 in self.stacks or self.street_index == 3:
            while len(self.board) < 5:
                self._deal(1)  # burn a card before each board reveal
                if not self.board:
                    self.board.extend(self._deal(3))
                else:
                    self.board.extend(self._deal(1))
            self._showdown()
            return
        self.street_index += 1
        self.contrib = [0, 0]
        self.current_bet = 0
        self.last_full_raise = 2
        self._deal(1)  # burn
        self.board.extend(self._deal(3 if self.street_index == 1 else 1))
        self.pending = [self.bb, self.button]  # BB acts first postflop

    def _showdown(self):
        left = hand_score(self.holes[0] + self.board)
        right = hand_score(self.holes[1] + self.board)
        if left == right:
            self._award(None, 'split', showdown=True)
        else:
            self._award(0 if left > right else 1, 'showdown', showdown=True)

    def _award(self, winner: int | None, reason: str, showdown: bool):
        self.finished = True
        self.winner = winner
        self.result_reason = reason
        self.showdown = showdown
        p = self.pot
        if winner is None:
            # Heads-up odd chip is awarded to the first player clockwise from
            # the dealer, i.e. the big blind in this two-player implementation.
            self.payouts = [p // 2, p // 2]
            self.payouts[self.bb] += p % 2
        else:
            self.payouts[winner] = p
        self.stacks = [s + winnings for s, winnings in zip(self.stacks, self.payouts)]
        assert sum(self.stacks) == self.starting_stack * 2
        self.pending = []

    def public_state(self, viewer: int = 0) -> dict[str, Any]:
        show = self.showdown
        return {
            'street': self.street, 'board': [format_card(c) for c in self.board],
            'you': [format_card(c) for c in self.holes[viewer]],
            'opponent': [format_card(c) for c in self.holes[1 - viewer]] if show else None,
            'pot': self.pot, 'stacks': self.stacks.copy(),
            'contrib': self.contrib.copy(), 'button': self.button,
            'to_act': self.to_act, 'legal': self.legal(viewer) if self.to_act == viewer else {'actions': []},
            'finished': self.finished, 'winner': self.winner,
            'reason': self.result_reason,
            'showdown_hand': [HAND_NAMES[hand_score(h + self.board)[0]] for h in self.holes] if show else None,
            'actions': [a.as_dict() for a in self.actions],
            'payouts': self.payouts.copy(),
        }
