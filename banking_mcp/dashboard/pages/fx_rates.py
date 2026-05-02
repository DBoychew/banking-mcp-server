"""Dashboard page: FX rates from BNB."""

import pandas as pd
import plotly.express as px
import streamlit as st

from banking_mcp.dashboard.utils import fetch_fx_rates


_COMMON_CURRENCIES = [
    "USD",
    "EUR",
    "GBP",
    "CHF",
    "JPY",
    "CAD",
    "AUD",
    "SEK",
    "NOK",
    "DKK",
]


def render() -> None:
    st.subheader("FX Rates (BNB)")

    col1, col2 = st.columns([3, 1])
    with col1:
        selected = st.multiselect(
            "Currency filter",
            options=_COMMON_CURRENCIES,
            default=["USD", "EUR", "GBP", "CHF"],
        )
    with col2:
        show_all = st.checkbox("Show all")

    currencies_param = "" if show_all else ",".join(selected)

    with st.spinner("Loading rates from BNB..."):
        rates = fetch_fx_rates(currencies_param)

    if not rates:
        st.error("Could not load exchange rates from BNB.")
        return

    df = pd.DataFrame(rates)
    rename_map = {
        "code": "Code",
        "name": "Currency",
        "rate_per_eur": "BGN per 1 EUR equivalent",
        "eur_per_unit": "EUR per unit",
        "as_of": "Date",
    }
    display_cols = [c for c in rename_map if c in df.columns]
    df_display = df[display_cols].rename(columns=rename_map)

    st.dataframe(df_display, width="stretch", hide_index=True)

    chart_df = df[df["code"].isin(selected if not show_all else df["code"].tolist())].copy()
    if "rate_per_eur" in chart_df.columns and not chart_df.empty:
        chart_df["rate_per_eur"] = pd.to_numeric(chart_df["rate_per_eur"], errors="coerce")
        chart_df = chart_df.dropna(subset=["rate_per_eur"])
        if not chart_df.empty:
            fig = px.bar(
                chart_df,
                x="code",
                y="rate_per_eur",
                labels={"code": "Currency", "rate_per_eur": "BGN vs EUR"},
                title="Exchange rates against EUR",
                color="rate_per_eur",
                color_continuous_scale="Blues",
            )
            st.plotly_chart(fig, width="stretch")
