import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from supabase import create_client, Client
from datetime import datetime, date
from dateutil.relativedelta import relativedelta

# --- 1. KONFIGURATION ---
st.set_page_config(page_title="Provisions-Tracker", layout="centered")

def format_euro(val):
    if pd.isna(val) or val == 0: return "0,00 €"
    return "{:,.2f} €".format(val).replace(",", "X").replace(".", ",").replace("X", ".")

# --- CSS ---
st.markdown("""
    <style>
    h1 { font-size: 1.6rem !important; }
    .kachel-grid { display: flex; flex-wrap: wrap; gap: 10px; justify-content: space-between; }
    .kachel-container {
        background-color: #f0f2f6; border-radius: 10px; padding: 12px 5px;
        text-align: center; border: 1px solid #e6e9ef; flex: 0 0 48%;
        box-sizing: border-box; margin-bottom: 5px;
    }
    .kachel-titel { font-size: 0.75rem; color: #5f6368; }
    .kachel-wert { font-size: 1.1rem; font-weight: bold; color: #2e7d32; }
    .stButton>button { border-radius: 20px; background-color: #2e7d32 !important; color: white !important; }
    </style>
    """, unsafe_allow_html=True)

# --- DB VERBINDUNG ---
@st.cache_resource
def init_connection():
    url = st.secrets["supabase_url"]
    key = st.secrets["supabase_key"]
    return create_client(url, key)

supabase = init_connection()

def load_data():
    res = supabase.table("ring_prov").select("*").order("Monat").execute()
    if not res.data: return pd.DataFrame()
    df = pd.DataFrame(res.data)
    df['Monat'] = pd.to_datetime(df['Monat'])
    df['Betrag'] = pd.to_numeric(df['Betrag'])
    return df

# --- KORREKTE LOGIK ---
def calculate_all(df_db):
    # 1. Ist-Daten sortieren
    df_ist = df_db.sort_values('Monat').copy()
    
    # 2. Letzten Monat bestimmen
    last_date = df_ist['Monat'].max()
    last_amount = df_ist['Betrag'].iloc[-1]
    
    # 3. Trend berechnen (YoY)
    df_ist['prev_year'] = df_ist['Betrag'].shift(12)
    df_ist['growth'] = (df_ist['Betrag'] / df_ist['prev_year']) - 1
    current_trend = df_ist['growth'].dropna().tail(6).mean() if not df_ist['growth'].dropna().empty else 0
    
    # 4. Historische Prognose (nur für Monate mit Ist-Werten)
    df_ist['hist_forecast'] = df_ist['prev_year'] * (1 + current_trend)
    
    # 5. Forecast (Startet erst einen Monat NACH dem letzten Ist-Wert)
    future = []
    for i in range(1, 13):
        f_date = last_date + pd.DateOffset(months=i)
        target_prev = f_date - pd.DateOffset(years=1)
        prev_val = df_ist[df_ist['Monat'] == target_prev]['Betrag']
        f_amt = prev_val.values[0] * (1 + current_trend) if not prev_val.empty else df_ist['Betrag'].tail(6).mean()
        future.append({'Monat': f_date, 'Betrag': f_amt})
    
    return df_ist, pd.DataFrame(future), current_trend, (last_date, last_amount)

# --- UI ---
st.title("Provisions-Dashboard")

with st.expander("➕ Neue Daten erfassen"):
    with st.form("input", clear_on_submit=True):
        # Standard auf Vormonat setzen
        d_val = date.today().replace(day=1) - relativedelta(months=1)
        i_date = st.date_input("Monat", value=d_val)
        i_amt = st.number_input("Betrag in €", min_value=0.0, format="%.2f")
        if st.form_submit_button("Speichern"):
            supabase.table("ring_prov").upsert({"Monat": i_date.strftime("%Y-%m-%d"), "Betrag": i_amt}).execute()
            st.cache_data.clear()
            st.rerun()

try:
    df_ist, df_future, trend_val, last_pt = calculate_all(load_data())
    
    if not df_ist.empty:
        # Kacheln
        st.markdown(f"""
            <div class="kachel-grid">
                <div class="kachel-container"><div class="kachel-titel">Letzter Monat</div><div class="kachel-wert">{format_euro(last_pt[1])}</div></div>
                <div class="kachel-container"><div class="kachel-titel">Trend (Ø 6M YoY)</div><div class="kachel-wert">{trend_val*100:+.1f} %</div></div>
                <div class="kachel-container"><div class="kachel-titel">Forecast (Folgem.)</div><div class="kachel-wert">{format_euro(df_future['Betrag'].iloc[0])}</div></div>
                <div class="kachel-container"><div class="kachel-titel">Ø 12 Monate</div><div class="kachel-wert">{format_euro(df_ist['Betrag'].tail(12).mean())}</div></div>
                <div class="kachel-container"><div class="kachel-titel">Summe (Gesamt)</div><div class="kachel-wert">{format_euro(df_ist['Betrag'].sum())}</div></div>
                <div class="kachel-container"><div class="kachel-titel">Status</div><div class="kachel-wert">Lückenlos</div></div>
            </div>
        """, unsafe_allow_html=True)

        # --- CHART ---
        fig = go.Figure()

        # 1. Schattenfläche (Prognose der Vergangenheit)
        # Endet hart bei last_date
        fig.add_trace(go.Scatter(
            x=df_ist['Monat'], y=df_ist['hist_forecast'],
            fill='tozeroy', mode='none', name='Prognose',
            fillcolor='rgba(169, 169, 169, 0.15)',
            hovertemplate="Prognose: %{y:,.2f} €<extra></extra>"
        ))

        # 2. Ist-Linie (Grün)
        fig.add_trace(go.Scatter(
            x=df_ist['Monat'], y=df_ist['Betrag'],
            mode='lines+markers', name='Ist',
            line=dict(color='#2e7d32', width=3), marker=dict(size=8),
            hovertemplate="Ist: %{y:,.2f} €<extra></extra>"
        ))

        # 3. Forecast-Linie (Grau) - Keine Verbindung, um Überlappung im Hover zu vermeiden
        fig.add_trace(go.Scatter(
            x=df_future['Monat'], y=df_future['Betrag'],
            mode='lines+markers', name='Forecast',
            line=dict(color='#A9A9A9', width=3), marker=dict(size=8),
            hovertemplate="Forecast: %{y:,.2f} €<extra></extra>"
        ))

        fig.update_layout(
            separators=".,", margin=dict(l=5, r=5, t=10, b=10),
            legend=dict(orientation="h", y=1.1, x=0.5, xanchor="center"),
            hovermode="x unified", # Jetzt wieder unified, da die Datenreihen getrennt sind!
            yaxis=dict(title="€", tickformat=",.", exponentformat="none"),
            xaxis=dict(tickformat="%b %y")
        )
        st.plotly_chart(fig, use_container_width=True)

except Exception as e:
    st.error(f"Fehler: {e}")
