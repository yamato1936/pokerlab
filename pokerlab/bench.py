"""Reproducible baseline-vs-random matches; terminal output is NOT proof of GTO strength."""
from __future__ import annotations

import argparse
from math import sqrt
from random import Random
from time import perf_counter

from .bots import EquityBot, RandomBot
from .engine import HeadsUpHand


def benchmark(hands: int, seed: int = 42, trials: int = 120):
    if hands < 2:
        raise ValueError('minimum 2 hands required')
    random = Random(seed)
    strong = EquityBot(seed + 1, trials=trials)
    baseline = RandomBot(seed + 2)
    profits = []
    t0 = perf_counter()
    for i in range(hands):
        hand = HeadsUpHand(seed=random.randrange(1 << 30),button=i%2)
        for n in range(100):
            if hand.finished: break
            seat = hand.to_act
            move = (strong if seat == 0 else baseline).decide(hand, seat)
            hand.act(seat, move.kind, move.raise_to)
        if not hand.finished:
            raise RuntimeError(f'hand {i} did not terminate')
        profits.append(hand.stacks[0] - hand.starting_stack)
    # Results: profit in chips; bb=2, so per hand chip/2; bb/100 = sum(chips)*50 / N.
    mean = sum(profits) / hands
    stddev = sqrt(sum((x-mean)**2 for x in profits) / (hands-1))
    bb100 = mean / 2 * 100
    stderr_bb100 = stddev / 2 * 100 / sqrt(hands)
    return {'hands':hands, 'bb_per_100':bb100,
            'ci95':(bb100-1.96*stderr_bb100,bb100+1.96*stderr_bb100),
            'elapsed':perf_counter()-t0, 'total_chips':sum(profits)}


def main():
    parser=argparse.ArgumentParser(description='EquityBot vs RandomBot (not GTO validation)')
    parser.add_argument('--hands',type=int,default=200)
    parser.add_argument('--trials',type=int,default=120)
    parser.add_argument('--seed',type=int,default=42)
    args=parser.parse_args()
    result=benchmark(args.hands,args.seed,args.trials)
    print(f'EquityBot vs RandomBot: {result["hands"]} hands / {result["elapsed"]:.2f} s')
    print(f'Net: {result["total_chips"]:+d} chips')
    print(f'bb/100 = {result["bb_per_100"]:+.2f} (naive 95% CI {result["ci95"][0]:+.2f} to {result["ci95"][1]:+.2f})')
    print('Warning: estimates are noisy; this tests only one weak opponent, not exploitability / GTO.')


if __name__=='__main__':
    main()
