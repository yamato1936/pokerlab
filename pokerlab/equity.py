#!/usr/bin/env python3
"""Poker Lab v0.1 — offline heads-up Texas Hold'em equity explorer.

No external dependencies, no servers, no account required.
This is an EQUITY CALCULATOR against a uniform-random opponent, not a GTO bot.

Example:
    python poker_lab.py --hero As Ks --board Qs Js 2d --pot 100 --call 25
    python poker_lab.py --hero Ah Ad --trials 10000
    python poker_lab.py --self-test
"""
from __future__ import annotations

import argparse
from collections import Counter
from itertools import combinations
from math import sqrt
from random import Random
from time import perf_counter

RANKS = '23456789TJQKA'
SUITS = 'cdhs' # clubs, diamonds, hearts, spades
DECK = tuple(range(52))
HAND_NAMES = ('ハイカード', 'ワンペア', 'ツーペア', 'スリーカード', 'ストレート',
              'フラッシュ', 'フルハウス', 'フォーカード', 'ストレートフラッシュ')


def parse_card(text: str) -> int:
    """'As' (ace of spades) -> integer card ID."""
    text = text.strip()
    if len(text) != 2 or text[0].upper() not in RANKS or text[1].lower() not in SUITS:
        raise ValueError(f'不正なカード: {text!r}。例: As, Kh, Td, 2c')
    return RANKS.index(text[0].upper()) * 4 + SUITS.index(text[1].lower())


def format_card(card: int) -> str:
    return RANKS[card // 4] + SUITS[card % 4]


def straight_high(ranks) -> int:
    """Return highest straight top rank; A2345 is 5-high."""
    mask = 0
    for r in ranks:
        mask |= 1 << r
    if mask & (1 << 14):
        mask |= 1 << 1
    for high in range(14, 4, -1):
        if (mask >> (high - 4)) & 0b11111 == 0b11111:
            return high
    return 0


def hand_score(cards: list[int] | tuple[int, ...]) -> tuple[int, ...]:
    """Rank the best five cards in a 5–7 card holding; larger wins."""
    if not 5 <= len(cards) <= 7 or len(cards) != len(set(cards)):
        raise ValueError('評価には重複なしの5～7枚が必要です')
    ranks = [c // 4 + 2 for c in cards]
    suits = [c % 4 for c in cards]
    counts = Counter(ranks)
    flush_suit = next((s for s in range(4) if suits.count(s) >= 5), None)
    if flush_suit is not None:
        suited_ranks = [r for r, s in zip(ranks, suits) if s == flush_suit]
        sf = straight_high(suited_ranks)
        if sf:
            return (8, sf)

    quads = sorted((r for r, n in counts.items() if n == 4), reverse=True)
    if quads:
        return (7, quads[0], max(r for r in ranks if r != quads[0]))

    trips = sorted((r for r, n in counts.items() if n >= 3), reverse=True)
    if trips:
        pairs_for_house = sorted((r for r, n in counts.items()
                                  if n >= 2 and r != trips[0]), reverse=True)
        if pairs_for_house:
            return (6, trips[0], pairs_for_house[0])

    if flush_suit is not None:
        return (5, *sorted(suited_ranks, reverse=True)[:5])

    st = straight_high(ranks)
    if st:
        return (4, st)

    if trips:
        kickers = sorted((r for r in ranks if r != trips[0]), reverse=True)[:2]
        return (3, trips[0], *kickers)

    pairs = sorted((r for r, n in counts.items() if n >= 2), reverse=True)
    if len(pairs) >= 2:
        kicker = max(r for r in ranks if r not in pairs[:2])
        return (2, pairs[0], pairs[1], kicker)
    if pairs:
        kickers = sorted((r for r in ranks if r != pairs[0]), reverse=True)[:3]
        return (1, pairs[0], *kickers)
    return (0, *sorted(ranks, reverse=True)[:5])


def simulate_equity(hero: list[int], board: list[int], trials: int, seed: int):
    """Heads-up against uniformly random legal opponent hole cards.

    Equity = P(win) + 0.5 P(tie). Unknown community cards are sampled.
    """
    known = set(hero + board)
    if len(hero) != 2 or len(known) != len(hero) + len(board):
        raise ValueError('自分のカードは2枚、カードの重複は禁止です')
    if len(board) not in (0, 3, 4, 5):
        raise ValueError('場のカード枚数は0/3/4/5枚です')
    if trials < 1:
        raise ValueError('trialsは1以上にしてください')
    remaining = [c for c in DECK if c not in known]
    rng = Random(seed)
    wins = ties = 0
    start = perf_counter()
    for _ in range(trials):
        drawn = rng.sample(remaining, 2 + 5 - len(board))
        opp = drawn[:2]
        completed_board = board + drawn[2:]
        ours = hand_score(hero + completed_board)
        theirs = hand_score(opp + completed_board)
        if ours > theirs:
            wins += 1
        elif ours == theirs:
            ties += 1
    elapsed = perf_counter() - start
    equity = (wins + 0.5 * ties) / trials
    second_moment = (wins + 0.25 * ties) / trials
    variance = max(0.0, (second_moment - equity * equity) * trials / max(trials - 1, 1))
    margin = 1.96 * sqrt(variance / trials)
    return {
        'equity': equity, 'low': max(0, equity - margin),
        'high': min(1, equity + margin), 'win': wins / trials,
        'tie': ties / trials, 'loss': (trials - wins - ties) / trials,
        'elapsed': elapsed, 'trials': trials,
    }


def _reference_five(cards):
    """Independent exhaustive 5-card ranking for test-only cross-checks."""
    rr = sorted((c // 4 + 2 for c in cards), reverse=True)
    freq = Counter(rr)
    same_suit = len({c % 4 for c in cards}) == 1
    uniq = sorted(set(rr), reverse=True)
    straight = 5 if uniq == [14, 5, 4, 3, 2] else (uniq[0] if len(uniq) == 5 and uniq[0] - uniq[-1] == 4 else 0)
    order = sorted(((n, r) for r, n in freq.items()), reverse=True)
    if same_suit and straight:
        return (8, straight)
    if order[0][0] == 4:
        return (7, order[0][1], order[1][1])
    if [v[0] for v in order] == [3, 2]:
        return (6, order[0][1], order[1][1])
    if same_suit:
        return (5, *rr)
    if straight:
        return (4, straight)
    if order[0][0] == 3:
        return (3, order[0][1], *sorted((r for r in rr if r != order[0][1]), reverse=True))
    if [v[0] for v in order][:2] == [2, 2]:
        ps = sorted((r for r, n in freq.items() if n == 2), reverse=True)
        return (2, *ps, next(r for r in rr if r not in ps))
    if order[0][0] == 2:
        return (1, order[0][1], *[r for r in rr if r != order[0][1]])
    return (0, *rr)


def self_test():
    # Special situations: ace-low straight; double trips; flush-vs-straight.
    known_cases = [
        ('As 2d 3h 4c 5s 9d Qc', 4),
        ('Ah Ad Ac Kh Kc Kd 2s', 6),
        ('As Ks Qs Js Ts 2h 3d', 8),
        ('Ac Ad Ah As 9s 2h 3d', 7),
        ('2c 3c 4c 5c 7c 9h Td', 5),
    ]
    for case, category in known_cases:
        cards = [parse_card(c) for c in case.split()]
        assert hand_score(cards)[0] == category, case
    rng = Random(9)
    for _ in range(2000):
        cards = rng.sample(DECK, 7)
        expected = max(_reference_five(hand) for hand in combinations(cards, 5))
        assert hand_score(cards) == expected, (cards, hand_score(cards), expected)
    print('PASS: 2,000ランダム7枚手札＋既知エッジケースの評価が一致')


def main():
    parser = argparse.ArgumentParser(description='Poker Lab v0.1 (完全オフライン・追加ライブラリ不要)')
    parser.add_argument('--hero', nargs=2, metavar=('CARD1', 'CARD2'), help='自分の2枚。例: As Ks')
    parser.add_argument('--board', nargs='*', default=[], metavar='CARD', help='共有カード。例: Qs Js 2d')
    parser.add_argument('--pot', type=float, default=None, help='現在のポット。相手のベットを含む、コール前の総額')
    parser.add_argument('--call', type=float, default=None, help='コールに必要な追加チップ')
    parser.add_argument('--trials', type=int, default=5000, help='乱数試行回数 (default: 5000)')
    parser.add_argument('--seed', type=int, default=42, help='再現用乱数シード (default: 42)')
    parser.add_argument('--self-test', action='store_true', help='役判定のテストを実行')
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if not args.hero:
        parser.error('--hero でカードを2枚指定してください')
    try:
        hero = list(map(parse_card, args.hero))
        board = list(map(parse_card, args.board))
        stats = simulate_equity(hero, board, args.trials, args.seed)
        if (args.pot is None) != (args.call is None):
            raise ValueError('--pot と --call は両方指定するか、両方省略してください')
        if args.pot is not None and (args.pot < 0 or args.call < 0 or args.call > args.pot):
            raise ValueError('0 <= call <= pot が必要です（potは現在の総額）')
    except ValueError as exc:
        parser.error(str(exc))
    print('\n=== Poker Lab v0.1 / オフライン勝率実験 ===')
    print('自分:         ', ' '.join(format_card(c) for c in hero))
    print('共有カード:   ', ' '.join(format_card(c) for c in board) or '(プリフロップ)')
    if len(board) == 5:
        print('現時点の役:   ', HAND_NAMES[hand_score(hero + board)[0]])
    print('相手モデル:    ランダムに選ばれた合法的な2枚 (1対1)')
    print(f"勝ち/引分/負け: {stats['win']:.1%} / {stats['tie']:.1%} / {stats['loss']:.1%}")
    print(f"エクイティ:    {stats['equity']:.2%} (約95% CI {stats['low']:.2%}～{stats['high']:.2%})")
    print(f"試行回数:      {args.trials:,} / 実行時間: {stats['elapsed']*1000:.1f} ms")
    if args.pot is not None:
        # POT ALREADY INCLUDES THE OPPONENT'S BET, but NOT the hero's call.
        # Final pot after calling is P + C; incremental call EV is e(P+C) - C.
        final_pot = args.pot + args.call
        threshold = args.call / final_pot if final_pot > 0 else 0.0
        ev = stats['equity'] * final_pot - args.call
        print(f'必要な最低エクイティ: {threshold:.2%} (call / (pot + call))')
        print(f'簡易コールEV: {ev:+.2f} チップ（この1回のコールに対する推定）')
        if stats['low'] > threshold:
            judgment = 'Call候補（単純モデルでは期待値プラス）'
        elif stats['high'] < threshold:
            judgment = 'Fold候補（単純モデルでは期待値マイナス）'
        else:
            judgment = '判断保留（推定の誤差範囲）'
        print('簡易判断:     ', judgment)
    print('\n注意: 相手のハンドレンジ・ブラフ・今後のベットを無視しています。')
    print('      強いポーカーAIやGTOソルバーの判断とは異なります。\n')


if __name__ == '__main__':
    main()
