import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from supabase import create_client, Client
from datetime import datetime, date
from dateutil.relativedelta import relativedelta

# --- 1. SETUP ---
st.set_page_config(page_title="Provisions-Tracker", layout="centered")

def format_euro(val):
    if pd.isna(val) or val == 0: return "0,00 €"
    return "{:,.2f} €".format(val).replace(",", "X").replace(".", ",").replace("X", ".")

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
    .calc-box { background-color: #fff; border: 1px solid #ddd; padding: 15px; border-radius: 10px; margin-top: 20px; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. DATEN ---
@st.cache_resource
def init_connection():
    return create_client(st.secrets["supabase_url"], st.secrets["supabase_key"])

def load_data():
    res = init_connection().table("ring_prov").select("*").order("Monat").execute()
    if not res.data: return pd.DataFrame()
    df = pd.DataFrame(res.data)
    df['Monat'] = pd.to_datetime(df['Monat'])
    df['Betrag'] = pd.to_numeric(df['Betrag'])
    return df

# --- 3. ROLLIERENDE LOGIK ---
def calculate_logic(df_db):
    df = df_db.sort_values('Monat').copy()
    last_dt = df['Monat'].max()
    
    # Vorjahres-Match für Wachstumsraten
    df['vj_monat'] = df['Monat'] - pd.DateOffset(years=1)
    df = df.merge(df[['Monat', 'Betrag']].rename(columns={'Monat': 'vj_monat', 'Betrag': 'vj_val'}), on='vj_monat', how='left')
    df['faktor'] = df['Betrag'] / df['vj_val']
    
    # Zeitachse (Ist + 12 Monate Zukunft)
    all_dates = pd.date_range(start=df['Monat'].min(), end=last_dt + pd.DateOffset(months=12), freq='MS')
    df_total = pd.DataFrame({'Monat': all_dates})
    
    # Ist-Werte und Faktoren in die Gesamt-Timeline bringen
    df_total = df_total.merge(df[['Monat', 'Betrag', 'faktor']], on='Monat', how='left')
    
    # Vorjahresbasis für JEDEN Monat der Timeline (für die Prognose-Rechnung)
    df_total['vj_monat_prog'] = df_total['Monat'] - pd.DateOffset(years=1)
    df_total = df_total.merge(df[['Monat', 'Betrag']].rename(columns={'Monat': 'vj_monat_prog', 'Betrag': 'vj_basis'}), on='vj_monat_prog', how='left')
    
    # ROLLIERENDER TREND:
    # Wir nehmen für jeden Monat den Durchschnitt der Faktoren der 6 Monate DAVOR.
    # 'min_periods=1' stellt sicher, dass wir auch am Anfang der Datenreihe Werte bekommen.
    df_total['trend_rollierend'] = df_total['faktor'].shift(1).rolling(window=6, min_periods=1).mean()
    
    # In der fernen Zukunft (wenn shift(1) leer wird) füllen wir mit dem letzten bekannten Trend auf
    last_known_trend = df_total['trend_rollierend'].dropna().iloc[-1]
    df_total['trend_rollierend'] = df_total['trend_rollierend'].fillna(last_known_trend)
    
    # PROGNOSE-BERECHNUNG: Vorjahresbasis * rollierender Trend
    df_total['prognose'] = df_total['vj_basis'] * df_total['trend_rollierend']
    
    # Ampel
    df_total['farbe'] = df_total.apply(lambda r: '#2e7d32' if r['Betrag'] >= r['prognose'] else ('#ff9800' if r['Betrag'] < r['prognose'] else '#424242'), axis=1)
    
    return df_total, last_known_trend, (last_dt, df['Betrag'].iloc[-1]), df.dropna(subset=['faktor']).tail(6)

# --- 4. APP ---
try:
    df_res, current_trend, last_pt, debug_df = calculate_logic(load_data())
    
    if not df_res.empty:
        # Filter (Alles / 1J / 3J)
        c1, c2, c3 = st.columns(3)
        if 'f' not in st.session_state: st.session_state.f = "alles"
        if c1.button("Alles", use_container_width=True): st.session_state.f = "alles"
        if c2.button("1 Zeitjahr", use_container_width=True): st.session_state.f = "1j"
        if c3.button("3 Zeitjahre", use_container_width=True): st.session_state.f = "3j"

        df_p = df_res.copy()
        if st.session_state.f == "1j": df_p = df_res[df_res['Monat'] > (last_pt[0] - pd.DateOffset(years=1))]
        elif st.session_state.f == "3j": df_p = df_res[df_res['Monat'] > (last_pt[0] - pd.DateOffset(years=3))]

        # Kacheln
        forecast_next = df_res[df_res['Monat'] > last_pt[0]]['prognose'].iloc[0]
        st.markdown(f"""
            <div class="kachel-grid">
                <div class="kachel-container"><div class="kachel-titel">Letzter Monat</div><div class="kachel-wert">{format_euro(last_pt[1])}</div></div>
                <div class="kachel-container"><div class="kachel-titel">Aktueller Trend (Ø 6M)</div><div class="kachel-wert">{current_trend:.4f}</div></div>
                <div class="kachel-container"><div class="kachel-titel">Forecast (Folgem.)</div><div class="kachel-wert">{format_euro(forecast_next)}</div></div>
                <div class="kachel-container"><div class="kachel-titel">Ø 12 Monate</div><div class="kachel-wert">{format_euro(df_res.dropna(subset=['Betrag'])['Betrag'].tail(12).mean())}</div></div>
                <div class="kachel-container"><div class="kachel-titel">Summe (Anzeige)</div><div class="kachel-wert">{format_euro(df_p['Betrag'].sum())}</div></div>
                <div class="kachel-container"><div class="kachel-titel">Modus</div><div class="kachel-wert">Dynamisch</div></div>
            </div>
        """, unsafe_allow_html=True)

        # Chart
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df_p['Monat'], y=df_p['prognose'], fill='tozeroy', mode='none', name='Prognose', fillcolor='rgba(169, 169, 169, 0.2)', hovertemplate="Prognose: %{y:,.2f} €<extra></extra>"))
        fig.add_trace(go.Scatter(x=df_p['Monat'], y=df_p['Betrag'], mode='lines+markers', name='Ist', line=dict(color='#424242', width=2), marker=dict(size=10, color=df_p['farbe'], line=dict(width=1, color='white')), hovertemplate="Ist: %{y:,.2f} €<extra></extra>"))
        fig.update_layout(hovermode="x unified", margin=dict(l=5, r=5, t=10, b=10), yaxis=dict(title="€"), xaxis=dict(tickformat="%b %y"))
        st.plotly_chart(fig, use_container_width=True)

        # --- TRANSPARENZ ---
        st.subheader("Berechnung der nächsten Prognose")
        st.table(debug_df[['Monat', 'Betrag', 'vj_val', 'faktor']].rename(columns={'vj_val': 'Vorjahr', 'faktor': 'Rate'}).style.format({'Betrag': '{:,.2f} €', 'Vorjahr': '{:,.2f} €', 'Rate': '{:.4f}'}))
        
        next_date = (last_pt[0] + pd.DateOffset(months=1))
        vj_basis = df_res[df_res['Monat'] == next_date]['vj_basis'].values[0]
        st.markdown(f"""
        <div class="calc-box">
            <b>{next_date.strftime('%B %Y')}:</b> Trend {current_trend:.4f} × Vorjahr {format_euro(vj_basis)} = <b>{format_euro(forecast_next)}</b>
        </div>
        """, unsafe_allow_html=True)

except Exception as e:
    st.error(f"Fehler: {e}")
