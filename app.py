import os
try:
    import requests
except ImportError:
    os.system('pip install requests yfinance pandas numpy scipy')

import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from scipy.stats import norm
from datetime import datetime
import time
import random

# --- 1. APP SETUP ---
st.set_page_config(page_title='OTM Put Scanner', layout='wide')
st.title('📱 OTM Put Option Scanner')

# --- 2. SIDEBAR ---
default_tickers = ['O','NLY','JEPI','JEPQ','SCHD','SPYI','MORT','QYLD','RYLD','IYRI','QQQI','BTCI']
selected = st.sidebar.multiselect('Tickers', default_tickers, default=default_tickers)
new_input = st.sidebar.text_input('Add ticker(s) comma separated')
tickers = list(dict.fromkeys(selected + [t.strip().upper() for t in new_input.split(',')] if new_input else selected))

min_return = st.sidebar.slider('Min Annual Return %', 1.0, 20.0, 5.0)
strike_dist_pct = st.sidebar.slider('Max Strike Distance %', 0.05, 0.50, 0.25)
risk_free = st.sidebar.number_input('Risk Free Rate', 0.0, 0.1, 0.04)

# --- 3. HELPERS ---
def get_vol(ticker_obj):
    try:
        hist = ticker_obj.history(period='1y')
        if len(hist) < 20: return 0.30
        r = np.log(hist['Close'] / hist['Close'].shift(1)).dropna()
        return r.std() * np.sqrt(252)
    except: return 0.30

def get_delta(S, K, T, r, sigma):
    if T <= 0 or sigma <= 0: return 0.0
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    return norm.cdf(d1) - 1

# --- 4. SCANNER ---
def scan_single_ticker(symbol, min_return, strike_dist_pct, risk_free):
    results = []
    logs = []
    try:
        # Slow down initialization
        time.sleep(random.uniform(1.0, 2.0))
        stock = yf.Ticker(symbol)
        
        price = None
        try: price = stock.fast_info['last_price']
        except: pass

        if price is None or np.isnan(price):
            hist = stock.history(period='1d')
            if not hist.empty: price = hist['Close'].iloc[-1]
        
        if price is None or np.isnan(price):
            return [], [f"{symbol}: No Price found"]

        vol = get_vol(stock)
        expiries = stock.options
        if not expiries:
            return [], [f"{symbol}: No Expiries found"]

        today = datetime.now()
        # Strictly limit to first 8 expiries to avoid rate limiting
        for exp in expiries[:8]:
            exp_date = datetime.strptime(exp, '%Y-%m-%d')
            days = (exp_date - today).days
            if not (20 <= days <= 160): continue

            # Throttle between expiry requests
            time.sleep(random.uniform(0.5, 1.0))

            try:
                chain = stock.option_chain(exp)
                puts = chain.puts
                if puts.empty: continue
            except Exception as e:
                logs.append(f"{symbol} {exp}: Chain error {str(e)}")
                continue

            rel_puts = puts[(puts['strike'] < price) & (puts['strike'] >= price * (1 - strike_dist_pct))]

            for _, row in rel_puts.iterrows():
                bid, ask, last = row.get('bid', 0), row.get('ask', 0), row.get('lastPrice', 0)
                mid = (bid + ask)/2 if (bid > 0 and ask > 0) else last
                if mid <= 0.01: continue
                
                ann_ret = (mid / row['strike']) * (365 / days) * 100
                if ann_ret < min_return: continue

                #delta = get_delta(price, row['strike'], days/365, risk_free, vol)
                results.append({
                    'Ticker': symbol, 'Expiry': exp, 'Days': days, 'Strike': row['strike'], 
                    'Opt Price': mid, 'Return': ann_ret#, 'Delta': delta
                })
    except Exception as e:
        return [], [f"{symbol}: Global Error {str(e)}"]
    return results, logs

# --- 5. MAIN ---
if 'scan_results' not in st.session_state:
    st.session_state.scan_results = None

if st.button('🚀 Run Scan'):
    all_rows = []
    all_logs = []
    progress_bar = st.progress(0)
    status_text = st.empty()

    for i, t in enumerate(tickers):
        status_text.text(f"Scanning {t}... (Throttle Active)")
        res, logs = scan_single_ticker(t, min_return, strike_dist_pct, risk_free)
        all_rows.extend(res)
        all_logs.extend(logs)
        progress_bar.progress((i + 1) / len(tickers))

    status_text.empty()
    progress_bar.empty()
    st.session_state.scan_results = all_rows
    st.session_state.logs = all_logs

if st.session_state.scan_results is not None:
    if not st.session_state.scan_results:
        st.warning("No results found. This often happens if the API is rate-limiting. Check debug logs.")
        if st.checkbox("Show Debug Logs"):
            for log in st.session_state.get('logs', []):
                st.text(log)
    else:
        df = pd.DataFrame(st.session_state.scan_results).sort_values(['Ticker', 'Days', 'Return'], ascending=[True, True, False])
        st.dataframe(df, use_container_width=True, column_config={
            "Return": st.column_config.ProgressColumn("Ann. Return %", format="%.2f%%", min_value=0, max_value=max(df['Return'].max(), 10.0)),
            "Strike": st.column_config.NumberColumn(format="$%.2f"),
            "Opt Price": st.column_config.NumberColumn(format="$%.3f"),
            "Delta": st.column_config.NumberColumn(format="%.3f")
        })
