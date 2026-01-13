import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from supabase import create_client, Client
from datetime import datetime, date
from dateutil.relativedelta import relativedelta

# --- 1. SEITEN-KONFIGURATION ---
st.set_page_config(page_title="Provisions-Tracker", layout="centered")

def format_euro(val):
    if pd.isna(val) or val == 0: return "0,00 €"
    return "{:,.2f} €".format(val).replace(",", "X").replace(".", ",").replace("X", ".")

# --- CSS FÜR KACHELN ---
st.markdown("""
    <style>
    h1 { font-size: 1.6rem !important; margin-bottom: 0.5rem; }
    .kachel-grid { display: flex; flex-wrap: wrap; gap: 10px; justify-content: space-between; margin-bottom: 20px; }
    .kachel-container {
        background-color: #f0f2f6; border-radius: 10px; padding: 12px 5px;
        text-align: center; border: 1px solid #e6e9ef; flex: 0 0 48%;
        box-sizing: border-box; margin-bottom: 5px;
    }
    .kachel-titel { font-size: 0.75rem; color: #5f6368; }
    .kachel-wert { font-size: 1.1rem; font-weight: bold; color: #2e7d32; }
    .stButton>button { border-radius: 20px; font-size: 0.8rem; }
    .main-button>button { background-color: #2e7d32 !important; color: white !important; font-weight: bold; height: 3em; }
    </style>
    """, unsafe_allow_html=True)

# --- DB & DATEN ---
@st.cache_resource
def init_connection():
    return create_client(st.secrets["supabase_url"], st.secrets["supabase_key"])

supabase = init_connection()

def load_data():
    res = supabase.table("ring_prov").select("*").order("Monat").execute()
    if not res.data: return pd.DataFrame()
    df = pd.DataFrame(res.data)
    df['Monat'] = pd.to_datetime(df['Monat'])
    df['Betrag'] = pd.to_numeric(df['Betrag'])
    return df

# --- LOGIK ---
def calculate_logic(df_db):
    df_ist = df_db.sort_values('Monat').copy()
    last_dt = df_ist['Monat'].max()
    last_val = df_ist['Betrag'].iloc[-1]
    
    df_ist['prev_yr'] = df_ist['Betrag'].shift(12)
    df_ist['growth'] = (df_ist['Betrag'] / df_ist['prev_yr']) - 1
    trend = df_ist['growth'].dropna().tail(6).mean() if not df_ist['growth'].dropna().empty else 0
    df_ist['prognose_flaeche'] = df_ist['prev_yr'] * (1 + trend)
    
    future = []
    for i in range(1, 13):
        f_dt = last_dt + pd.DateOffset(months=i)
        target = f_dt - pd.DateOffset(years=1)
        prev = df_ist[df_ist['Monat'] == target]['Betrag']
        f_val = prev.values[0] * (1 + trend) if not prev.empty else df_ist['Betrag'].tail(6).mean()
        future.append({'Monat': f_dt, 'Betrag': f_val})
    
    return df_ist, pd.DataFrame(future), trend, (last_dt, last_val)

# --- UI ---
st.title("Provisions-Dashboard")

with st.expander("➕ Neue Daten erfassen"):
    with st.form("input", clear_on_submit=True):
        d_val = date.today().replace(day=1) - relativedelta(months=1)
        i_date = st.date_input("Monat", value=d_val)
        i_amt = st.number_input("Betrag in €", min_value=0.0, format="%.2f")
        if st.form_submit_button("Speichern"):
            supabase.table("ring_prov").upsert({"Monat": i_date.strftime("%Y-%m-%d"), "Betrag": i_amt}).execute()
            st.cache_data.clear()
            st.rerun()

try:
    df_ist, df_future, trend_val, last_pt = calculate_logic(load_data())
    
    if not df_ist.empty:
        # Buttons
        st.write("Zeitraum filtern:")
        c_f1, c_f2, c_f3 = st.columns(3)
        if 'filter' not in st.session_state: st.session_state.filter = "alles"
        if c_f1.button("Alles", use_container_width=True): st.session_state.filter = "alles"
        if c_f2.button("1 Zeitjahr", use_container_width=True): st.session_state.filter = "1j"
        if c_f3.button("3 Zeitjahre", use_container_width=True): st.session_state.filter = "3j"

        if st.session_state.filter == "1j":
            df_plot = df_ist[df_ist['Monat'] > (last_pt[0] - pd.DateOffset(years=1))]
            df_prev = df_ist[(df_ist['Monat'] <= (last_pt[0] - pd.DateOffset(years=1))) & (df_ist['Monat'] > (last_pt[0] - pd.DateOffset(years=2)))]
        elif st.session_state.filter == "3j":
            df_plot = df_ist[df_ist['Monat'] > (last_pt[0] - pd.DateOffset(years=3))]
            df_prev = df_ist[(df_ist['Monat'] <= (last_pt[0] - pd.DateOffset(years=3))) & (df_ist['Monat'] > (last_pt[0] - pd.DateOffset(years=6)))]
        else:
            df_plot = df_ist
            df_prev = pd.DataFrame()

        sum_period = df_plot['Betrag'].sum()
        diff_val = f"{((sum_period / df_prev['Betrag'].sum()) - 1) * 100:+.1f} %" if not df_prev.empty else "--"

        # Kacheln
        st.markdown(f"""
            <div class="kachel-grid">
                <div class="kachel-container"><div class="kachel-titel">Letzter Monat</div><div class="kachel-wert">{format_euro(last_pt[1])}</div></div>
                <div class="kachel-container"><div class="kachel-titel">Trend (Ø 6M YoY)</div><div class="kachel-wert">{trend_val*100:+.1f} %</div></div>
                <div class="kachel-container"><div class="kachel-titel">Forecast (Folgem.)</div><div class="kachel-wert">{format_euro(df_future['Betrag'].iloc[0])}</div></div>
                <div class="kachel-container"><div class="kachel-titel">Ø 12 Monate</div><div class="kachel-wert">{format_euro(df_ist['Betrag'].tail(12).mean())}</div></div>
                <div class="kachel-container"><div class="kachel-titel">Summe (Zeitraum)</div><div class="kachel-wert">{format_euro(sum_period)}</div></div>
                <div class="kachel-container"><div class="kachel-titel">vs. Vor-Zeitraum</div><div class="kachel-wert">{diff_val}</div></div>
            </div>
        """, unsafe_allow_html=True)

        # --- CHART ---
        fig = go.Figure()
        
        # 1. Fläche (Kein Hover)
        fig.add_trace(go.Scatter(
            x=df_plot['Monat'], y=df_plot['prognose_flaeche'],
            fill='tozeroy', mode='none', name='Prognose',
            fillcolor='rgba(169, 169, 169, 0.15)', hoverinfo='skip'
        ))

        # 2. Ist (Grün)
        fig.add_trace(go.Scatter(
            x=df_plot['Monat'], y=df_plot['Betrag'],
            mode='lines+markers', name='Ist',
            line=dict(color='#2e7d32', width=3), marker=dict(size=8),
            hovertemplate="Ist: %{y:,.2f} €<extra></extra>"
        ))

        # 3. Forecast (Grau) - Keine Brücke, kein Unified-Zwang
        fig.add_trace(go.Scatter(
            x=df_future['Monat'], y=df_future['Betrag'],
            mode='lines+markers', name='Forecast',
            line=dict(color='#A9A9A9', width=3), marker=dict(size=8),
            hovertemplate="Forecast: %{y:,.2f} €<extra></extra>"
        ))

        fig.update_layout(
            separators=".,", margin=dict(l=5, r=5, t=10, b=10),
            legend=dict(orientation="h", y=1.1, x=0.5, xanchor="center"),
            hovermode="x", # Zeigt nur an, was WIRKLICH auf der X-Linie liegt
            yaxis=dict(title="€", tickformat=",.", exponentformat="none"),
            xaxis=dict(tickformat="%b %y")
        )
        st.plotly_chart(fig, use_container_width=True)

except Exception as e:
    st.error(f"Fehler: {e}")
