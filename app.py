import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from supabase import create_client, Client
from datetime import datetime, date
from dateutil.relativedelta import relativedelta

# --- 1. SEITEN-KONFIGURATION ---
st.set_page_config(page_title="Provisions-Tracker", layout="centered")

# --- HILFSFUNKTION FÜR EURO-FORMATIERUNG ---
def format_euro(val):
    if pd.isna(val) or val == 0: return "0,00 €"
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
def calculate_all(df_hist):
    df = df_hist.sort_values('Monat').copy()
    
    # Historische Prognose
    df['prev_year_amount'] = df['Betrag'].shift(12)
    df['yoy_growth'] = (df['Betrag'] / df['prev_year_amount']) - 1
    current_trend = df['yoy_growth'].dropna().tail(6).mean() if not df['yoy_growth'].dropna().empty else 0
    df['hist_forecast'] = df['prev_year_amount'] * (1 + current_trend)
    
    last_date = df['Monat'].max()
    last_amount = df['Betrag'].iloc[-1]
    
    # Forecast-Liste (Startet ohne Verbindungspunkt erst im nächsten Monat)
    future_data = []
    for i in range(1, 13):
        f_date = last_date + pd.DateOffset(months=i)
        target_prev = f_date - pd.DateOffset(years=1)
        prev_val = df[df['Monat'] == target_prev]['Betrag']
        f_amount = prev_val.values[0] * (1 + current_trend) if not prev_val.empty else df['Betrag'].tail(6).mean()
        future_data.append({'Monat': f_date, 'Betrag': f_amount})
    
    return df, pd.DataFrame(future_data), current_trend, (last_date, last_amount)

# --- 5. HAUPT-APP ---
st.title("Provisions-Dashboard")

# Datenerfassung (Standard: Vormonat)
with st.expander("➕ Neue Daten erfassen"):
    with st.form("input_form", clear_on_submit=True):
        default_date = date.today().replace(day=1) - relativedelta(months=1)
        input_date = st.date_input("Monat", value=default_date)
        input_amount = st.number_input("Betrag in €", min_value=0.0, format="%.2f")
        st.markdown('<div class="main-button">', unsafe_allow_html=True)
        if st.form_submit_button("Speichern"):
            supabase.table("ring_prov").upsert({"Monat": input_date.strftime("%Y-%m-%d"), "Betrag": input_amount}).execute()
            st.cache_data.clear()
            st.rerun()

try:
    df_raw, df_future, trend_val, last_pt = calculate_all(load_data())
    
    if not df_raw.empty:
        # Filter
        col_f1, col_f2, col_f3 = st.columns(3)
        if 'filter' not in st.session_state: st.session_state.filter = "alles"
        if col_f1.button("Alles", use
