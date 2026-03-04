import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from scipy.stats import norm
from datetime import datetime

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
def fmt_pct(x):
    """2 decimals max, no decimals for whole numbers"""
    if abs(x - round(x)) < 0.01:
        return f"{int(round(x))}%"
    return f"{x:.2f}%"


def get_vol(ticker_obj):
    try:
        hist = ticker_obj.history(period='1y')
        r = np.log(hist['Close'] / hist['Close'].shift(1)).dropna()
        return r.std() * np.sqrt(252)
    except:
        return 0.30


def get_delta(S, K, T, r, sigma):
    if T <= 0 or sigma <= 0:
        return 0
    d1 = (np.log(S/K) + (r+0.5*sigma**2)*T)/(sigma*np.sqrt(T))
    return norm.cdf(d1) - 1


# -----------------------
# CACHE PER TICKER
# -----------------------
import time
import random

@st.cache_data(ttl=600)
def scan_single_ticker(symbol, min_return, strike_dist_pct, risk_free):
    results = []

    try:
        stock = yf.Ticker(symbol)

        # small pause before each ticker
        time.sleep(random.uniform(0.4, 0.8))

        price = stock.fast_info.get('last_price')

        if not price:
            hist = stock.history(period='1d')
            if hist.empty:
                return []
            price = hist['Close'].iloc[-1]

        vol = get_vol(stock)

        expiries = stock.options
        if not expiries:
            return []

        for exp in expiries[:6]:  # fewer calls = safer
            days = (datetime.strptime(exp, '%Y-%m-%d') - datetime.now()).days
            if not (20 <= days <= 160):
                continue

            # pause before each option chain request
            time.sleep(random.uniform(0.3, 0.6))

            try:
                chain = stock.option_chain(exp)
            except:
                # retry once if blocked
                time.sleep(1)
                chain = stock.option_chain(exp)

            puts = chain.puts[
                (chain.puts['strike'] < price) &
                (chain.puts['strike'] >= price*(1-strike_dist_pct))
            ]

            for _, row in puts.iterrows():
                mid = (row['bid'] + row['ask'])/2 if row['bid']>0 and row['ask']>0 else row['lastPrice']
                if mid <= 0:
                    continue

                ann_ret = (mid/row['strike']) * (365/days) * 100
                if ann_ret < min_return:
                    continue

                delta = get_delta(price, row['strike'], days/365, risk_free, vol)

                results.append({
                    'Ticker': symbol,
                    'Exp': exp[5:],
                    'D': days,
                    'Strike': row['strike'],
                    'Price': mid,
                    'Return': ann_ret,
                    'Delta': delta
                })

    except:
        return []

    return results


# -----------------------
# MAIN
# -----------------------
if st.button('Run Scan'):

    all_rows = []

    for t in tickers:
        all_rows.extend(
            scan_single_ticker(t, min_return, strike_dist_pct, risk_free)
        )

    if not all_rows:
        st.warning("No results found.")
        st.stop()

    df = pd.DataFrame(all_rows)

    # formatting for mobile
    #df['Return'] = df['Return'].apply(fmt_pct)
    df['Price'] = df['Price'].round(2)
    df['Strike'] = df['Strike'].round(2)
    df['Delta'] = df['Delta'].round(2)

    df = df.sort_values('Return', ascending=False)

st.dataframe(
    df,
    use_container_width=True,
    column_config={
        "Return": st.column_config.ProgressColumn(
            "Return %",
            format="%.2f%%",
            min_value=0,
            max_value=df["Return"].max()
        ),
        "Price": st.column_config.NumberColumn(format="%.2f"),
        "Strike": st.column_config.NumberColumn(format="%.2f"),
        "Delta": st.column_config.NumberColumn(format="%.2f"),
    }
)
