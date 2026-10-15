"""Educational vanilla CFR for 3-card Kuhn poker, not Texas Hold'em.

This solves a tiny imperfect-information game and checks best-response
exploitability numerically. It is deliberately separate from the NLHE bot.

Run: python -m pokerlab.kuhn_cfr --iterations 20000
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from itertools import permutations, product
from random import Random

CARDS = ('J', 'Q', 'K')


def player_to_act(history: str) -> int:
    return len(history) % 2


def terminal_payoff(history: str, cards: tuple[str, str]) -> int | None:
    """Net winnings to player 0; each antes one chip; bet size = one."""
    if history == 'pp':
        return 1 if CARDS.index(cards[0]) > CARDS.index(cards[1]) else -1
    if history == 'bp':
        return 1  # P0 bet; P1 folded
    if history == 'pbp':
        return -1  # P1 bet; P0 folded
    if history in ('bb', 'pbb'):
        return 2 if CARDS.index(cards[0]) > CARDS.index(cards[1]) else -2
    return None


@dataclass
class InfoSet:
    regret: list[float] = field(default_factory=lambda: [0.0, 0.0])
    strategy_sum: list[float] = field(default_factory=lambda: [0.0, 0.0])

    def strategy(self) -> tuple[float,float]:
        pos = [max(0.0, r) for r in self.regret]
        total = sum(pos)
        return (pos[0] / total, pos[1] / total) if total > 0 else (.5, .5)

    def average(self) -> tuple[float,float]:
        total = sum(self.strategy_sum)
        return (self.strategy_sum[0] / total, self.strategy_sum[1] / total) if total > 0 else (.5,.5)


class CFR:
    def __init__(self, seed: int = 123):
        self.nodes: dict[str,InfoSet] = {}
        self.rng = Random(seed)

    def traverse(self, cards: tuple[str,str], history: str, p0: float, p1: float) -> float:
        payoff = terminal_payoff(history,cards)
        if payoff is not None:
            return float(payoff) if player_to_act(history)==0 else -float(payoff)
        player=player_to_act(history)
        key=cards[player] + history
        node=self.nodes.setdefault(key,InfoSet())
        strat=node.strategy()
        utils=[]
        for i,a in enumerate('pb'):
            if player==0:
                utils.append(-self.traverse(cards,history+a,p0*strat[i],p1))
            else:
                utils.append(-self.traverse(cards,history+a,p0,p1*strat[i]))
        value = sum(s*u for s,u in zip(strat,utils))
        opp_reach = p1 if player==0 else p0
        own_reach = p0 if player==0 else p1
        for i in range(2):
            node.regret[i]+=opp_reach*(utils[i]-value)
            node.strategy_sum[i]+=own_reach*strat[i]
        return value

    def train(self, iterations: int=20000):
        for _ in range(iterations):
            cards=tuple(self.rng.sample(CARDS,2))
            self.traverse(cards,'',1.0,1.0)
        return {k:n.average() for k,n in self.nodes.items()}


def expected_value(policy0: dict, policy1: dict) -> float:
    """Exact average player-0 net payoffs over all six possible deals."""
    def recursive(cards: tuple[str,str], history: str):
        payoff=terminal_payoff(history,cards)
        if payoff is not None: return float(payoff)
        player=player_to_act(history)
        key=cards[player] + history
        probs=(policy0 if player==0 else policy1).get(key,(.5,.5))
        return sum(probs[i]*recursive(cards,history+a) for i,a in enumerate('pb'))
    return sum(recursive(cards,'') for cards in permutations(CARDS,2)) / 6


def exploitability(policy: dict[str,tuple[float,float]]) -> dict:
    """Exact 2-player NashConv: BR0 return minus P0 return against BR1.

    Enumerate the 2^6 pure strategies for each player, respecting infosets.
    Policy of each player is held fixed while the other best responds.
    """
    p0_keys = [c+h for c in CARDS for h in ('','pb')]
    p1_keys = [c+h for c in CARDS for h in ('p','b')]
    pol0 = {k:v for k,v in policy.items() if k in p0_keys}
    pol1 = {k:v for k,v in policy.items() if k in p1_keys}
    br0 = max(expected_value(dict(zip(p0_keys,bits)),pol1)
              for bits in product(((1.,0.),(0.,1.)),repeat=len(p0_keys)))
    br1 = min(expected_value(pol0,dict(zip(p1_keys,bits)))
              for bits in product(((1.,0.),(0.,1.)),repeat=len(p1_keys)))
    value=expected_value(pol0,pol1)
    return {'value_player0':value,'best_response_p0':br0,
            'best_response_p1':br1,'nash_conv':br0-br1,
            'exploitability_per_player':(br0-br1)/2}


def main():
    parser=argparse.ArgumentParser(description='3-card Kuhn poker CFR training')
    parser.add_argument('--iterations',type=int,default=20000)
    parser.add_argument('--seed',type=int,default=123)
    args=parser.parse_args()
    if args.iterations<1: parser.error('iterations must be >= 1')
    solver=CFR(args.seed)
    policy=solver.train(args.iterations)
    scores=exploitability(policy)
    print(f'Kuhn CFR: iterations={args.iterations:,} seed={args.seed}')
    print(f'P0 expected net value: {scores["value_player0"]:+.5f} (theoretical -0.05556)')
    print(f'NashConv (0 = Nash equilibrium): {scores["nash_conv"]:.5f}')
    print(f'Exploitability per player: {scores["exploitability_per_player"]:.5f}')
    for key in sorted(policy):
        print(f'  {key or "-":<3}: check/pass/fold {policy[key][0]:.2%} / bet/call {policy[key][1]:.2%}')
    print('Warning: 3-card Kuhn poker only; it does not imply strength in real Texas Hold\'em.')


if __name__=='__main__':
    main()
