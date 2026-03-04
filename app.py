import streamlit as st
import pandas as pd

# Function to format prices and returns

def format_numeric(value):
    if value == int(value):  # Check if the number is a round number
        return str(int(value))  # Return as integer
    else:
        return f'{value:.2f}'  # Return with two decimal places

# Store scan results in the session state
if 'scan_results' not in st.session_state:
    st.session_state.scan_results = []  # Initialize scan results

# Function to run the scan
# Here you would implement the logic to fetch scan data based on selected tickers

def run_scan(selected_tickers):
    # Mockup DataFrame as an example, replace with actual fetching logic
    data = {
        'Ticker': selected_tickers,
        'Price': [100.123, 200.4, 150.0],  # Mocked prices
        'Return': [10.123, -5.256, 3.0]  # Mocked returns
    }
    df = pd.DataFrame(data)
    df['Price'] = df['Price'].apply(format_numeric)
    df['Return'] = df['Return'].apply(format_numeric)
    return df

# Function to filter results based on current ticker selection
def filter_results(selected_tickers):
    return [result for result in st.session_state.scan_results if result['Ticker'] in selected_tickers]

# Sidebar for user input: ticker selection
st.sidebar.title('Select Tickers')
selected_tickers = st.sidebar.multiselect('Choose ticker(s)', options=['AAPL', 'GOOGL', 'AMZN', 'MSFT'])

# Confirm button for scan
if st.sidebar.button('Confirm Scan'):
    scan_df = run_scan(selected_tickers)
    st.session_state.scan_results = scan_df.to_dict(orient='records')  # Save results in session state

# Filter and display results
results_df = pd.DataFrame(filter_results(selected_tickers))
if not results_df.empty:
    # Sort functionality
    sort_column = st.selectbox('Sort by', results_df.columns)
    results_df = results_df.sort_values(by=sort_column)
    st.table(results_df)
else:
    st.write('No data available for selected tickers.')  # Message when no data
