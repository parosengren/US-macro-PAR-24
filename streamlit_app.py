import streamlit as st
import pandas as pd
import fredapi
import plotly.graph_objects as go

# FRED API Key (REPLACE THIS WITH YOUR ACTUAL KEY)
FRED_API_KEY = "73d91c54519573fad1e3a2bb990af710"

fred = fredapi.Fred(api_key=FRED_API_KEY)

from datetime import datetime, timedelta

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

@st.cache_data
def convert_df_to_csv(df):
    return df.to_csv(index=False).encode('utf-8')

@st.cache_data
def convert_df_to_excel(df):
    from io import BytesIO
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Sheet1")
    return output.getvalue()

st.set_page_config(page_title="US Macro Dashboard")
st.title("US Macro Dashboard")

# --- Timeline Slider ---
st.header("Timeline Selector")
min_date = datetime(2010, 1, 1).date()
max_date = datetime.today().date()

start_date, end_date = st.slider(
    "Select Date Range",
    min_value=min_date,
    max_value=max_date,
    value=(min_date, max_date),
    format="YYYY-MM-DD"
)

# --- Available Indicators ---
indicators = {
    "GDP": {"id": "A191RL1Q225SBEA", "title": "Real GDP (SAAR)"},
    "Unemployment Rate": {"id": "UNRATE", "title": "Unemployment Rate (%)"},
    "Inflation - CPI": {"series": [("CPIAUCSL", "CPI (y/y)"), ("CPILFESL", "Core CPI (y/y)")], "yoy_func": calculate_cpi_yoy},
    "10-Year Treasury Yield": {"id": "GS10", "title": "10-Year Treasury Yield (%)"},
    "S&P 500": {"id": "SP500", "title": "S&P 500"},
}

# --- Indicator Selection Dropdown ---
selected_indicator = st.selectbox("Select an Economic Indicator", list(indicators.keys()))

# --- Display Selected Indicator ---
st.header(selected_indicator)
selected_data = indicators[selected_indicator]

three_years_ago = datetime.now() - timedelta(days=3 * 365)

if "series" in selected_data:  # Handle combined CPI case
    fig_cpi = go.Figure()
    for series_id, series_title in selected_data["series"]:
        df = get_fred_data(series_id, series_title.split(" ")[0])
        if df is not None:
            df = selected_data["yoy_func"](df, series_title.split(" ")[0])
            if df is not None:
                fig_cpi.add_trace(go.Scatter(x=df.index, y=df[series_title.split(" ")[0]], mode='lines', name=series_title))
                
                # Filter for last 3 years
                df_last_3_years = df[df.index >= three_years_ago]
                df_last_3_years.reset_index(inplace=True)
                df_last_3_years["index"] = df_last_3_years["index"].dt.strftime("%m/%d/%Y")
                df_last_3_years.rename(columns={"index": "Date"}, inplace=True)
                
                st.subheader(f"Last 3 Years of Data for {series_title}")
                st.table(df_last_3_years)

                # Download buttons
                csv_data = convert_df_to_csv(df_last_3_years)
                excel_data = convert_df_to_excel(df_last_3_years)

                st.download_button(
                    label=f"Download {series_title} as CSV",
                    data=csv_data,
                    file_name=f"{series_title.replace(' ', '_')}_last_3_years.csv",
                    mime="text/csv",
                )

                st.download_button(
                    label=f"Download {series_title} as Excel",
                    data=excel_data,
                    file_name=f"{series_title.replace(' ', '_')}_last_3_years.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            else:
                st.warning(f"Error calculating YoY for {series_title}.")
        else:
            st.warning(f"Could not retrieve data for {series_title}.")
    fig_cpi.update_layout(title="CPI and Core CPI (y/y)", xaxis_title="Date", yaxis_title="Percent Change (y/y)")
    st.plotly_chart(fig_cpi, use_container_width=True)

elif "id" in selected_data:  # Handle other indicators
    df = get_fred_data(selected_data["id"], selected_data["title"])
    if df is not None:
        if "yoy_func" in selected_data:
            df = selected_data["yoy_func"](df, selected_data["title"])
            if df is None:
                st.warning("Error calculating YoY.")
                st.stop()

        # Filter data by the selected range
        df_filtered = df[(df.index >= pd.to_datetime(start_date)) & (df.index <= pd.to_datetime(end_date))]
        if not df_filtered.empty:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df_filtered.index, y=df_filtered[selected_data["title"]], mode='lines'))
            fig.update_layout(title=selected_indicator, xaxis_title="Date", yaxis_title=selected_data["title"])
            st.plotly_chart(fig, use_container_width=True)

            # Filter for last 3 years and display as table
            df_last_3_years = df[df.index >= three_years_ago]
            df_last_3_years.reset_index(inplace=True)
            df_last_3_years["index"] = df_last_3_years["index"].dt.strftime("%m/%d/%Y")
            df_last_3_years.rename(columns={"index": "Date"}, inplace=True)
            
            st.subheader(f"Last 3 Years of Data for {selected_data['title']}")
            st.table(df_last_3_years)

            # Download buttons
            csv_data = convert_df_to_csv(df_last_3_years)
            excel_data = convert_df_to_excel(df_last_3_years)

            st.download_button(
                label="Download as CSV",
                data=csv_data,
                file_name=f"{selected_data['title'].replace(' ', '_')}_last_3_years.csv",
                mime="text/csv",
            )

            st.download_button(
                label="Download as Excel",
                data=excel_data,
                file_name=f"{selected_data['title'].replace(' ', '_')}_last_3_years.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        else:
            st.warning("No data available for the selected indicator within the chosen date range.")
    else:
        st.warning("Could not retrieve data for the selected indicator.")

