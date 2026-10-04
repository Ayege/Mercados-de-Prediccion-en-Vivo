import math
import random

from app.domain import lmsr


def test_initial_price_is_even():
    assert lmsr.prices([0, 0], 100) == [0.5, 0.5]


def test_prices_sum_to_one():
    p = lmsr.prices([37.2, -5.1], 50)
    assert math.isclose(sum(p), 1.0)


def test_shares_for_spend_matches_cost_function():
    q, b = [10.0, 3.0], 80.0
    shares = lmsr.shares_for_spend(q, b, 0, 25.0)
    after = [q[0] + shares, q[1]]
    assert math.isclose(lmsr.cost(after, b) - lmsr.cost(q, b), 25.0, rel_tol=1e-9)


def test_buying_yes_raises_yes_price():
    q, b = [0.0, 0.0], 100.0
    s = lmsr.shares_for_spend(q, b, 0, 50)
    assert lmsr.prices([s, 0.0], b)[0] > 0.5


def test_creator_loss_is_bounded_by_b_ln2():
    rng = random.Random(7)
    b = 100.0
    q = [0.0, 0.0]
    collected = 0.0
    for _ in range(300):
        i = rng.randint(0, 1)
        spend = rng.uniform(1, 200)
        q[i] += lmsr.shares_for_spend(q, b, i, spend)
        collected += spend
    worst_payout = max(q)
    assert worst_payout - collected <= b * math.log(2) + 1e-6
