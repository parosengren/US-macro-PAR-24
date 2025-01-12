import streamlit as st
import pandas as pd
import fredapi
import plotly.graph_objects as go
from datetime import datetime, timedelta

# FRED API Key (REPLACE THIS WITH YOUR ACTUAL KEY)
FRED_API_KEY = "73d91c54519573fad1e3a2bb990af710"

fred = fredapi.Fred(api_key=FRED_API_KEY)

############################################################################
# 1. Data Fetching / Utility Functions
############################################################################

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
    """
    Year-over-year inflation:
    yoy = ((index / index.shift(12)) - 1)*100, 
    using a monthly resample to ensure monthly frequency.
    """
    try:
        df_yoy = df.resample('MS').last().pct_change(12) * 100
        df_yoy.columns = [title]
        return df_yoy
    except Exception as e:
        st.error(f"Error calculating YoY for {title}: {e}")
        return None

def calculate_monthly_change(df, title):
    """
    Resample to monthly (start of month), take the last data point each month,
    then compute the month-to-month difference, multiplied by 1,000.
    """
    try:
        df_m = df.resample('MS').last()
        df_diff = df_m.diff() * 1000
        df_diff.columns = [title]
        return df_diff
    except Exception as e:
        st.error(f"Error calculating monthly change for {title}: {e}")
        return None

def annualized_inflation_3m(df):
    """
    annualized 3-month inflation = ((CPI_t / CPI_{t-3})^(12/3) - 1)*100
    """
    result = (df / df.shift(3))**4 - 1
    return result * 100

def annualized_inflation_6m(df):
    """
    annualized 6-month inflation = ((CPI_t / CPI_{t-6})^(12/6) - 1)*100
    """
    result = (df / df.shift(6))**2 - 1
    return result * 100

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

############################################################################
# 2. Streamlit App
############################################################################

st.set_page_config(page_title="US Macro Dashboard")
st.title("US Macro Dashboard")

# --- Timeline Selector ---
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
    "Employment": {
        "series": [
            {
                "id": "PAYEMS",
                "title": "Monthly Change in Nonfarm Payrolls",
                "monthly_func": calculate_monthly_change
            },
            {"id": "UNRATE", "title": "Unemployment Rate (%)"},
        ]
    },
    "Inflation - CPI": {
        "series": [
            {"id": "CPIAUCSL",  "title": "CPI (y/y)",      "yoy_func": calculate_cpi_yoy},
            {"id": "CPILFESL", "title": "Core CPI (y/y)", "yoy_func": calculate_cpi_yoy},
        ]
    },
    "10-Year Treasury Yield": {"id": "DGS10", "title": "10-Year Treasury Yield (%)"},
    "S&P 500": {"id": "SP500", "title": "S&P 500"},
}

# --- Indicator Selection Dropdown ---
selected_indicator = st.selectbox("Select an Economic Indicator", list(indicators.keys()))

# --- Display Selected Indicator ---
st.header(selected_indicator)
selected_data = indicators[selected_indicator]

three_years_ago = datetime.now() - timedelta(days=3 * 365)

############################################################################
# 2a. Inflation (CPI + Core CPI) -> Multiple Series
############################################################################
if selected_indicator == "Inflation - CPI":
    # Original chart type (Line vs. Bar) for the y/y charts
    chart_type = st.radio(
        "Select Chart Type for CPI Chart",
        options=["Line Chart", "Bar Chart"],
        index=0,  # Default to "Line Chart"
        horizontal=True,
        key="cpi_chart_type"
    )

    combined_fig = go.Figure()
    data_frames = []

    # We'll store the raw monthly data for CPI & Core CPI for the new 3/6m charts
    cpi_df = None
    core_cpi_df = None

    # Loop over "CPI (y/y)" and "Core CPI (y/y)"
    for series in selected_data["series"]:
        df = get_fred_data(series["id"], series["title"])
        if df is not None:
            # Filter to date range
            df_filtered = df[
                (df.index >= pd.to_datetime(start_date)) &
                (df.index <= pd.to_datetime(end_date))
            ]

            # If yoy_func is present, transform for y/y inflation
            if "yoy_func" in series:
                df_filtered = series["yoy_func"](df_filtered, series["title"])

            if df_filtered is not None and not df_filtered.empty:
                # Add to combined_fig
                if chart_type == "Line Chart":
                    combined_fig.add_trace(
                        go.Scatter(
                            x=df_filtered.index,
                            y=df_filtered[series["title"]],
                            mode="lines",
                            name=series["title"]
                        )
                    )
                else:  # Bar Chart
                    combined_fig.add_trace(
                        go.Bar(
                            x=df_filtered.index,
                            y=df_filtered[series["title"]],
                            name=series["title"]
                        )
                    )

                # Prepare last 3 years (for table)
                df_last_3_years = df[df.index >= three_years_ago]
                if "yoy_func" in series:
                    df_last_3_years = series["yoy_func"](df_last_3_years, series["title"])

                if df_last_3_years is not None and not df_last_3_years.empty:
                    df_last_3_years.reset_index(inplace=True)
                    df_last_3_years.rename(columns={"index": "Datetime"}, inplace=True)
                    df_last_3_years.sort_values(by="Datetime", ascending=False, inplace=True)
                    df_last_3_years["Datetime"] = df_last_3_years["Datetime"].dt.strftime("%m/%d/%Y")
                    df_last_3_years.rename(columns={"Datetime": "Date"}, inplace=True)
                    data_frames.append((series["title"], df_last_3_years))

            # Save the raw data for 3/6 month charts
            if series["id"] == "CPIAUCSL":
                cpi_df = df
            elif series["id"] == "CPILFESL":
                core_cpi_df = df
        else:
            st.warning(f"Could not retrieve data for {series['title']}.")

    # Display the main yoy chart
    if combined_fig.data:
        combined_fig.update_layout(
            title="CPI and Core CPI (y/y)",
            xaxis_title="Date",
            yaxis_title="Percent Change (y/y)",
            yaxis=dict(autorange=True),
        )
        st.plotly_chart(combined_fig, use_container_width=True)

    # Display yoy tables
    for title, df_last_3_years in data_frames:
        st.subheader(f"Last 3 Years of Data for {title} (YoY)")
        st.dataframe(df_last_3_years, height=300)

        csv_data = convert_df_to_csv(df_last_3_years)
        excel_data = convert_df_to_excel(df_last_3_years)

        st.download_button(
            label=f"Download {title} as CSV",
            data=csv_data,
            file_name=f"{title.replace(' ', '_')}_last_3_years.csv",
            mime="text/csv",
        )
        st.download_button(
            label=f"Download {title} as Excel",
            data=excel_data,
            file_name=f"{title.replace(' ', '_')}_last_3_years.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    # --------------------------------------------------------------------
    # NEW: Additional Charts for 3m & 6m Annualized CPI and Core CPI
    # --------------------------------------------------------------------
    # 1) CPI (3 & 6 Month Annualized)
    if cpi_df is not None:
        cpi_filtered = cpi_df[
            (cpi_df.index >= pd.to_datetime(start_date)) &
            (cpi_df.index <= pd.to_datetime(end_date))
        ].resample('MS').last()

        cpi_3m = annualized_inflation_3m(cpi_filtered)
        cpi_6m = annualized_inflation_6m(cpi_filtered)

        cpi_annualized_fig = go.Figure()
        cpi_annualized_fig.add_trace(go.Scatter(
            x=cpi_3m.index, y=cpi_3m.iloc[:,0],
            mode='lines', name="CPI (3m Ann.)"
        ))
        cpi_annualized_fig.add_trace(go.Scatter(
            x=cpi_6m.index, y=cpi_6m.iloc[:,0],
            mode='lines', name="CPI (6m Ann.)"
        ))
        cpi_annualized_fig.update_layout(
            title="CPI (3 & 6 Month Annualized)",
            xaxis_title="Date",
            yaxis_title="Annualized Inflation (%)",
            yaxis=dict(autorange=True),
        )
        st.plotly_chart(cpi_annualized_fig, use_container_width=True)

    # 2) Core CPI (3 & 6 Month Annualized)
    if core_cpi_df is not None:
        core_cpi_filtered = core_cpi_df[
            (core_cpi_df.index >= pd.to_datetime(start_date)) &
            (core_cpi_df.index <= pd.to_datetime(end_date))
        ].resample('MS').last()

        core_3m = annualized_inflation_3m(core_cpi_filtered)
        core_6m = annualized_inflation_6m(core_cpi_filtered)

        core_annualized_fig = go.Figure()
        core_annualized_fig.add_trace(go.Scatter(
            x=core_3m.index, y=core_3m.iloc[:,0],
            mode='lines', name="Core CPI (3m Ann.)"
        ))
        core_annualized_fig.add_trace(go.Scatter(
            x=core_6m.index, y=core_6m.iloc[:,0],
            mode='lines', name="Core CPI (6m Ann.)"
        ))
        core_annualized_fig.update_layout(
            title="Core CPI (3 & 6 Month Annualized)",
            xaxis_title="Date",
            yaxis_title="Annualized Inflation (%)",
            yaxis=dict(autorange=True),
        )
        st.plotly_chart(core_annualized_fig, use_container_width=True)

############################################################################
# 2b. Multi-Series (Employment, etc.) 
############################################################################
elif "series" in selected_data:  # e.g. "Employment"
    for series in selected_data["series"]:
        st.subheader(series["title"])

        df = get_fred_data(series["id"], series["title"])
        if df is not None:
            df_filtered = df[
                (df.index >= pd.to_datetime(start_date)) &
                (df.index <= pd.to_datetime(end_date))
            ]

            # If there's a custom monthly_func (e.g. PAYEMS)
            if "monthly_func" in series:
                df_filtered = series["monthly_func"](df_filtered, series["title"])

            # If it's PAYEMS => default bar
            default_chart_index = 0
            if series["id"] == "PAYEMS" and "monthly_func" in series:
                default_chart_index = 1

            chart_type = st.radio(
                f"Select Chart Type for {series['title']}",
                options=["Line Chart", "Bar Chart"],
                index=default_chart_index,
                horizontal=True,
                key=f"chart_type_{series['id']}_{series['title']}",
            )

            if df_filtered is not None and not df_filtered.empty:
                fig = go.Figure()
                if chart_type == "Line Chart":
                    fig.add_trace(go.Scatter(x=df_filtered.index, y=df_filtered[series["title"]], mode='lines'))
                else:
                    fig.add_trace(go.Bar(x=df_filtered.index, y=df_filtered[series["title"]]))

                fig.update_layout(
                    title=series["title"],
                    xaxis_title="Date",
                    yaxis_title=series["title"],
                    yaxis=dict(autorange=True),
                )
                st.plotly_chart(fig, use_container_width=True)

                df_last_3_years = df[df.index >= three_years_ago]
                if "monthly_func" in series:
                    df_last_3_years = series["monthly_func"](df_last_3_years, series["title"])

                if df_last_3_years is not None and not df_last_3_years.empty:
                    df_last_3_years = df_last_3_years.sort_index(ascending=False)
                    df_last_3_years.reset_index(inplace=True)
                    df_last_3_years["index"] = df_last_3_years["index"].dt.strftime("%m/%d/%Y")
                    df_last_3_years.rename(columns={"index": "Date"}, inplace=True)

                    st.subheader(f"Last 3 Years of Data for {series['title']}")
                    st.dataframe(df_last_3_years, height=300)

                    csv_data = convert_df_to_csv(df_last_3_years)
                    excel_data = convert_df_to_excel(df_last_3_years)

                    st.download_button(
                        label=f"Download {series['title']} as CSV",
                        data=csv_data,
                        file_name=f"{series['title'].replace(' ', '_')}_last_3_years.csv",
                        mime="text/csv",
                    )
                    st.download_button(
                        label=f"Download {series['title']} as Excel",
                        data=excel_data,
                        file_name=f"{series['title'].replace(' ', '_')}_last_3_years.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                else:
                    st.warning(f"No data available for {series['title']} in the last 3 years.")
            else:
                st.warning(f"No data available for {series['title']} within the selected date range.")
        else:
            st.warning(f"Could not retrieve data for {series['title']}.")

############################################################################
# 2c. Single-Series (GDP, 10Y Treasury, S&P 500)
############################################################################
elif "id" in selected_data:
    st.subheader(selected_data["title"])

    df = get_fred_data(selected_data["id"], selected_data["title"])
    if df is not None:
        # Forward-fill if it's DGS10 (10Y Treasury) or SP500
        if selected_data["id"] in ["DGS10", "SP500"]:
            df.fillna(method="ffill", inplace=True)

        df_filtered = df[
            (df.index >= pd.to_datetime(start_date)) &
            (df.index <= pd.to_datetime(end_date))
        ]

        # If it's GDP => default bar
        default_chart_index = 0
        if selected_data["id"] == "A191RL1Q225SBEA":
            default_chart_index = 1

        if not df_filtered.empty:
            chart_type = st.radio(
                "Select Chart Type",
                options=["Line Chart", "Bar Chart"],
                index=default_chart_index,
                horizontal=True,
            )

            # If SP500, compute 50-day and 200-day SMAs
            if selected_data["id"] == "SP500":
                df_filtered["SMA_50"] = df_filtered[selected_data["title"]].rolling(window=50).mean()
                df_filtered["SMA_200"] = df_filtered[selected_data["title"]].rolling(window=200).mean()

            fig = go.Figure()

            if chart_type == "Line Chart":
                # Main data line
                fig.add_trace(go.Scatter(
                    x=df_filtered.index,
                    y=df_filtered[selected_data["title"]],
                    mode='lines',
                    name=selected_data["title"]
                ))

                # If SP500, add SMA lines
                if selected_data["id"] == "SP500":
                    fig.add_trace(go.Scatter(
                        x=df_filtered.index,
                        y=df_filtered["SMA_50"],
                        mode='lines',
                        line=dict(color='green'),
                        name='SMA (50-day)'
                    ))
                    fig.add_trace(go.Scatter(
                        x=df_filtered.index,
                        y=df_filtered["SMA_200"],
                        mode='lines',
                        line=dict(color='red'),
                        name='SMA (200-day)'
                    ))

            else:  # Bar Chart
                fig.add_trace(go.Bar(
                    x=df_filtered.index,
                    y=df_filtered[selected_data["title"]],
                    name=selected_data["title"]
                ))
                # If SP500, overlay SMA lines
                if selected_data["id"] == "SP500":
                    fig.add_trace(go.Scatter(
                        x=df_filtered.index,
                        y=df_filtered["SMA_50"],
                        mode='lines',
                        line=dict(color='green'),
                        name='SMA (50-day)'
                    ))
                    fig.add_trace(go.Scatter(
                        x=df_filtered.index,
                        y=df_filtered["SMA_200"],
                        mode='lines',
                        line=dict(color='red'),
                        name='SMA (200-day)'
                    ))

            fig.update_layout(
                title=selected_data["title"],
                xaxis_title="Date",
                yaxis_title=selected_data["title"],
                yaxis=dict(autorange=True),
            )
            st.plotly_chart(fig, use_container_width=True)

            # Last 3 years table
            df_last_3_years = df[df.index >= three_years_ago]
            df_last_3_years = df_last_3_years.sort_index(ascending=False)
            df_last_3_years.reset_index(inplace=True)
            df_last_3_years["index"] = df_last_3_years["index"].dt.strftime("%m/%d/%Y")
            df_last_3_years.rename(columns={"index": "Date"}, inplace=True)

            st.subheader(f"Last 3 Years of Data for {selected_data['title']}")
            st.dataframe(df_last_3_years, height=300)

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
            st.warning(f"No data available for {selected_data['title']} within the selected date range.")
    else:
        st.warning("Could not retrieve data for the selected indicator.")
