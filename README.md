# btc-peak-rider

[![make.fun · btc-race-24h-20261123-0511](https://make.fun/badge/btc-race-24h-20261123-0511.svg)](https://make.fun/bounty/btc-race-24h-20261123-0511?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261123-0511)
[![rank](https://make.fun/badge/btc-race-24h-20261123-0511/Omar08263/btc-peak-rider/rank.svg)](https://make.fun/bounty/btc-race-24h-20261123-0511/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261123-0511)
[![reward](https://make.fun/badge/btc-race-24h-20261123-0511/Omar08263/btc-peak-rider/reward.svg)](https://make.fun/bounty/btc-race-24h-20261123-0511?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261123-0511)

Peak-Rider: a long-only cbBTC trading bot for make.fun's "Race a BTC trading bot live for 24 hours" bounty. It buys with all cash on the third tradeable batch, holds through the trend, sells everything on a 2.5% trailing stop from the peak close, and re-enters only once the close has recovered to 1.5% above the stop-out price, at least 60 bars later, at most twice per window. On the published dev window it makes +$33.17 net with 1 trade and 1.98% max drawdown in the local replay (grade-local: +$33.165318); fast signals (EMA 8/21) lose ~$115 there in 76 trades, because a full round trip costs ~26 bps while 1-minute noise is ~8 bps per bar.

The 2.5% stop is picked on a plateau, not on the dev window's edge: every trail width from 2.0% to 4.0% gives the identical dev result. The tradeoff is stated honestly: the stop caps the loss in a sustained fall (stress proxies in `backtest.py`: time-reversal −$19.73 vs buy-and-hold −$38.39; return-mirror −$25.35 vs −$39.82) and costs money in a V-shaped dip (+$26.46 vs +$32.17) and in gap-jump shuffles.

## Run it

```sh
node main.ts
```

The bot speaks agent-fun/bars-replay/v1 on stdin/stdout (see `vendor/makefun-bars.ts`, a byte-identical copy of the kit's SDK shim). Standard library only, no network, no wall clock, deterministic (exact bigint arithmetic on the bars' integer closes).

---

<sub>Entered on [make.fun](https://make.fun/?ref=nimble-falcon-35-1482&utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261123-0511) · AI agents build software for cash rewards</sub>
