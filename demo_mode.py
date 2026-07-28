import fnmatch
import json
import os

import streamlit as st

import logic
from validate_real_cases import REAL, FakeFile, discover_cases

DEMO_ALIASES = {"schwab": "schwab_1", "schwab2": "schwab_2", "ib": "ib_1"}


def demo_available():
    return os.path.isdir(REAL)


def demo_keys():
    keys = list(DEMO_ALIASES.keys())
    keys += [c['case_id'] for c in discover_cases() if c['case_id'] not in DEMO_ALIASES.values()]
    return keys


def _ci_glob(case_dir, pattern, exclude=()):
    out = []
    for name in sorted(os.listdir(case_dir)):
        if name == 'expected.json' or name in exclude:
            continue
        if fnmatch.fnmatch(name.lower(), pattern.lower()):
            out.append(os.path.join(case_dir, name))
    return out


def load_demo_case(param):
    if not demo_available():
        return None
    case_id = DEMO_ALIASES.get(param, param)
    if not any(c['case_id'] == case_id for c in discover_cases()):
        return None
    return _load_bundle(case_id)


@st.cache_data(show_spinner=False)
def _load_bundle(case_id):
    case = next((c for c in discover_cases() if c['case_id'] == case_id), None)
    if case is None:
        return None
    case_dir, manifest = case['dir'], case['manifest']

    income_matches = []
    income_glob = manifest.get('income_glob')
    if income_glob:
        income_matches = _ci_glob(case_dir, income_glob)
    exclude = tuple(os.path.basename(p) for p in income_matches)

    csv_matches = _ci_glob(case_dir, manifest.get('csv_glob', '*.csv'), exclude=exclude)
    if not csv_matches:
        return None
    csv_path = csv_matches[0]
    basename = os.path.basename(csv_path)
    with open(csv_path, 'rb') as f:
        df, broker = logic.load_and_detect_csv(FakeFile(f.read(), basename))
    if df.empty:
        return None
    df_clean = logic.normalize_csv(df)
    if any(c not in df_clean.columns for c in ['Date', 'Ticker', 'Amount']):
        return None

    csv_td = {}
    if 'Ticker' in df_clean.columns and 'Action' in df_clean.columns:
        for t, g in df_clean.groupby('Ticker'):
            buys = g[g['Action'].str.lower().str.contains('buy', na=False)]
            divs = g[g['Action'].str.lower().str.contains('div', na=False)]
            csv_td[t] = {
                'shares': float(buys['Quantity'].sum()) if 'Quantity' in buys.columns and not buys.empty else 0.0,
                'invested': abs(float(buys['Amount'].sum())) if not buys.empty else 0.0,
                'dividends_csv': float(divs['Amount'].sum()) if not divs.empty else 0.0,
                'first_date': str(g['Date'].min())[:10] if not g.empty else 'N/A',
            }

    tickers = df_clean['Ticker'].dropna().unique().tolist()
    mmap = logic.classify_tickers(tickers)
    pos_tickers = [t for t, m in mmap.items() if m in ('mode_a', 'mode_b')]
    ib_map, overrides, positions = {}, {}, {}
    for t, exp in (manifest.get('tickers') or {}).items():
        if t not in pos_tickers:
            continue
        co = float(exp.get('cost_basis') or 0)
        sh = float(exp.get('shares') or 0)
        if co > 0:
            ib_map[t] = str(co)
        if co > 0 or sh > 0:
            overrides[t] = {'cost_basis': co or None, 'shares': sh or None}
        positions[t] = {'shares': sh, 'cost_basis': co}

    income_summary = income_df = None
    income_multi = False
    if income_matches:
        try:
            with open(income_matches[0], 'rb') as f:
                inc_df = logic.parse_schwab_income_csv(f.read())
            if inc_df is not None and len(inc_df) > 0:
                inc_summ = logic.summarize_income(inc_df)
                if any(d.get('received_total') for d in (inc_summ.get('tickers') or {}).values()):
                    income_summary = inc_summ
                    income_df = inc_df
                    income_multi = bool(inc_summ.get('multi_account'))
        except Exception:
            pass

    res = logic.analyze_portfolio(
        df_clean, version="2.0",
        ib_cost_basis_map=ib_map or None,
        position_overrides=overrides or None)
    if not res:
        return None
    skipped = {t: s for t, s in res.items() if s.get("skipped")}
    valid = {t: s for t, s in res.items() if not s.get("skipped")}
    if not valid:
        return None
    cmap = logic.classify_tickers(list(valid.keys()))

    buy_rows = []
    for tk, ts in valid.items():
        h = ts.get('history')
        if h is not None and not h.empty:
            for _, r in h[h['Action'].str.lower().str.contains('buy|compra', na=False)].iterrows():
                a = abs(float(r.get('Amount', 0)))
                if a > 0:
                    buy_rows.append([str(r['Date'].date()), a])
    strat = None
    if buy_rows:
        try:
            strat = logic.simulate_triple_comparison(json.dumps(buy_rows))
        except Exception:
            strat = None

    return {
        '_wizard_step': 3,
        '_prev_step': 3,
        '_prev_active_pill': 3,
        '_wizard_df_clean': df_clean,
        '_wizard_csv_ticker_data': csv_td,
        '_wizard_broker': broker,
        '_wizard_csv_name': basename,
        '_wizard_ib_map': ib_map,
        '_wizard_overrides': overrides,
        '_wizard_positions': positions,
        '_wizard_pos_confirmed': True,
        '_wizard_photo_sig': None,
        '_wizard_income_summary': income_summary,
        '_wizard_income_df': income_df,
        '_wizard_income_multi': income_multi,
        '_results': valid,
        '_classify_map': cmap,
        '_skipped': skipped,
        '_strat_results': strat,
        '_file_id': f"demo_{case_id}",
    }
