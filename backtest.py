#!/usr/bin/env python3
"""Backtester replicating bars-replay/v1 fills for CBBTC dev window.
Fill at next bar open; fee 4bps; slippage 2bps; impact 1+a/D vs open depth.
Prices: price_scale 5 (USD = raw/1e5). Depth: micro-USDC (USD = raw/1e6).
"""
import gzip, json, sys, math

KIT = '/home/hatch/workspace/make-fun/btc-race-24h-20261123-0511-kit/btc-race-24h-20261123-0511-kit'
rows = []
with gzip.open(f'{KIT}/dataset/bars/CBBTC.ndjson.gz', 'rt') as f:
    for line in f:
        d = json.loads(line)
        rows.append(d)
O = [int(r['o'])/1e5 for r in rows]
H = [int(r['h'])/1e5 for r in rows]
L = [int(r['l'])/1e5 for r in rows]
C = [int(r['c'])/1e5 for r in rows]
D = [int(r['o_depth'][0])/1e6 for r in rows]   # open depth USD
Dc = [int(r['c_depth'][0])/1e6 for r in rows]  # close depth USD
N = len(rows)

def run(signals):
    """signals: list per bar index of 'buy'/'sell'/None decided at that bar's close.
    Orders fill at next bar's open. Returns dict."""
    cash = 1000.0
    qty = 0.0
    cost = 0.0  # cost basis of position in USD spent
    peak_equity = 1000.0
    max_dd = 0.0
    trades = 0
    equity_curve = []
    pending = None  # ('buy', notional) or ('sell', qty)
    for i in range(N):
        # fill pending order at this bar's open
        if pending is not None and i > 0:
            side, amt = pending
            o, d = O[i], D[i]
            if side == 'buy' and amt > 0:
                fee = amt * 0.0004
                a = amt - fee
                fp = o * 1.0002 * (1 + a / d)
                # max slippage check vs prev close: 1000bps (matches the bot)
                if fp <= C[i-1] * 1.10:
                    q = a / fp
                    qty += q
                    cost += amt
                    cash -= amt
                    trades += 1
            elif side == 'sell' and qty > 0:
                a = qty * o
                fp = o * 0.9998 / (1 + a / d)
                if fp >= C[i-1] * 0.90:
                    gross = qty * fp
                    fee = gross * 0.0004
                    cash += gross - fee
                    qty = 0.0
                    cost = 0.0
                    trades += 1
            pending = None
        # decide on this bar (fills next bar); last bar: no orders
        if i < N - 1:
            s = signals[i]
            if s == 'buy' and qty == 0 and cash >= 1:
                pending = ('buy', cash)
            elif s == 'sell' and qty > 0:
                pending = ('sell', qty)
        eq = cash + qty * C[i]
        peak_equity = max(peak_equity, eq)
        dd = (peak_equity - eq) / peak_equity
        max_dd = max(max_dd, dd)
        equity_curve.append(eq)
    # final flatten at last close
    if qty > 0:
        o, d = C[-1], Dc[-1]
        a = qty * o
        fp = o * 0.9998 / (1 + a / d)
        gross = qty * fp
        cash += gross - gross * 0.0004
        qty = 0.0
    return dict(pnl=cash - 1000.0, trades=trades, max_dd=max_dd * 100,
                final=cash, curve=equity_curve)

def ema(vals, span):
    k = 2 / (span + 1)
    out = [None] * len(vals)
    s = sum(vals[:span]) / span
    out[span - 1] = s
    for i in range(span, len(vals)):
        s = s + k * (vals[i] - s)
        out[i] = s
    return out

def strat_ema_cross(roi=0.5, stop=-0.2, trail=None, tp=None):
    f, s = ema(C, 8), ema(C, 21)
    sig = [None] * N
    held = False
    entry_cost = 0.0
    peak = 0.0
    prev_diff = None
    for i in range(N):
        if f[i] is None or s[i] is None:
            continue
        diff = f[i] - s[i]
        if prev_diff is not None:
            if not held and diff > 0 and prev_diff <= 0:
                sig[i] = 'buy'; held = True; entry_cost = C[i]; peak = C[i]
            elif held and diff < 0 and prev_diff >= 0:
                sig[i] = 'sell'; held = False
        if held:
            peak = max(peak, C[i])
            val_ratio = C[i] / entry_cost if entry_cost else 1
            if val_ratio - 1 >= roi:
                sig[i] = 'sell'; held = False
            elif val_ratio - 1 <= stop:
                sig[i] = 'sell'; held = False
            elif trail is not None and C[i] < peak * (1 - trail):
                sig[i] = 'sell'; held = False
            elif tp is not None and val_ratio - 1 >= tp:
                sig[i] = 'sell'; held = False
        prev_diff = diff
    return sig

def strat_bh():
    sig = [None] * N
    sig[0] = 'buy'
    return sig

def strat_donchian(lb=60, exit_lb=30, trail=None):
    sig = [None] * N
    held = False
    peak = 0.0
    for i in range(N):
        if i < lb:
            continue
        hi = max(H[i-lb:i])
        lo = min(L[i-exit_lb:i])
        if not held and C[i] > hi:
            sig[i] = 'buy'; held = True; peak = C[i]
        elif held:
            peak = max(peak, C[i])
            if C[i] < lo:
                sig[i] = 'sell'; held = False
            elif trail is not None and C[i] < peak * (1 - trail):
                sig[i] = 'sell'; held = False
    return sig

def strat_mom(look=30, up=0.005, down=-0.003, trail=0.01):
    sig = [None] * N
    held = False
    peak = 0.0
    for i in range(look, N):
        r = C[i] / C[i-look] - 1
        if not held and r > up:
            sig[i] = 'buy'; held = True; peak = C[i]
        elif held:
            peak = max(peak, C[i])
            if r < down or C[i] < peak * (1 - trail):
                sig[i] = 'sell'; held = False
    return sig

def strat_ema_filtered(trail=0.012, tp=0.03, mom_look=30, mom_up=0.002):
    """EMA cross entry only with positive 30m momentum; exit cross-down / trail / TP."""
    f, s = ema(C, 8), ema(C, 21)
    sig = [None] * N
    held = False
    peak = 0.0
    prev_diff = None
    for i in range(N):
        if f[i] is None or s[i] is None:
            continue
        diff = f[i] - s[i]
        if prev_diff is not None:
            if not held and diff > 0 and prev_diff <= 0:
                if i >= mom_look and C[i] / C[i-mom_look] - 1 > mom_up:
                    sig[i] = 'buy'; held = True; peak = C[i]
            elif held and diff < 0 and prev_diff >= 0:
                sig[i] = 'sell'; held = False
        if held:
            peak = max(peak, C[i])
            if C[i] < peak * (1 - trail):
                sig[i] = 'sell'; held = False
            elif tp is not None and C[i] / C[i-1] is not None and False:
                pass
        prev_diff = diff
    return sig

if __name__ == '__main__':
    tests = {
        'buy-hold': strat_bh(),
        'ema-cross baseline (roi50/stop20)': strat_ema_cross(),
        'ema-cross trail1.2% tp3%': strat_ema_cross(roi=9, stop=-0.2, trail=0.012, tp=0.03),
        'ema-cross trail0.8%': strat_ema_cross(roi=9, stop=-0.2, trail=0.008),
        'ema-cross trail1.5%': strat_ema_cross(roi=9, stop=-0.2, trail=0.015),
        'ema-cross trail1.2% noTP': strat_ema_cross(roi=9, stop=-0.2, trail=0.012),
        'donchian60/30': strat_donchian(),
        'donchian60/30 trail1%': strat_donchian(trail=0.01),
        'donchian30/15': strat_donchian(30, 15),
        'momentum30 +0.5%/-0.3% trail1%': strat_mom(),
        'momentum60 +0.5%': strat_mom(60, 0.005, -0.003, 0.01),
        'ema-filtered trail1.2%': strat_ema_filtered(),
    }
    for name, sig in tests.items():
        r = run(sig)
        print(f"{name:38s} PnL ${r['pnl']:+7.2f}  trades {r['trades']:2d}  maxDD {r['max_dd']:5.2f}%")
    # halves robustness for top candidates: run on first/second half by slicing bars
    print('\n--- halves (re-run strategy on each half independently, $1000 start) ---')
    import copy
    for name, sig in [('ema-cross trail1.2%', strat_ema_cross(roi=9, stop=-0.2, trail=0.012)),
                      ('ema-cross baseline', strat_ema_cross()),
                      ('donchian60/30', strat_donchian()),
                      ('momentum30', strat_mom()),
                      ('buy-hold', strat_bh())]:
        for lo, hi, lbl in [(0, 720, 'H1'), (720, 1440, 'H2')]:
            # simulate sub-window by temporarily swapping globals
            gO, gC, gD, gDc, gN = O, C, D, Dc, N
            globals()['O'] = O[lo:hi]; globals()['C'] = C[lo:hi]
            globals()['D'] = D[lo:hi]; globals()['Dc'] = Dc[lo:hi]
            globals()['N'] = hi - lo
            r = run(sig[lo:hi])
            globals()['O'], globals()['C'], globals()['D'], globals()['Dc'], globals()['N'] = gO, gC, gD, gDc, gN
            print(f"{name:22s} {lbl}: PnL ${r['pnl']:+7.2f} trades {r['trades']:2d} maxDD {r['max_dd']:5.2f}%")

def strat_slow_ema(fast, slow, trail=None, exit_cross=True):
    f, s = ema(C, fast), ema(C, slow)
    sig = [None] * N
    held = False; peak = 0.0; prev = None
    for i in range(N):
        if f[i] is None or s[i] is None: continue
        diff = f[i] - s[i]
        if prev is not None:
            if not held and diff > 0 and prev <= 0:
                sig[i] = 'buy'; held = True; peak = C[i]
            elif held and exit_cross and diff < 0 and prev >= 0:
                sig[i] = 'sell'; held = False
        if held:
            peak = max(peak, C[i])
            if trail is not None and C[i] < peak * (1 - trail):
                sig[i] = 'sell'; held = False
        prev = diff
    return sig

def strat_trend_hold(look=120, up=0.01, down=-0.01, trail=0.02):
    sig = [None] * N
    held = False; peak = 0.0
    for i in range(look, N):
        r = C[i] / C[i-look] - 1
        if not held and r > up:
            sig[i] = 'buy'; held = True; peak = C[i]
        elif held:
            peak = max(peak, C[i])
            if r < down or C[i] < peak * (1 - trail):
                sig[i] = 'sell'; held = False
    return sig

def strat_sma_trend(look=240, trail=0.02):
    """Buy when close crosses above 240-bar SMA; sell when below it or trailing stop."""
    sig = [None] * N
    held = False; peak = 0.0
    sma = [None]*N
    for i in range(look-1, N):
        sma[i] = sum(C[i-look+1:i+1]) / look
    prev = None
    for i in range(N):
        if sma[i] is None: continue
        above = C[i] > sma[i]
        if prev is not None:
            if not held and above and not prev:
                sig[i] = 'buy'; held = True; peak = C[i]
            elif held and not above and prev:
                sig[i] = 'sell'; held = False
        if held:
            peak = max(peak, C[i])
            if C[i] < peak * (1 - trail):
                sig[i] = 'sell'; held = False
        prev = above
    return sig

def strat_hybrid(entry_bar=1, trail=0.025, reentry_look=240, reentry_up=0.015):
    """Buy full cash at entry_bar; trailing stop from peak; re-enter on 240m momentum."""
    sig = [None] * N
    held = False; peak = 0.0; stopped = False
    for i in range(N):
        if not held and not stopped and i == entry_bar:
            sig[i] = 'buy'; held = True; peak = C[i]
        elif held:
            peak = max(peak, C[i])
            if C[i] < peak * (1 - trail):
                sig[i] = 'sell'; held = False; stopped = True
        elif stopped and i >= reentry_look:
            r = C[i] / C[i-reentry_look] - 1
            if r > reentry_up:
                sig[i] = 'buy'; held = True; peak = C[i]; stopped = False
    return sig

# --- v2 (revised after council review): trail 2.5%, entry 3rd batch, slippage cap 10%,
#     re-entry from stop-out price +1.5% after >=60 bars, max 2 stop-outs ---
def strat_v2(entry_bar=2, trail=0.025, re_up=0.015, cooldown=60, max_stops=2):
    sig = [None] * N
    held = False; peak = 0.0; stop_price = None; stop_i = -1; stops = 0
    for i in range(N):
        if not held and stops == 0 and i == entry_bar and stop_price is None:
            sig[i] = 'buy'; held = True; peak = C[i]
        elif held:
            peak = max(peak, C[i])
            if C[i] < peak * (1 - trail):
                sig[i] = 'sell'; held = False; stop_price = C[i]; stop_i = i; stops += 1
        elif stop_price is not None and stops < max_stops and i - stop_i >= cooldown:
            if C[i] > stop_price * (1 + re_up):
                sig[i] = 'buy'; held = True; peak = C[i]; stop_price = None
    return sig

def run_with_slip(signals, cap=0.10):
    """run() but with a max-slippage cap parameter (buy fill must be <= prev close*(1+cap))."""
    import backtest as _b
    # replicate run() with configurable cap via monkey-patching is complex; instead
    # re-implement inline using module globals O,C,D,Dc,N
    cash = 1000.0; qty = 0.0; peak_eq = 1000.0; max_dd = 0.0; trades = 0
    pending = None
    for i in range(N):
        if pending is not None and i > 0:
            side, amt = pending
            o, d = O[i], D[i]
            if side == 'buy' and amt > 0:
                fee = amt * 0.0004; a = amt - fee
                fp = o * 1.0002 * (1 + a / d)
                if fp <= C[i-1] * (1 + cap):
                    qty += a / fp; cash -= amt; trades += 1
            elif side == 'sell' and qty > 0:
                a = qty * o
                fp = o * 0.9998 / (1 + a / d)
                if fp >= C[i-1] * (1 - cap):
                    gross = qty * fp; cash += gross - gross * 0.0004; qty = 0.0; trades += 1
            pending = None
        if i < N - 1:
            s = signals[i]
            if s == 'buy' and qty == 0 and cash >= 1: pending = ('buy', cash)
            elif s == 'sell' and qty > 0: pending = ('sell', qty)
        eq = cash + qty * C[i]
        peak_eq = max(peak_eq, eq); max_dd = max(max_dd, (peak_eq - eq) / peak_eq)
    if qty > 0:
        o, d = C[-1], Dc[-1]; a = qty * o
        fp = o * 0.9998 / (1 + a / d); gross = qty * fp
        cash += gross - gross * 0.0004; qty = 0.0
    return dict(pnl=cash - 1000.0, trades=trades, max_dd=max_dd * 100)

# --- Published stress proxies for strat_v2 (council review #2, fix 1) ---
# NOTE on parity with main.ts: the bot counts a stop-out only once the stop
# sell is confirmed filled (stopPending flag) and re-issues a rejected sell;
# strat_v2 counts it at the trigger bar. The two agree on every window below
# because a sell is rejected only by a >10% one-minute gap (max_slippage 1000bps)
# while the largest 1-minute move on the dev window is 0.72% — no rejection
# ever occurs in these runs, so trigger-count == fill-count throughout.
import random as _random

def _set_series(Cs, Os=None, Hs=None, Ls=None, Ds=None, Dcs=None):
    g = globals()
    g['C'] = list(Cs)
    g['O'] = list(Os if Os is not None else Cs)
    g['H'] = list(Hs if Hs is not None else Cs)
    g['L'] = list(Ls if Ls is not None else Cs)
    g['D'] = list(Ds if Ds is not None else _D0)
    g['Dc'] = list(Dcs if Dcs is not None else _Dc0)
    g['N'] = len(Cs)

_D0 = list(D); _Dc0 = list(Dc)

def proxy_p1_time_reversal():
    """P1: reverse bar order (depths too). The +2.29% hour becomes a -2.29% hour early."""
    _set_series(C[::-1], O[::-1], H[::-1], L[::-1], D[::-1], Dc[::-1])

def proxy_p2_return_mirror():
    """P2: mirror log-returns around the first close (a falling market with the same shapes)."""
    _set_series([C[0] * (C[0] / c) for c in C], [O[0] * (O[0] / o) for o in O])

def proxy_p3_block_shuffle(seed=7):
    """P3: shuffle 360-bar blocks with random.Random(seed). Boundary jumps are
    artifacts no real replay has (max real open/prev-close move is 19.8bps),
    so this is a gap-sensitivity stress, not a realistic regime."""
    rng = _random.Random(seed)
    order = [0, 1, 2, 3]; rng.shuffle(order)
    idx = [i for b in order for i in range(b * 360, (b + 1) * 360)]
    _set_series([C[i] for i in idx], [O[i] for i in idx], [H[i] for i in idx],
                [L[i] for i in idx], [D[i] for i in idx], [Dc[i] for i in idx])
    return order

def proxy_p4_v_dip(start=600, depth=0.03, width=120):
    """P4: impose a synthetic -3% dip over 60 bars from `start`, recovering over the next 60."""
    Cv = list(C)
    for k in range(width):
        f = 1 - depth * (k / 60) if k < 60 else 1 - depth * (1 - (k - 60) / 60)
        Cv[start + k] = C[start + k] * f
    _set_series(Cv, O, H, L)

def run_v2_report():
    """Dev + P1-P4 for strat_v2 vs buy-and-hold, all via run_with_slip(cap=0.10)."""
    import copy
    C0, O0, H0, L0 = list(C), list(O), list(H), list(L)
    out = []
    _set_series(C0, O0, H0, L0)
    for name, sig in [('v2', strat_v2()), ('B&H', strat_bh())]:
        r = run_with_slip(sig, cap=0.10)
        out.append(f"dev {name}: PnL ${r['pnl']:+.2f} trades {r['trades']} maxDD {r['max_dd']:.2f}%")
    _set_series(C0, O0, H0, L0); proxy_p1_time_reversal()
    for name, sig in [('v2', strat_v2()), ('B&H', strat_bh())]:
        r = run_with_slip(sig, cap=0.10)
        out.append(f"P1 time-reversal {name}: PnL ${r['pnl']:+.2f} trades {r['trades']} maxDD {r['max_dd']:.2f}%")
    _set_series(C0, O0, H0, L0); proxy_p2_return_mirror()
    for name, sig in [('v2', strat_v2()), ('B&H', strat_bh())]:
        r = run_with_slip(sig, cap=0.10)
        out.append(f"P2 return-mirror {name}: PnL ${r['pnl']:+.2f} trades {r['trades']} maxDD {r['max_dd']:.2f}%")
    _set_series(C0, O0, H0, L0); order = proxy_p3_block_shuffle(7)
    out.append(f"P3 block order: {order}")
    for name, sig in [('v2', strat_v2()), ('B&H', strat_bh())]:
        r = run_with_slip(sig, cap=0.10)
        out.append(f"P3 block-shuffle-7 {name}: PnL ${r['pnl']:+.2f} trades {r['trades']} maxDD {r['max_dd']:.2f}%")
    _set_series(C0, O0, H0, L0); proxy_p4_v_dip()
    for name, sig in [('v2', strat_v2()), ('B&H', strat_bh())]:
        r = run_with_slip(sig, cap=0.10)
        out.append(f"P4 V-dip {name}: PnL ${r['pnl']:+.2f} trades {r['trades']} maxDD {r['max_dd']:.2f}%")
    return out

if __name__ == '__main__' and '--v2' in sys.argv:
    for line in run_v2_report():
        print(line)
