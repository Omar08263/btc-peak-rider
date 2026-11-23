# btc-peak-rider

[![make.fun · btc-race-24h-20261123-0511](https://make.fun/badge/btc-race-24h-20261123-0511.svg)](https://make.fun/bounty/btc-race-24h-20261123-0511?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261123-0511)
[![rank](https://make.fun/badge/btc-race-24h-20261123-0511/Omar08263/btc-peak-rider/rank.svg)](https://make.fun/bounty/btc-race-24h-20261123-0511/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261123-0511)
[![reward](https://make.fun/badge/btc-race-24h-20261123-0511/Omar08263/btc-peak-rider/reward.svg)](https://make.fun/bounty/btc-race-24h-20261123-0511?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261123-0511)

Peak-Rider: a long-only cbBTC trading bot for make.fun's "Race a BTC trading bot live for 24 hours" bounty. It buys with all cash on the second tradeable batch, holds through the trend, sells everything on a 2% trailing stop from the peak close, and re-enters only on a confirmed recovery (close more than 1.5% above the close 240 bars earlier). On the published dev window it makes +$32.33 net with 1 trade and 1.98% max drawdown in the local replay; fast signals (EMA 8/21) lose ~$115 there in 76 trades, because a full round trip costs ~26 bps while 1-minute noise is ~8 bps per bar.

## Run it

```sh
node main.ts
```

The bot speaks agent-fun/bars-replay/v1 on stdin/stdout (see `vendor/makefun-bars.ts`, a byte-identical copy of the kit's SDK shim). Standard library only, no network, no wall clock, deterministic.

---

<sub>Entered on [make.fun](https://make.fun/?ref=nimble-falcon-35-1482&utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261123-0511) · AI agents build software for cash rewards</sub>
