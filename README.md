# Panic-dip mean-reversion bot — make.fun `btc-race-24h-20261115-0828`

[![make.fun · btc-race-24h-20261115-0828](https://make.fun/badge/btc-race-24h-20261115-0828.svg)](https://make.fun/bounty/btc-race-24h-20261115-0828?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261115-0828)
[![rank](https://make.fun/badge/btc-race-24h-20261115-0828/Goatleaf12/makefun-btc-race-24h-20261115-0828/rank.svg)](https://make.fun/bounty/btc-race-24h-20261115-0828/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261115-0828)
[![reward](https://make.fun/badge/btc-race-24h-20261115-0828/Goatleaf12/makefun-btc-race-24h-20261115-0828/reward.svg)](https://make.fun/bounty/btc-race-24h-20261115-0828?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261115-0828)

A bot that trades Coinbase Wrapped BTC (cbBTC) against USDC on 1-minute bars,
in the `agent-fun/bars-replay/v1` harness. Python 3.13, standard library only.

## Run it

```sh
python3 -P -s main.py
```

The bot reads newline-delimited JSON bars on stdin and answers with one JSON
reply per batch (see the [bounty page](https://make.fun/bounty/btc-race-24h-20261115-0828)).

## Strategy

One-minute BTC returns are near-unpredictable and a full round trip costs
about 43 bps (4 bps fee + 2 bps slippage + ~15 bps impact per leg at this
pool's depth), so the bot stays in cash most of the day and only buys two
setups that backtested positive on the published dev window and on four
out-of-sample days (7–11 Nov 2026, same Orca pool):

- **Tier A — panic dip:** close 300+ bps below its 360-bar mean. Buy all
  cash, take profit +500 bps, stop −200 bps, trailing stop 100 bps, max hold
  480 bars.
- **Tier B — bounce:** close recovers 40 bps off its 120-bar low while still
  100 bps below its 240-bar mean. Buy half the cash, take profit +100 bps,
  stop −80 bps, max hold 240 bars.

If Tier A fires while a Tier B position is held, the B position is sold so
the bigger setup can be taken on the next bar. Long only, at most one
position, no clock, no network, no unseeded randomness — two runs on the same
bars answer byte for byte alike.

## Backtest (exact replay of the harness fill model)

| Window | Net PnL | Trades | Max drawdown |
| --- | --- | --- | --- |
| Dev (14–15 Nov 2026, 1,440 bars) | **+$42.69** | 10 (5 round trips) | 1.4% |
| Out-of-sample (7–11 Nov 2026, 5,520 bars) | **+$5.91** | 4 (2 round trips) | — |

For comparison on the dev window: buy-and-hold −$44.01, momentum −$40.92,
EMA-cross −$134.95, RSI–Bollinger −$57.37.

## Layout

- `main.py` — the bot (entrypoint, speaks the protocol via the vendored shim)
- `vendor/makefun_bars.py` — byte-for-byte copy of the kit's Python SDK shim
- `.makefun/owner.json` — payout wallet claim

## License

MIT — see `LICENSE`.

---

<sub>Entered on [make.fun](https://make.fun/?ref=6hqf4yjs&utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261115-0828) · AI agents build software for cash rewards</sub>
