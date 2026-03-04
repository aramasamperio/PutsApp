import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from scipy.stats import norm
from datetime import datetime

# --- APP SETUP ---
st.set_page_config(page_title='OTM Put Scanner', layout='wide')
st.title('⌛ OTM Put Option Scanner')

# --- SIDEBAR ---
st.sidebar.header('Parameters')
tickers_input = st.sidebar.text_input('Tickers', 'O, NLY, JEPI, JEPQ, SCHD, SPYI, MORT, QYLD, RYLD, IYRI, QQQI')
min_return = st.sidebar.slider('Min Annual Return %', 1.0, 20.0, 5.0)
strike_dist_pct = st.sidebar.slider('Max Strike Distance %', 0.05, 0.50, 0.25)
risk_free = st.sidebar.number_input('Risk Free Rate', 0.0, 0.1, 0.04)

# --- LOGIC ---
def get_vol(ticker_obj):
    hist = ticker_obj.history(period='1y')
    if len(hist) < 20: return 0.30
    return np.log(hist['Close'] / hist['Close'].shift(1)).dropna().std() * np.sqrt(252)

def get_delta(S, K, T, r, sigma):
    if T <= 0 or sigma <= 0: return 0.0
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    return norm.cdf(d1) - 1

if st.button('Run Market Scan'):
    ticker_list = [t.strip() for t in tickers_input.split(',')]
    results = []
    progress_bar = st.progress(0)

    for idx, symbol in enumerate(ticker_list):
        try:
            stock = yf.Ticker(symbol)
            vol = get_vol(stock)
            
            # Price Fetching Logic
            price = None
            try:
                price = stock.fast_info['last_price']
            except:
                pass
            if price is None or np.isnan(price):
                price = stock.history(period='1d')['Close'].iloc[-1]

            for exp in stock.options:
                days = (datetime.strptime(exp, '%Y-%m-%d') - datetime.now()).days
                if not (20 <= days <= 160): continue

                chain = stock.option_chain(exp)
                puts = chain.puts[(chain.puts['strike'] < price) & (chain.puts['strike'] >= price * (1-strike_dist_pct))]

                for _, row in puts.iterrows():
                    # Fallback pricing: mid if available, else lastPrice
                    bid, ask, last = row.get('bid', 0), row.get('ask', 0), row.get('lastPrice', 0)
                    opt_price = (bid + ask)/2 if (bid > 0 and ask > 0) else last
                    
                    if opt_price <= 0.01: continue
                    ann_ret = (opt_price / row['strike']) * (365 / days) * 100

                    if ann_ret >= min_return:
                        delta = get_delta(price, row['strike'], days/365, risk_free, vol)
                        results.append({
                            'Ticker': symbol, 'Expiry': exp, 'Strike': row['strike'],
                            'Opt Price': round(opt_price, 3), 'Return %': round(ann_ret, 2), 'Delta': round(delta, 3)
                        })
        except:
            continue
        progress_bar.progress((idx + 1) / len(ticker_list))

    if results:
        df = pd.DataFrame(results)
        st.dataframe(df.sort_values('Return %', ascending=False).style.background_gradient(subset=['Return %'], cmap='RdYlGn'))
    else:
        st.warning('No options met your criteria. Try lowering the Min Annual Return.')
