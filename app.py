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

# --- 3. LOGIK ---
def calculate_logic(df_db):
    df = df_db.sort_values('Monat').copy()
    last_dt = df['Monat'].max()
    
    df['vj_monat'] = df['Monat'] - pd.DateOffset(years=1)
    df = df.merge(df[['Monat', 'Betrag']].rename(columns={'Monat': 'vj_monat', 'Betrag': 'vj_val'}), on='vj_monat', how='left')
    df['faktor'] = df['Betrag'] / df['vj_val']
    
    all_dates = pd.date_range(start=df['Monat'].min(), end=last_dt + pd.DateOffset(months=12), freq='MS')
    df_total = pd.DataFrame({'Monat': all_dates})
    df_total = df_total.merge(df[['Monat', 'Betrag', 'faktor']], on='Monat', how='left')
    
    df_total['vj_monat_prog'] = df_total['Monat'] - pd.DateOffset(years=1)
    df_total = df_total.merge(df[['Monat', 'Betrag']].rename(columns={'Monat': 'vj_monat_prog', 'Betrag': 'vj_basis'}), on='vj_monat_prog', how='left')
    
    df_total['trend_rollierend'] = df_total['faktor'].shift(1).rolling(window=6, min_periods=1).mean()
    last_known_trend = df_total['trend_rollierend'].dropna().iloc[-1]
    df_total['trend_rollierend'] = df_total['trend_rollierend'].fillna(last_known_trend)
    
    df_total['prognose'] = df_total['vj_basis'] * df_total['trend_rollierend']
    df_total['farbe'] = df_total.apply(lambda r: '#2e7d32' if r['Betrag'] >= r['prognose'] else ('#ff9800' if r['Betrag'] < r['prognose'] else '#424242'), axis=1)
    
    return df_total, last_known_trend, (last_dt, df['Betrag'].iloc[-1])

# --- 4. APP ---
try:
    df_res, current_trend, last_pt = calculate_logic(load_data())
    
    if not df_res.empty:
        c1, c2, c3 = st.columns(3)
        if 'f' not in st.session_state: st.session_state.f = "alles"
        if c1.button("Alles", use_container_width=True): st.session_state.f = "alles"
        if c2.button("1 Zeitjahr", use_container_width=True): st.session_state.f = "1j"
        if c3.button("3 Zeitjahre", use_container_width=True): st.session_state.f = "3j"

        df_p = df_res.copy()
        diff_val = "--"
        
        if st.session_state.f == "1j":
            df_p = df_res[df_res['Monat'] > (last_pt[0] - pd.DateOffset(years=1))]
            start_prev, end_prev = last_pt[0] - pd.DateOffset(years=2), last_pt[0] - pd.DateOffset(years=1)
            sum_curr = df_res[(df_res['Monat'] > end_prev) & (df_res['Monat'] <= last_pt[0])]['Betrag'].sum()
            sum_prev = df_res[(df_res['Monat'] > start_prev) & (df_res['Monat'] <= end_prev)]['Betrag'].sum()
            if sum_prev > 0: diff_val = f"{((sum_curr / sum_prev) - 1) * 100:+.1f} %"
            
        elif st.session_state.f == "3j":
            df_p = df_res[df_res['Monat'] > (last_pt[0] - pd.DateOffset(years=3))]
            start_prev, end_prev = last_pt[0] - pd.DateOffset(years=6), last_pt[0] - pd.DateOffset(years=3)
            sum_curr = df_res[(df_res['Monat'] > end_prev) & (df_res['Monat'] <= last_pt[0])]['Betrag'].sum()
            sum_prev = df_res[(df_res['Monat'] > start_prev) & (df_res['Monat'] <= end_prev)]['Betrag'].sum()
            if sum_prev > 0: diff_val = f"{((sum_curr / sum_prev) - 1) * 100:+.1f} %"
        
        sum_period = df_p['Betrag'].sum()

        # Kacheln
        forecast_next = df_res[df_res['Monat'] > last_pt[0]]['prognose'].iloc[0]
        st.markdown(f"""
            <div class="kachel-grid">
                <div class="kachel-container"><div class="kachel-titel">Letzter Monat</div><div class="kachel-wert">{format_euro(last_pt[1])}</div></div>
                <div class="kachel-container"><div class="kachel-titel">Wachstumsfaktor (Ø 6M)</div><div class="kachel-wert">{current_trend:.4f}</div></div>
                <div class="kachel-container"><div class="kachel-titel">Forecast (Folgem.)</div><div class="kachel-wert">{format_euro(forecast_next)}</div></div>
                <div class="kachel-container"><div class="kachel-titel">Ø 12 Monate</div><div class="kachel-wert">{format_euro(df_res.dropna(subset=['Betrag'])['Betrag'].tail(12).mean())}</div></div>
                <div class="kachel-container"><div class="kachel-titel">Summe Zeitraum</div><div class="kachel-wert">{format_euro(sum_period)}</div></div>
                <div class="kachel-container"><div class="kachel-titel">vs. Vor-Zeitraum</div><div class="kachel-wert">{diff_val}</div></div>
            </div>
        """, unsafe_allow_html=True)

        # CHART
        fig = go.Figure()

        # 1. Prognose-Fläche
        fig.add_trace(go.Scatter(
            x=df_p['Monat'], y=df_p['prognose'], 
            fill='tozeroy', mode='none', 
            fillcolor='rgba(169, 169, 169, 0.2)', hoverinfo='skip'
        ))

        # 2. Prognose-Trendlinie (Dezent gestrichelt, etwas dunkler als Fläche)
        fig.add_trace(go.Scatter(
            x=df_p['Monat'], y=df_p['prognose'], 
            mode='lines', 
            line=dict(color='rgba(80, 80, 80, 0.3)', width=1.5, dash='dot'),
            hovertemplate="Prognose: %{y:,.2f} €<extra></extra>"
        ))

        # 3. Ist-Linie
        fig.add_trace(go.Scatter(
            x=df_p['Monat'], y=df_p['Betrag'], 
            mode='lines+markers', 
            line=dict(color='#424242', width=2), 
            marker=dict(size=10, color=df_p['farbe'], line=dict(width=1, color='white')), 
            hovertemplate="Ist: %{y:,.2f} €<extra></extra>"
        ))

        fig.update_layout(
            separators=".,", 
            hovermode="x unified", 
            margin=dict(l=5, r=5, t=10, b=10), 
            showlegend=False,  # Legende komplett entfernt
            yaxis=dict(title="€", tickformat=",."), 
            xaxis=dict(tickformat="%b %y")
        )
        st.plotly_chart(fig, use_container_width=True)

except Exception as e:
    st.error(f"Fehler: {e}")
