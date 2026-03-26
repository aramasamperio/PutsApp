import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from scipy.stats import norm
from datetime import datetime
import time
import random

# -----------------------
# APP SETUP
# -----------------------
st.set_page_config(page_title='OTM Put Scanner', layout='wide')
st.title('📱 OTM Put Option Scanner')

# -----------------------
# SIDEBAR
# -----------------------
default_tickers = ['O','NLY','JEPI','JEPQ','SCHD','SPYI','MORT','QYLD','RYLD','IYRI','QQQI']

selected = st.sidebar.multiselect(
    'Tickers',
    default_tickers,
    default=default_tickers
)

new_input = st.sidebar.text_input('Add ticker(s) comma separated')

tickers = selected.copy()
if new_input:
    tickers += [t.strip().upper() for t in new_input.split(',')]

tickers = list(dict.fromkeys(tickers))

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
    except:
        return 0.30

def get_delta(S, K, T, r, sigma):
    if T <= 0 or sigma <= 0:
        return 0
    d1 = (np.log(S/K) + (r+0.5*sigma**2)*T)/(sigma*np.sqrt(T))
    return norm.cdf(d1) - 1

def scan_single_ticker(symbol, min_return, strike_dist_pct, risk_free):
    results = []
    try:
        stock = yf.Ticker(symbol)
        # Fixed: removed invalid string concatenation that caused exceptions
        
        # Resilient Price Logic
        price = None
        try:
            price = stock.fast_info['last_price']
        except:
            pass
        
        if price is None or np.isnan(price):
            hist = stock.history(period='1d')
            if not hist.empty:
                price = hist['Close'].iloc[-1]
        
        if price is None or np.isnan(price):
            return []

        vol = get_vol(stock)
        expiries = stock.options
        if not expiries:
            return []

        today = datetime.now()
        for exp in expiries:
            exp_date = datetime.strptime(exp, '%Y-%m-%d')
            days = (exp_date - today).days
            
            # Filter by window (matching windows from first script approx)
            if not (20 <= days <= 160):
                continue

            try:
                chain = stock.option_chain(exp)
                puts = chain.puts
            except:
                continue

            relevant_puts = puts[
                (puts['strike'] < price) & 
                (puts['strike'] >= price * (1 - strike_dist_pct))
            ]

            for _, row in relevant_puts.iterrows():
                strike = row['strike']
                bid, ask, last_trade = row.get('bid', 0), row.get('ask', 0), row.get('lastPrice', 0)
                
                opt_price = (bid + ask) / 2 if (bid > 0 and ask > 0) else last_trade
                if opt_price <= 0.01: continue

                ann_ret = (opt_price / strike) * (365 / days) * 100
                if ann_ret < min_return: continue

                delta = get_delta(price, strike, days/365, risk_free, vol)

                results.append({
                    'Ticker': symbol,
                    'Expiry': exp,
                    'Days': days,
                    'Strike': strike,
                    'Opt Price': opt_price,
                    'Return': ann_ret,
                    'Delta': delta
                })
    except Exception as e:
        st.sidebar.error(f"Error {symbol}: {e}")
        return []
    return results

# -----------------------
# MAIN
# -----------------------
if st.button('Run Scan'):
    all_rows = []
    progress_bar = st.progress(0)
    status_text = st.empty()

    for i, t in enumerate(tickers):
        status_text.text(f"Scanning {t}...")
        all_rows.extend(scan_single_ticker(t, min_return, strike_dist_pct, risk_free))
        progress_bar.progress((i + 1) / len(tickers))

    status_text.empty()
    progress_bar.empty()

    if not all_rows:
        st.warning("No results found for the selected criteria.")
    else:
        df = pd.DataFrame(all_rows)
        df = df.sort_values(['Ticker', 'Days', 'Return'], ascending=[True, True, False])

        st.dataframe(
            df,
            use_container_width=True,
            column_config={
                "Return": st.column_config.ProgressColumn("Ann. Return %", format="%.2f%%", min_value=0, max_value=max(df['Return'].max(), 10)),
                "Strike": st.column_config.NumberColumn(format="$%.2f"),
                "Opt Price": st.column_config.NumberColumn(format="$%.3f"),
                "Delta": st.column_config.NumberColumn(format="%.3f"),
            }
        )
