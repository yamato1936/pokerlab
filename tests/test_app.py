import unittest

from pokerlab.bots import RandomBot
from pokerlab.coach import Coach
from pokerlab.engine import HeadsUpHand
from pokerlab.equity import DECK, hand_score, parse_card
from pokerlab.session import Session


class EngineTests(unittest.TestCase):
    def test_blinds_and_position(self):
        h=HeadsUpHand(button=0)
        self.assertEqual(h.pot,3)
        self.assertEqual(h.stacks,[199,198])
        self.assertEqual(h.to_act,0)
        self.assertEqual(h.legal(0)['to_call'],1)
        self.assertEqual(h.legal(0)['min_raise_to'],4)
        h.act(0,'call')
        self.assertEqual(h.to_act,1)
        h.act(1,'check')
        self.assertEqual(h.street,'flop')
        self.assertEqual(len(h.board),3)
        self.assertEqual(h.to_act,1)
        self.assertEqual(h.pot,4)
        self.assertEqual(h.contrib,[0,0])

    def test_raise_and_minimum_reraise(self):
        h=HeadsUpHand()
        h.act(0,'raise',4)
        self.assertEqual(h.legal(1)['min_raise_to'],6)
        self.assertEqual(h.legal(1)['to_call'],2)
        with self.assertRaises(ValueError): h.act(1,'raise',5)
        h.act(1,'raise',12)
        self.assertEqual(h.legal(0)['min_raise_to'],20)
        h.act(0,'call')
        self.assertEqual(h.pot,24)
        self.assertEqual(h.street,'flop')

    def test_fold_and_payout(self):
        h=HeadsUpHand(button=0)
        h.act(0,'fold')
        self.assertTrue(h.finished)
        self.assertEqual(h.winner,1)
        self.assertEqual(h.stacks,[199,201])
        self.assertEqual(h.public_state()['opponent'],None)

    def test_allin_auto_runout(self):
        h=HeadsUpHand()
        h.act(0,'raise',200)
        h.act(1,'call')
        self.assertTrue(h.finished)
        self.assertEqual(len(h.board),5)
        self.assertTrue(h.showdown)
        self.assertEqual(sum(h.stacks),400)
        self.assertEqual(h.pot,400)
        self.assertEqual(len(set(h.holes[0]+h.holes[1]+h.board)),9)

    def test_showdown_shared_board_split(self):
        first=[parse_card(c) for c in '2c 3d 4c 5d 6h As Ks Qs 7h Js 8d Ts'.split()]
        deck=first+[c for c in DECK if c not in first]
        h=HeadsUpHand(deck=deck)
        h.act(0,'call');h.act(1,'check')
        for i in range(3):
            h.act(1,'check');h.act(0,'check')
        self.assertTrue(h.finished)
        self.assertEqual(h.winner,None)
        self.assertEqual(h.stacks,[200,200])
        self.assertEqual(h.public_state()['opponent'],['4c','5d'])

    def test_short_allin_min_raise(self):
        h=HeadsUpHand(starting_stack=9)
        h.act(0,'raise',8)
        self.assertEqual(h.legal(1)['min_raise_to'],9)
        self.assertEqual(h.legal(1)['max_raise_to'],9)
        self.assertTrue(h.legal(1)['is_short_all_in_only'])
        h.act(1,'raise',9)
        self.assertEqual(h.legal(0)['to_call'],1)
        self.assertNotIn('raise',h.legal(0)['actions'])
        h.act(0,'call')
        self.assertEqual(sum(h.stacks),18)

    def test_100_random_games(self):
        bot0,bot1=RandomBot(1),RandomBot(2)
        for n in range(100):
            h=HeadsUpHand(seed=n,button=n%2)
            for _ in range(100):
                if h.finished: break
                seat=h.to_act
                mv=(bot0 if seat==0 else bot1).decide(h,seat)
                h.act(seat,mv.kind,mv.raise_to)
                self.assertEqual(sum(h.stacks)+(0 if h.finished else h.pot),400)
            self.assertTrue(h.finished,(n,h.actions))
            self.assertEqual(sum(h.stacks),400)


class CoachTests(unittest.TestCase):
    def test_no_rival_hole_card_leakage(self):
        h=HeadsUpHand(button=0)
        c1,c2=Coach(trials=80),Coach(trials=80)
        c1.observe(h,0,'call')
        h.holes[1]=[parse_card('Ah'),parse_card('Kh')]
        c2.observe(h,0,'call')
        self.assertEqual(c1.report(),c2.report())

    def test_invalid_action_no_coach_log(self):
        s=Session(seed=5)
        if s.hand.finished: s.new_hand()
        if s.hand.to_act == 0:
            with self.assertRaises(ValueError):
                s.human_action('raise',-1)
            self.assertEqual(s.coach.report(),[])

    def test_session_play(self):
        s=Session(seed=1)
        for i in range(10):
            while not s.hand.finished:
                legal=s.hand.legal(0)
                self.assertEqual(s.hand.to_act,0)
                s.human_action('call' if 'call' in legal['actions'] else 'check')
            self.assertEqual(s.hand_no,i+1)
            self.assertEqual(s.state()['completed_hands'],i+1)
            if i!=9: s.new_hand()


if __name__ == '__main__':
    unittest.main()

class CFRTests(unittest.TestCase):
    def test_kuhn_cfr_convergence(self):
        from pokerlab.kuhn_cfr import CFR, exploitability, expected_value
        learned = CFR(seed=123).train(iterations=30000)
        summary = exploitability(learned)
        self.assertLess(summary['nash_conv'], 0.07, summary)
        self.assertAlmostEqual(summary['value_player0'], -1/18, delta=.06)

    def test_terminal_payouts(self):
        from pokerlab.kuhn_cfr import terminal_payoff
        self.assertEqual(terminal_payoff('pbp', ('K','J')),-1)
        self.assertEqual(terminal_payoff('bp', ('J','K')),1)
        self.assertEqual(terminal_payoff('pbb', ('K','J')),2)
