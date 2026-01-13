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
        if col_f1.button("Alles", use_container_width=True): st.session_state.filter = "alles"
        if col_f2.button("1 Zeitjahr", use_container_width=True): st.session_state.filter = "1j"
        if col_f3.button("3 Zeitjahre", use_container_width=True): st.session_state.filter = "3j"

        if st.session_state.filter == "1j":
            df_plot = df_raw[df_raw['Monat'] > (last_pt[0] - pd.DateOffset(years=1))]
        elif st.session_state.filter == "3j":
            df_plot = df_raw[df_raw['Monat'] > (last_pt[0] - pd.DateOffset(years=3))]
        else:
            df_plot = df_raw

        sum_period = df_plot['Betrag'].sum()

        # Kacheln
        st.markdown(f"""
            <div class="kachel-grid">
                <div class="kachel-container"><div class="kachel-titel">Letzter Monat ({last_pt[0].strftime('%m/%y')})</div><div class="kachel-wert">{format_euro(last_pt[1])}</div></div>
                <div class="kachel-container"><div class="kachel-titel">Trend (Ø 6M YoY)</div><div class="kachel-wert">{trend_val*100:+.1f} %</div></div>
                <div class="kachel-container"><div class="kachel-titel">Forecast ({df_future['Monat'].iloc[0].strftime('%m/%y')})</div><div class="kachel-wert">{format_euro(df_future['Betrag'].iloc[0])}</div></div>
                <div class="kachel-container"><div class="kachel-titel">Ø 12 Monate</div><div class="kachel-wert">{format_euro(df_raw['Betrag'].tail(12).mean())}</div></div>
                <div class="kachel-container"><div class="kachel-titel">Summe Zeitraum</div><div class="kachel-wert">{format_euro(sum_period)}</div></div>
                <div class="kachel-container"><div class="kachel-titel">Status</div><div class="kachel-wert">Analysiert</div></div>
            </div>
        """, unsafe_allow_html=True)

        # --- CHART ---
        fig = go.Figure()

        # 1. Schatten-Fläche (Nur Ist-Bereich)
        df_area = df_plot.dropna(subset=['hist_forecast'])
        fig.add_trace(go.Scatter(
            x=df_area['Monat'], y=df_area['hist_forecast'],
            fill='tozeroy', mode='none', name='Prognose',
            fillcolor='rgba(169, 169, 169, 0.15)',
            hovertemplate="Prognose: %{y:,.2f} €<extra></extra>"
        ))

        # 2. Ist-Daten (Grün) - Endet hart beim letzten DB-Eintrag
        fig.add_trace(go.Scatter(
            x=df_plot['Monat'], y=df_plot['Betrag'],
            mode='lines+markers', name='Ist',
            line=dict(color='#2e7d32', width=3), marker=dict(size=8),
            hovertemplate="Ist: %{y:,.2f} €<extra></extra>"
        ))

        # 3. Forecast (Grau) - Startet erst im Monat NACH dem letzten DB-Eintrag
        # Da KEINE Verbindungslinie existiert, kann Plotly hier nichts vermischen
        fig.add_trace(go.Scatter(
            x=df_future['Monat'], y=df_future['Betrag'],
            mode='lines+markers', name='Forecast',
            line=dict(color='#A9A9A9', width=3, dash='dot'), marker=dict(size=8, symbol='circle-open'),
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
