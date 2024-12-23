import streamlit as st
import pandas as pd
import fredapi
import plotly.graph_objects as go

# FRED API Key (REPLACE THIS WITH YOUR ACTUAL KEY)
FRED_API_KEY = "73d91c54519573fad1e3a2bb990af710"

fred = fredapi.Fred(api_key=FRED_API_KEY)

@st.cache_data
def get_fred_data(series_id, title):
    try:
        data = fred.get_series(series_id)
        if data is None or data.empty:
            st.warning(f"No data available for {title} (Series ID: {series_id}).")
            return None
        df = pd.DataFrame(data, columns=[title])
        df.index = pd.to_datetime(df.index)
        return df
    except Exception as e:
        st.error(f"Error fetching data for {series_id}: {e}")
        return None

def calculate_cpi_yoy(df, title):
    try:
        df_yoy = df.resample('MS').last().pct_change(12) * 100
        return df_yoy
    except Exception as e:
        st.error(f"Error calculating YoY for {title}: {e}")
        return None

st.set_page_config(page_title="US Macro Dashboard")
st.title("US Macro Dashboard")

# Date Range Slider
start_date, end_date = st.date_input("Select Date Range", value=(pd.to_datetime('2010-01-01'), pd.Timestamp.today()))

# Available Indicators
indicators = {
    "GDP": {"id": "A191RL1Q225SBEA", "title": "Real GDP (SAAR)"},
    "Unemployment Rate": {"id": "UNRATE", "title": "Unemployment Rate (%)"},
    "Inflation - CPI": {"series": [("CPIAUCSL", "CPI (y/y)"), ("CPILFESL", "Core CPI (y/y)")], "yoy_func": calculate_cpi_yoy}, # Combined CPI entry
    "10-Year Treasury Yield": {"id": "GS10", "title": "10-Year Treasury Yield (%)"},
    "S&P 500": {"id": "SP500", "title": "S&P 500"},
}

# Indicator Selection Dropdown
selected_indicator = st.selectbox("Select an Economic Indicator", list(indicators.keys()))

# --- Display Selected Indicator ---
st.header(selected_indicator)

selected_data = indicators[selected_indicator]

if "series" in selected_data:  # Handle combined CPI case
    fig_cpi = go.Figure()
    for series_id, series_title in selected_data["series"]:
        df = get_fred_data(series_id, series_title.split(" ")[0]) #get base title for data retrieval
        if df is not None:
            df = selected_data["yoy_func"](df, series_title.split(" ")[0])
            if df is not None:
                fig_cpi.add_trace(go.Scatter(x=df.index, y=df[series_title.split(" ")[0]], mode='lines', name=series_title))
            else:
                st.warning(f"Error calculating YoY for {series_title}.")
        else:
            st.warning(f"Could not retrieve data for {series_title}.")
    fig_cpi.update_layout(title="CPI and Core CPI (y/y)", xaxis_title="Date", yaxis_title="Percent Change (y/y)")
    st.plotly_chart(fig_cpi, use_container_width=True)

elif "id" in selected_data: #handle other metrics
    df = get_fred_data(selected_data["id"], selected_data["title"])

    if df is not None:
        if "yoy_func" in selected_data:
            df = selected_data["yoy_func"](df, selected_data["title"])
            if df is None:
                st.warning("Error calculating YoY.")
                st.stop()

        df_filtered = df[(df.index >= pd.to_datetime(start_date)) & (df.index <= pd.to_datetime(end_date))]
        if not df_filtered.empty:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df_filtered.index, y=df_filtered[selected_data["title"]], mode='lines'))
            fig.update_layout(title=selected_indicator, xaxis_title="Date", yaxis_title=selected_data["title"])
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("No data available for the selected indicator within the chosen date range.")
    else:
        st.warning("Could not retrieve data for the selected indicator.")