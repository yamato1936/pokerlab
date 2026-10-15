"""Session orchestration; bot action and local training metrics."""
from __future__ import annotations

from random import Random

from .bots import EquityBot
from .coach import Coach
from .engine import HeadsUpHand


class Session:
    def __init__(self, seed: int = 42):
        self.rng = Random(seed)
        self.bot = EquityBot(seed=seed + 1)
        self.hand_no = 0
        self.history: list[dict] = []
        self.hand: HeadsUpHand
        self.coach: Coach
        self.new_hand()

    def new_hand(self):
        if hasattr(self, 'hand') and not self.hand.finished:
            raise ValueError('現在のハンドが終わっていません')
        self.coach = Coach()
        self.hand = HeadsUpHand(seed=self.rng.randrange(1 << 30),
                                button=(self.hand_no % 2))
        self.hand_no += 1
        self._bot_turns()
        return self.state()

    def _bot_turns(self):
        for _ in range(100):
            if self.hand.finished or self.hand.to_act != 1:
                return
            move = self.bot.decide(self.hand, 1)
            self.hand.act(1, move.kind, move.raise_to)
        raise RuntimeError('bot exceeded maximum decisions')

    def human_action(self, kind: str, raise_to: int | None = None):
        if self.hand.to_act != 0:
            raise ValueError('現在は人間のターンではありません')
        legal = self.hand.legal(0)
        # Validate first: invalid requests must not produce coach records.
        if kind not in legal['actions']:
            raise ValueError('不正なアクションです')
        if kind == 'raise' and (type(raise_to) is not int or not
                legal['min_raise_to'] <= raise_to <= legal['max_raise_to']):
            raise ValueError('不正なレイズ額です')
        self.coach.observe(self.hand, 0, kind)
        self.hand.act(0, kind, raise_to)
        self._bot_turns()
        if self.hand.finished:
            self._record_completed_hand()
        return self.state()

    def _record_completed_hand(self):
        # No private opponent hole cards in trainer feedback unless showdown.
        if self.history and self.history[-1]['number'] == self.hand_no:
            return
        self.history.append({
            'number': self.hand_no,
            'net_chips': self.hand.stacks[0] - self.hand.starting_stack,
            'winner': self.hand.winner,
            'reason': self.hand.result_reason,
            'decisions': self.coach.report(),
        })

    def state(self):
        state = self.hand.public_state()
        state.update({'hand_number': self.hand_no,
                      'decisions': self.coach.report(),
                      'completed_hands': len(self.history),
                      'net_chips': sum(h['net_chips'] for h in self.history),
                      'recent_hands': [{k:v for k,v in h.items() if k != 'decisions'}
                                       for h in self.history[-8:][::-1]],
                      'note': 'エクイティはランダムな相手カードへの推定です。GTO解析ではありません。'})
        return state
