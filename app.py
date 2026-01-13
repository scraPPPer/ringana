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

# --- CSS (Dein 2x3 Grid) ---
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

# --- 2. VERBINDUNG ---
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

# --- 3. LOGIK (DEIN ANSATZ) ---
def calculate_combined_logic(df_db):
    df = df_db.sort_values('Monat').copy()
    last_dt = df['Monat'].max()
    
    # Trend berechnen
    df['prev_yr'] = df['Betrag'].shift(12)
    df['growth'] = (df['Betrag'] / df['prev_yr']) - 1
    trend = df['growth'].dropna().tail(6).mean() if not df['growth'].dropna().empty else 0
    
    # Durchgehende Zeitachse erstellen
    all_dates = pd.date_range(start=df['Monat'].min(), end=last_dt + pd.DateOffset(months=12), freq='MS')
    df_combined = pd.DataFrame({'Monat': all_dates})
    df_combined = df_combined.merge(df[['Monat', 'Betrag']], on='Monat', how='left')
    
    # Prognose berechnen
    def get_prognose(row):
        target_prev = row['Monat'] - pd.DateOffset(years=1)
        prev_val = df[df['Monat'] == target_prev]['Betrag']
        if not prev_val.empty:
            return prev_val.values[0] * (1 + trend)
        return None

    df_combined['prognose'] = df_combined.apply(get_prognose, axis=1)
    
    # Ampel-Farben bestimmen
    def get_color(row):
        if pd.isna(row['Betrag']) or pd.isna(row['prognose']):
            return '#2e7d32' # Default Grün
        return '#2e7d32' if row['Betrag'] >= row['prognose'] else '#ff9800' # Grün oder Orange

    df_combined['punkt_farbe'] = df_combined.apply(get_color, axis=1)
    
    return df_combined, trend, (last_dt, df['Betrag'].iloc[-1])

# --- 4. APP ---
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
    df_total, trend_val, last_pt = calculate_combined_logic(load_data())
    
    if not df_total.empty:
        # Filter Buttons
        st.write("Zeitraum filtern:")
        c_f1, c_f2, c_f3 = st.columns(3)
        if 'filter' not in st.session_state: st.session_state.filter = "alles"
        if c_f1.button("Alles", use_container_width=True): st.session_state.filter = "alles"
        if c_f2.button("1 Zeitjahr", use_container_width=True): st.session_state.filter = "1j"
        if c_f3.button("3 Zeitjahre", use_container_width=True): st.session_state.filter = "3j"

        if st.session_state.filter == "1j":
            df_plot = df_total[df_total['Monat'] > (last_pt[0] - pd.DateOffset(years=1))]
        elif st.session_state.filter == "3j":
            df_plot = df_total[df_total['Monat'] > (last_pt[0] - pd.DateOffset(years=3))]
        else:
            df_plot = df_total

        # Kacheln
        st.markdown(f"""
            <div class="kachel-grid">
                <div class="kachel-container"><div class="kachel-titel">Letzter Monat</div><div class="kachel-wert">{format_euro(last_pt[1])}</div></div>
                <div class="kachel-container"><div class="kachel-titel">Trend (Ø 6M YoY)</div><div class="kachel-wert">{trend_val*100:+.1f} %</div></div>
                <div class="kachel-container"><div class="kachel-titel">Forecast (Folgem.)</div><div class="kachel-wert">{format_euro(df_total[df_total['Monat'] > last_pt[0]]['prognose'].iloc[0])}</div></div>
                <div class="kachel-container"><div class="kachel-titel">Ø 12 Monate</div><div class="kachel-wert">{format_euro(df_total.dropna(subset=['Betrag'])['Betrag'].tail(12).mean())}</div></div>
                <div class="kachel-container"><div class="kachel-titel">Summe (Zeitraum)</div><div class="kachel-wert">{format_euro(df_plot['Betrag'].sum())}</div></div>
                <div class="kachel-container"><div class="kachel-titel">Status</div><div class="kachel-wert">Korrekt</div></div>
            </div>
        """, unsafe_allow_html=True)

        # --- CHART ---
        fig = go.Figure()

        # 1. Durchgehende Fläche (Prognose)
        fig.add_trace(go.Scatter(
            x=df_plot['Monat'], y=df_plot['prognose'],
            fill='tozeroy', mode='none', name='Prognose',
            fillcolor='rgba(169, 169, 169, 0.2)',
            hovertemplate="Prognose: %{y:,.2f} €<extra></extra>"
        ))

        # 2. Ist-Linie (Dunkelgrau mit farbigen Punkten)
        fig.add_trace(go.Scatter(
            x=df_plot['Monat'], y=df_plot['Betrag'],
            mode='lines+markers', name='Ist',
            line=dict(color='#424242', width=2), # Dunkelgraue Linie
            marker=dict(
                size=10, 
                color=df_plot['punkt_farbe'], # Dynamische Farbe
                line=dict(width=1, color='white')
            ),
            hovertemplate="Ist: %{y:,.2f} €<extra></extra>",
            connectgaps=False
        ))

        fig.update_layout(
            separators=".,", margin=dict(l=5, r=5, t=10, b=10),
            legend=dict(orientation="h", y=1.1, x=0.5, xanchor="center"),
            hovermode="x unified",
            yaxis=dict(title="€", tickformat=",.", exponentformat="none"),
            xaxis=dict(tickformat="%b %y")
        )
        st.plotly_chart(fig, use_container_width=True)

except Exception as e:
    st.error(f"Fehler: {e}")
