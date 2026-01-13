import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from supabase import create_client, Client
from datetime import datetime

# --- 1. SEITEN-KONFIGURATION ---
st.set_page_config(page_title="Provisions-Tracker", layout="centered")

# --- HILFSFUNKTION FÜR EURO-FORMATIERUNG ---
def format_euro(val):
    if pd.isna(val): return "0,00 €"
    return "{:,.2f} €".format(val).replace(",", "X").replace(".", ",").replace("X", ".")

# --- CUSTOM CSS ---
st.markdown("""
    <style>
    h1 { font-size: 1.6rem !important; margin-bottom: 0.5rem; }
    .kachel-grid { display: flex; flex-wrap: wrap; gap: 10px; justify-content: space-between; margin-bottom: 20px; }
    .kachel-container {
        background-color: #f0f2f6; border-radius: 10px; padding: 12px 5px;
        text-align: center; border: 1px solid #e6e9ef; flex: 0 0 48%;
        box-sizing: border-box; margin-bottom: 5px;
    }
    .kachel-titel { font-size: 0.75rem; color: #5f6368; margin-bottom: 3px; }
    .kachel-wert { font-size: 1.1rem; font-weight: bold; color: #2e7d32; }
    .stButton>button { border-radius: 20px; font-size: 0.8rem; }
    .main-button>button { background-color: #2e7d32 !important; color: white !important; font-weight: bold; height: 3em; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. VERBINDUNG ---
@st.cache_resource
def init_connection():
    try:
        url = st.secrets["supabase_url"]
        key = st.secrets["supabase_key"]
        return create_client(url, key)
    except Exception as e:
        st.error("Verbindung fehlgeschlagen.")
        st.stop()

supabase = init_connection()

# --- 3. DATEN LADEN ---
def load_data():
    response = supabase.table("ring_prov").select("*").order("Monat").execute()
    if not response.data: return pd.DataFrame()
    df = pd.DataFrame(response.data)
    df['Monat'] = pd.to_datetime(df['Monat'])
    df['Betrag'] = pd.to_numeric(df['Betrag'])
    return df

# --- 4. LOGIK ---
def calculate_all_forecasts(df_historical):
    df = df_historical.sort_values('Monat').copy()
    df['prev_year_amount'] = df['Betrag'].shift(12)
    df['yoy_growth'] = (df['Betrag'] / df['prev_year_amount']) - 1
    df['rolling_trend'] = df['yoy_growth'].shift(1).rolling(window=6, min_periods=1).mean()
    df['hist_forecast'] = df['prev_year_amount'] * (1 + df['rolling_trend'])
    current_trend = df['yoy_growth'].dropna().tail(6).mean() if not df['yoy_growth'].dropna().empty else 0
    
    last_row = df.iloc[-1]
    last_date, last_amount = last_row['Monat'], last_row['Betrag']
    
    future_list = []
    for i in range(1, 13):
        f_month = last_date + pd.DateOffset(months=i)
        target_prev_year = f_month - pd.DateOffset(years=1)
        hist_row = df[df['Monat'] == target_prev_year]
        f_amount = hist_row['Betrag'].values[0] * (1 + current_trend) if not hist_row.empty else df['Betrag'].tail(6).mean()
        future_list.append({'Monat': f_month, 'Betrag': f_amount})
    
    return df, pd.DataFrame(future_list), current_trend, (last_date, last_amount)

# --- 5. HAUPT-APP ---
st.title("Provisions-Dashboard")

try:
    df_raw_all, df_future, trend, last_point = calculate_all_forecasts(load_data())
    
    if not df_raw_all.empty:
        # Filter (gekürzt für Übersicht)
        col_f1, col_f2, col_f3 = st.columns(3)
        if 'filter' not in st.session_state: st.session_state.filter = "alles"
        if col_f1.button("Alles"): st.session_state.filter = "alles"
        if col_f2.button("1 Zeitjahr"): st.session_state.filter = "1j"
        if col_f3.button("3 Zeitjahre"): st.session_state.filter = "3j"

        # ... (Kacheln-Logik bleibt gleich wie zuvor)
        
        # --- CHART ---
        fig = go.Figure()
        
        # 1. Ist-Daten (Grün)
        fig.add_trace(go.Scatter(
            x=df_raw_all['Monat'], y=df_raw_all['Betrag'],
            mode='lines+markers', name='Ist',
            line=dict(color='#2e7d32', width=3), marker=dict(size=8),
            hovertemplate="Ist: %{y:,.2f} €<extra></extra>"
        ))

        # 2. Reiner Verbindungspunkt (Graue Linie vom letzten Ist zum ersten Forecast)
        # Dieser Punkt hat KEINEN Hover-Text
        fig.add_trace(go.Scatter(
            x=[last_point[0], df_future['Monat'].iloc[0]],
            y=[last_point[1], df_future['Betrag'].iloc[0]],
            mode='lines', name='Verbindung',
            line=dict(color='#A9A9A9', width=3),
            hoverinfo='skip', showlegend=False
        ))

        # 3. Forecast-Daten (Grau, beginnt erst im ECHTEN Forecast-Monat)
        fig.add_trace(go.Scatter(
            x=df_future['Monat'], y=df_future['Betrag'],
            mode='lines+markers', name='Forecast',
            line=dict(color='#A9A9A9', width=3), marker=dict(size=8),
            hovertemplate="Forecast: %{y:,.2f} €<extra></extra>"
        ))

        fig.update_layout(
            separators=".,", margin=dict(l=5, r=5, t=10, b=10),
            legend=dict(orientation="h", y=1.1, x=0.5, xanchor="center"),
            hovermode="x unified",
            yaxis=dict(title="€", tickformat=",.", exponentformat="none"),
            xaxis=dict(tickformat="%b %Y")
        )
        st.plotly_chart(fig, use_container_width=True)

except Exception as e:
    st.error(f"Fehler: {e}")
