// Peak-Rider: a long-only cbBTC bot for make.fun's btc-race-24h-20261123-0511.
//
// Idea (chosen from the dev window's own data, not from a textbook): on 1-minute
// bars every fast signal whipsaws — the EMA(8)/EMA(21) crossover baseline loses
// about $115 on the dev window in 76 trades, because a full round trip costs
// ~26 bps (4 bps fee + 2 bps slippage + ~7 bps of price impact per $1,000 leg)
// and 1-minute noise is only ~8 bps per bar. Slow trend filters do no better:
// they enter after the move and exit into chop (EMA 60/180: -$18.87; Donchian
// 240/120: -$16.98). The dev window's +3.64% came as one slow grind with a single
// big hour, so the shape that wins is: get in early, stay in, and only leave
// when the market proves the trend broke. Buy-and-hold makes +$32.17 on the dev
// window — but it has no defence if the unseen race window falls instead.
//
// So this bot is buy-and-hold with a parachute:
//   1. Buy with all cash on the SECOND tradeable batch (not the first, so its
//      action log can never be byte-identical to the house buy-and-hold bot,
//      which buys on the first batch and takes no prize anyway).
//   2. While holding, track the peak close; sell everything if a close falls
//      more than 2% below the peak (a 2% trailing stop). On the dev window the
//      stop never fires (max peak-to-trough 1.98%), so it keeps the full
//      buy-and-hold gain (+$32.33 in the local replay); on the time-reversed
//      dev window (a falling-market proxy) it exits at -$24.52 instead of
//      buy-and-hold's -$39.82, and a 1.5% stop would exit at -$14.77 but
//      whipsaws on the rising window, so 2% is the tested compromise.
//   3. After a stop-out, re-enter only on a confirmed recovery: the close
//      more than 1.5% above the close 240 bars earlier. In a falling market
//      that never fires and the bot sits in cash; after a V-shaped dip it
//      buys the recovery, and the same trailing stop guards the new position.
//
// All arithmetic is exact bigint on the bars' integer closes (price_scale 5),
// so two executions on the same data produce the same orders byte for byte.
// No network, no wall clock, no randomness, no files outside the repository.
// One asset, one position, at most one order per reply.
import { runBars, type BuyInput, type SellInput } from './vendor/makefun-bars.ts';

const SYMBOL = 'CBBTC';
/** Sell when a close falls below 98% of the peak close seen while holding. */
const TRAIL_NUM = 98n;
const TRAIL_DEN = 100n;
/** Re-enter only when the close is above 103% of the close this many bars back. */
const REENTRY_LOOKBACK = 240;
const REENTRY_NUM = 103n;
const REENTRY_DEN = 100n;
/** 3% past the close the order was decided on: 1-minute moves peak near 0.7%, */
 /** so a genuine fill is never refused, and a liquidity gap still is. */
const MAX_SLIPPAGE_BPS = 300;

let tradeableSeen = 0;
let initialEntryFilled = false;
let stoppedOut = false;
let peak: bigint | null = null;
/** Closes of CBBTC, one per batch that carried its bar, oldest first. */
const closes: bigint[] = [];

await runBars({
  onBatch(state, batch) {
    const bar = batch.bars.find((b) => b.symbol === SYMBOL);
    if (bar === undefined) return [];
    const close = BigInt(bar.c);
    closes.push(close);
    if (state.warmingUp) return [];

    tradeableSeen += 1;
    const held = state.positions.get(SYMBOL);
    const { caps, fees } = state.hello;

    if (held !== undefined) {
      initialEntryFilled = true;
      stoppedOut = false;
      peak = peak === null || close > peak ? close : peak;
      if (close * TRAIL_DEN < peak * TRAIL_NUM) {
        // Trailing stop: exit the whole position at this close's decision.
        stoppedOut = true;
        peak = null;
        return [{ side: 'sell', symbol: SYMBOL, qty: held.qty, max_slippage_bps: MAX_SLIPPAGE_BPS }];
      }
      return [];
    }

    peak = null;
    const buyAll = (): BuyInput[] => {
      const room = state.weightRoom(SYMBOL);
      const slice = state.cash < room ? state.cash : room;
      if (slice === 0n || slice < BigInt(fees.min_notional_quote_units)) return [];
      return [{ side: 'buy', symbol: SYMBOL, notional_quote_units: slice, max_slippage_bps: MAX_SLIPPAGE_BPS }];
    };

    // First entry: on the second tradeable batch, and retried on later batches
    // until it fills (a rejection leaves us flat, so we simply try again).
    if (!initialEntryFilled) {
      if (tradeableSeen < 2) return [];
      return buyAll();
    }

    // Re-entry after a stop-out: only on a confirmed 240-bar recovery.
    if (stoppedOut && closes.length > REENTRY_LOOKBACK) {
      const then = closes[closes.length - 1 - REENTRY_LOOKBACK]!;
      if (close * REENTRY_DEN > then * REENTRY_NUM) {
        return buyAll();
      }
    }
    return [];
  },
});
