"""Panic-dip mean-reversion bot for agent-fun/bars-replay/v1 (cbBTC/USDC, 1m bars).

Idea, in one paragraph: one-minute BTC returns are near-unpredictable, a full
round trip costs about 43 bps (4 bps fee + 2 bps slippage + ~15 bps impact per
leg at this pool's depth), and the dev window trends down, so frequent trading
bleeds. The bot therefore stays in cash most of the day and only buys two
setups that backtested positive on the dev window and on four out-of-sample
days (7-11 Nov 2026, same pool):

  Tier A -- panic dip: the close falls 300 bps or more below its 360-bar mean
  (a -7% intraday washout in the dev window). Buy the whole cash balance and
  ride the snap-back: take profit at +500 bps, stop at -200 bps, trailing
  stop 100 bps off the peak, max hold 480 bars.
  Tier B -- bounce: the close recovers 40 bps off its 120-bar low while still
  100 bps below its 240-bar mean. Buy half the cash, take profit at +100 bps,
  stop at -80 bps, max hold 240 bars. Tier B keeps the bot trading (and the
  guardrail met) on days with no panic dip.

If Tier A fires while a Tier B position is held, the B position is sold at
once so the bigger setup can be taken on the next bar. The bot is long only,
holds at most one position, never uses the clock, the network, or unseeded
randomness, and every decision is a pure function of the closes seen so far,
so two runs on the same bars answer byte for byte alike.

All prices here are raw integer units from the harness (price_scale 5); the
ratios below are in basis points and are computed in float64, which is
deterministic for the same inputs on every run.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))

import makefun_bars

SYMBOL = "CBBTC"
MAX_SLIPPAGE_BPS = 100  # 1% past the close the order was decided on

# Tier A -- panic dip off the long mean.
A_MEAN_BARS = 360
A_DIP_BPS = 300
A_TAKE_PROFIT_BPS = 500
A_STOP_LOSS_BPS = 200
A_TRAILING_BPS = 100
A_MAX_HOLD_BARS = 480

# Tier B -- bounce off the rolling low, still deep below the medium mean.
B_LOW_BARS = 120
B_MEAN_BARS = 240
B_BOUNCE_BPS = 40
B_BELOW_MEAN_BPS = 100
B_TAKE_PROFIT_BPS = 100
B_STOP_LOSS_BPS = 80
B_MAX_HOLD_BARS = 240
B_SIZE_FRACTION = 0.5


class PanicDipBot:
    """Keeps the closes seen so far and the one open position's entry."""

    def __init__(self):
        # Closes, oldest first, capped at the longest lookback we need.
        self.closes = []
        # Entry of the open position: close it was decided on, batch it was
        # decided on, best return since entry (bps), and which tier bought it.
        self.entry_close = None
        self.entry_seq = None
        self.peak_return_bps = None
        self.tier = None

    def _mean(self, bars):
        """Mean of the last `bars` closes (float, deterministic)."""
        window = self.closes[-bars:]
        return sum(window) / len(window)

    def _tier_a_fires(self, close):
        """True when the close is A_DIP_BPS or more below the long mean."""
        if len(self.closes) < A_MEAN_BARS:
            return False
        return close < self._mean(A_MEAN_BARS) * (1 - A_DIP_BPS / 10000)

    def _tier_b_fires(self, close):
        """True on the first bar the close recovers B_BOUNCE_BPS off the low
        while still B_BELOW_MEAN_BPS under the medium mean. The low is
        measured over the last B_LOW_BARS bars plus the current one, so the
        window below holds B_LOW_BARS + 1 closes ending now."""
        if len(self.closes) < B_MEAN_BARS:
            return False
        low = min(self.closes[-B_LOW_BARS - 1:])
        bounced = close >= low * (1 + B_BOUNCE_BPS / 10000)
        just_crossed = self.closes[-2] < low * (1 + B_BOUNCE_BPS / 10000)
        still_deep = close < self._mean(B_MEAN_BARS) * (1 - B_BELOW_MEAN_BPS / 10000)
        return bounced and just_crossed and still_deep

    def _open(self, close, seq, tier):
        self.entry_close = close
        self.entry_seq = seq
        self.peak_return_bps = 0.0
        self.tier = tier

    def _close_position(self):
        self.entry_close = None
        self.entry_seq = None
        self.peak_return_bps = None
        self.tier = None

    def _sell_order(self, state):
        held = state.positions.get(SYMBOL)
        return [{
            "side": "sell",
            "symbol": SYMBOL,
            "qty": held.qty,
            "max_slippage_bps": MAX_SLIPPAGE_BPS,
        }]

    def on_batch(self, state, batch):
        # A batch with no bar for our symbol carries nothing to decide on.
        close = state.close(SYMBOL)
        if close is None or state.warming_up:
            return []
        self.closes.append(close)
        if len(self.closes) > A_MEAN_BARS:
            self.closes.pop(0)

        panic = self._tier_a_fires(close)

        if state.positions.get(SYMBOL) is not None:
            ret_bps = (close / self.entry_close - 1) * 10000
            if ret_bps > self.peak_return_bps:
                self.peak_return_bps = ret_bps
            # The panic setup outranks a bounce position: free the slot now
            # so Tier A can be bought on the next bar.
            if self.tier == "B" and panic:
                self._close_position()
                return self._sell_order(state)
            if self.tier == "A":
                take, stop, hold, trail = (
                    A_TAKE_PROFIT_BPS, A_STOP_LOSS_BPS,
                    A_MAX_HOLD_BARS, A_TRAILING_BPS,
                )
            else:
                take, stop, hold, trail = (
                    B_TAKE_PROFIT_BPS, B_STOP_LOSS_BPS,
                    B_MAX_HOLD_BARS, None,
                )
            give_up = (
                ret_bps >= take
                or ret_bps <= -stop
                or state.seq - self.entry_seq >= hold
                or (trail is not None and ret_bps <= self.peak_return_bps - trail)
            )
            if give_up:
                self._close_position()
                return self._sell_order(state)
            return []

        if len(self.closes) < A_MEAN_BARS:
            return []
        if panic:
            self._open(close, state.seq, "A")
            return [{
                "side": "buy",
                "symbol": SYMBOL,
                "notional_quote_units": state.cash,
                "max_slippage_bps": MAX_SLIPPAGE_BPS,
            }]
        if self._tier_b_fires(close):
            self._open(close, state.seq, "B")
            return [{
                "side": "buy",
                "symbol": SYMBOL,
                "notional_quote_units": int(state.cash * B_SIZE_FRACTION),
                "max_slippage_bps": MAX_SLIPPAGE_BPS,
            }]
        return []


makefun_bars.run(PanicDipBot().on_batch)
