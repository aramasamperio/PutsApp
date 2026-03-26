import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from scipy.stats import norm
from datetime import datetime
import time
import random
import requests
from requests_cache import CachedSession
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

# -----------------------
# SESSION SETUP (FIX FOR RATE LIMITING)
# -----------------------
def get_yf_session():
    session = requests.Session()
    # User-Agent is critical to prevent 'Too Many Requests'
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36'
    })
    retries = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    session.mount('https://', HTTPAdapter(max_retries=retries))
    return session

# -----------------------
# APP SETUP
# -----------------------
st.set_page_config(page_title='OTM Put Scanner', layout='wide')
st.title('📱 OTM Put Option Scanner')

# -----------------------
# SIDEBAR
# -----------------------
default_tickers = ['O','NLY','JEPI','JEPQ','SCHD','SPYI','MORT','QYLD','RYLD','IYRI','QQQI']
selected = st.sidebar.multiselect('Tickers', default_tickers, default=default_tickers)
new_input = st.sidebar.text_input('Add ticker(s) comma separated')
tickers = list(dict.fromkeys(selected + [t.strip().upper() for t in new_input.split(',')] if new_input else selected))

min_return = st.sidebar.slider('Min Annual Return %', 1.0, 20.0, 5.0)
strike_dist_pct = st.sidebar.slider('Max Strike Distance %', 0.05, 0.50, 0.25)
risk_free = st.sidebar.number_input('Risk Free Rate', 0.0, 0.1, 0.04)

# -----------------------
# HELPERS
# -----------------------
def get_vol(ticker_obj):
    try:
        hist = ticker_obj.history(period='1y')
        if len(hist) < 20: return 0.30
        r = np.log(hist['Close'] / hist['Close'].shift(1)).dropna()
        return r.std() * np.sqrt(252)
    except: return 0.30

def get_delta(S, K, T, r, sigma):
    if T <= 0 or sigma <= 0: return 0
    d1 = (np.log(S/K) + (r+0.5*sigma**2)*T)/(sigma*np.sqrt(T))
    return norm.cdf(d1) - 1

def scan_single_ticker(symbol, min_return, strike_dist_pct, risk_free, session):
    results = []
    try:
        stock = yf.Ticker(symbol, session=session)
        # Use fast_info for current price to minimize heavy calls
        price = None
        try: price = stock.fast_info['last_price']
        except: pass

        if price is None or np.isnan(price):
            hist = stock.history(period='1d')
            if not hist.empty: price = hist['Close'].iloc[-1]
        
        if price is None or np.isnan(price): return []

        vol = get_vol(stock)
        expiries = stock.options
        if not expiries: return []

        today = datetime.now()
        # Limit iterations to avoid triggering rate limit
        for exp in expiries[:15]:
            exp_date = datetime.strptime(exp, '%Y-%m-%d')
            days = (exp_date - today).days
            if not (20 <= days <= 160): continue

            try:
                chain = stock.option_chain(exp)
                puts = chain.puts
            except: continue

            rel_puts = puts[(puts['strike'] < price) & (puts['strike'] >= price * (1 - strike_dist_pct))]

            for _, row in rel_puts.iterrows():
                mid = (row['bid'] + row['ask'])/2 if (row['bid'] > 0 and row['ask'] > 0) else row['lastPrice']
                if mid <= 0.01: continue
                ann_ret = (mid / row['strike']) * (365 / days) * 100
                if ann_ret < min_return: continue

                delta = get_delta(price, row['strike'], days/365, risk_free, vol)
                results.append({'Ticker': symbol, 'Expiry': exp, 'Days': days, 'Strike': row['strike'], 'Opt Price': mid, 'Return': ann_ret, 'Delta': delta})
        
        # Randomized sleep to throttle requests
        time.sleep(random.uniform(0.5, 1.5))
    except: return []
    return results

# -----------------------
# MAIN
# -----------------------
if st.button('Run Scan'):
    all_rows = []
    session = get_yf_session()
    progress_bar = st.progress(0)
    status_text = st.empty()

    for i, t in enumerate(tickers):
        status_text.text(f"Scanning {t}...")
        all_rows.extend(scan_single_ticker(t, min_return, strike_dist_pct, risk_free, session))
        progress_bar.progress((i + 1) / len(tickers))

    status_text.empty()
    progress_bar.empty()

    if not all_rows: st.warning("No results found. Try lowering 'Min Return' or increasing 'Max Strike Distance'.")
    else:
        df = pd.DataFrame(all_rows).sort_values(['Ticker', 'Days', 'Return'], ascending=[True, True, False])
        st.dataframe(df, use_container_width=True, column_config={
            "Return": st.column_config.ProgressColumn("Ann. Return %", format="%.2f%%", min_value=0, max_value=max(df['Return'].max(), 10)),
            "Strike": st.column_config.NumberColumn(format="$%.2f"),
            "Opt Price": st.column_config.NumberColumn(format="$%.3f"),
            "Delta": st.column_config.NumberColumn(format="%.3f")
        })
