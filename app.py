import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from scipy.stats import norm
from datetime import datetime

# --- APP SETUP ---
st.set_page_config(page_title='OTM Put Scanner - Enhanced', layout='wide')
st.title('⌛ OTM Put Option Scanner (Debug Mode)')

# --- SIDEBAR ---
st.sidebar.header('Parameters')
tickers_input = st.sidebar.text_input('Tickers', 'O, NLY, JEPI, JEPQ, SCHD, SPYI, MORT, QYLD, RYLD, IYRI, QQQI')
min_return = st.sidebar.slider('Min Annual Return %', 1.0, 20.0, 5.0)
strike_dist_pct = st.sidebar.slider('Max Strike Distance %', 0.05, 0.50, 0.25)
risk_free = st.sidebar.number_input('Risk Free Rate', 0.0, 0.1, 0.04)

# --- LOGIC ---
def get_vol(ticker_obj):
    try:
        hist = ticker_obj.history(period='1y')
        if len(hist) < 20: return 0.30
        return np.log(hist['Close'] / hist['Close'].shift(1)).dropna().std() * np.sqrt(252)
    except:
        return 0.30

def get_delta(S, K, T, r, sigma):
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0: return 0.0
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    return norm.cdf(d1) - 1

if st.button('Run Market Scan'):
    ticker_list = [t.strip() for t in tickers_input.split(',')]
    results = []
    progress_bar = st.progress(0)
    debug_container = st.expander("Detailed Debug Logs", expanded=True)

    for idx, symbol in enumerate(ticker_list):
        try:
            stock = yf.Ticker(symbol)
            vol = get_vol(stock)

            # --- ENHANCED PRICE FETCHING ---
            price = None
            try:
                price = stock.fast_info['last_price']
            except: pass

            if price is None or np.isnan(price):
                try:
                    price = stock.history(period='1d')['Close'].iloc[-1]
                except: pass

            if price is None or np.isnan(price):
                debug_container.error(f"❌ {symbol}: Could not fetch current market price.")
                continue

            expirations = stock.options
            if not expirations:
                debug_container.warning(f"⚠️ {symbol}: No option expirations found in Yahoo Finance.")
                continue

            valid_expiry_count = 0
            for exp in expirations[:15]: # Scan first 15 expiries
                days = (datetime.strptime(exp, '%Y-%m-%d') - datetime.now()).days
                if not (20 <= days <= 160): continue
                
                valid_expiry_count += 1
                try:
                    chain = stock.option_chain(exp)
                    puts = chain.puts[(chain.puts['strike'] < price) & (chain.puts['strike'] >= price * (1-strike_dist_pct))]

                    if puts.empty:
                        debug_container.info(f"ℹ️ {symbol} [{exp}]: No strikes met distance criteria ({strike_dist_pct*100}% OTM).")
                        continue

                    for _, row in puts.iterrows():
                        bid, ask, last = row.get('bid', 0), row.get('ask', 0), row.get('lastPrice', 0)
                        opt_price = (bid + ask)/2 if (bid > 0 and ask > 0) else last

                        if opt_price <= 0.01: continue
                        ann_ret = (opt_price / row['strike']) * (365 / days) * 100

                        if ann_ret >= min_return:
                            delta = get_delta(price, row['strike'], days/365, risk_free, vol)
                            results.append({
                                'Ticker': symbol, 'Expiry': exp, 'Days': days, 'Strike': row['strike'],
                                'Opt Price': round(opt_price, 3), 'Return %': round(ann_ret, 2), 'Delta': round(delta, 3)
                            })
                except Exception as e:
                    debug_container.write(f"Error fetching chain for {symbol} {exp}: {e}")
            
            if valid_expiry_count == 0:
                debug_container.warning(f"⚠️ {symbol}: No expirations found in the 20-160 day window.")

        except Exception as e:
            debug_container.error(f"Global error for {symbol}: {e}")

        progress_bar.progress((idx + 1) / len(ticker_list))

    if results:
        df = pd.DataFrame(results)
        st.subheader("Scan Results")
        st.dataframe(df.sort_values('Return %', ascending=False).style.background_gradient(subset=['Return %'], cmap='RdYlGn'))
    else:
        st.warning('No options met your criteria. Try lowering the "Min Annual Return %" or increasing the "Max Strike Distance %" in the sidebar.')
