import unittest

from limiter import clamp_rps, next_due_ts, refill_tokens


class LimiterTests(unittest.TestCase):
    def test_clamp_rps(self):
        self.assertEqual(clamp_rps(0), 1)
        self.assertEqual(clamp_rps(1), 1)
        self.assertEqual(clamp_rps(10), 10)
        self.assertEqual(clamp_rps(11), 10)

    def test_refill_tokens_caps_burst(self):
        # rps=5, burst cap = 5 tokens
        tokens, ts = refill_tokens(tokens=0.0, last_ts=0.0, now=100.0, rps=5)
        self.assertEqual(ts, 100.0)
        self.assertEqual(tokens, 0.0)

        tokens, ts = refill_tokens(tokens=0.0, last_ts=100.0, now=101.0, rps=5)
        self.assertAlmostEqual(tokens, 5.0)

        tokens, ts = refill_tokens(tokens=4.0, last_ts=101.0, now=103.0, rps=5)
        # would be 4 + 2*5 = 14, capped to 5
        self.assertAlmostEqual(tokens, 5.0)

    def test_next_due_ts(self):
        now = 100.0
        self.assertEqual(next_due_ts(tokens=1.0, rps=5, now=now), now)
        self.assertEqual(next_due_ts(tokens=2.0, rps=5, now=now), now)

        # tokens=0.0, need 1 token at rps=4 => 0.25s
        self.assertAlmostEqual(next_due_ts(tokens=0.0, rps=4, now=now), 100.25)

        # tokens=0.5 => need 0.5 => 0.125s
        self.assertAlmostEqual(next_due_ts(tokens=0.5, rps=4, now=now), 100.125)


if __name__ == "__main__":
    unittest.main()
