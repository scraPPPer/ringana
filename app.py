import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from supabase import create_client
from datetime import date
from dateutil.relativedelta import relativedelta

# --- 1. SETUP & DESIGN ---
st.set_page_config(page_title="Provisions-Tracker", layout="centered")

st.markdown("""
    <style>
    .kachel-grid { display: flex; flex-wrap: wrap; gap: 10px; justify-content: space-between; }
    .kachel-container {
        background-color: #f0f2f6; border-radius: 10px; padding: 12px 5px;
        text-align: center; border: 1px solid #e6e9ef; flex: 0 0 48%; margin-bottom: 5px;
    }
    .kachel-titel { font-size: 0.75rem; color: #5f6368; }
    .kachel-wert { font-size: 1.1rem; font-weight: bold; color: #2e7d32; }
    </style>
    """, unsafe_allow_html=True)

def format_euro(val):
    return "{:,.2f} €".format(val).replace(",", "X").replace(".", ",").replace("X", ".") if pd.notna(val) else "0,00 €"

# --- 2. DATEN LADEN & BERECHNEN ---
@st.cache_resource
def init_connection():
    return create_client(st.secrets["supabase_url"], st.secrets["supabase_key"])

def get_data():
    data = init_connection().table("ring_prov").select("*").order("Monat").execute().data
    df = pd.DataFrame(data)
    df['Monat'] = pd.to_datetime(df['Monat'])
    df['Betrag'] = pd.to_numeric(df['Betrag'])
    return df

try:
    df_raw = get_data()
    last_date = df_raw['Monat'].max()

    # Trend-Logik (Mittelwert der letzten 6 Faktoren: Ist / Vorjahr)
    df_calc = df_raw.copy()
    df_calc['vj_monat'] = df_calc['Monat'] - pd.DateOffset(years=1)
    df_calc = df_calc.merge(df_raw[['Monat', 'Betrag']].rename(columns={'Monat': 'vj_monat', 'Betrag': 'vj_val'}), on='vj_monat', how='left')
    df_calc['faktor'] = df_calc['Betrag'] / df_calc['vj_val']
    trend = df_calc['faktor'].dropna().tail(6).mean()

    # Gesamt-Timeline (Ist + 12 Monate Zukunft)
    all_dates = pd.date_range(start=df_raw['Monat'].min(), end=last_date + pd.DateOffset(months=12), freq='MS')
    df_all = pd.DataFrame({'Monat': all_dates})
    df_all = df_all.merge(df_raw[['Monat', 'Betrag']], on='Monat', how='left')
    df_all['vj_monat'] = df_all['Monat'] - pd.DateOffset(years=1)
    df_all = df_all.merge(df_raw[['Monat', 'Betrag']].rename(columns={'Monat': 'vj_monat', 'Betrag': 'vj_val'}), on='vj_monat', how='left')
    df_all['prognose'] = df_all['vj_val'] * trend

    # --- 3. FILTER-STEUERUNG ---
    if 'filter' not in st.session_state: st.session_state.filter = "alles"
    col1, col2, col3 = st.columns(3)
    if col1.button("Alles", use_container_width=True): st.session_state.filter = "alles"
    if col2.button("1 Jahr", use_container_width=True): st.session_state.filter = "1j"
    if col3.button("3 Jahre", use_container_width=True): st.session_state.filter = "3j"

    # Zeiträume definieren
    df_plot = df_all.copy()
    sum_curr, sum_prev = 0, 0
    diff_text = "--"

    if st.session_state.filter == "1j":
        df_plot = df_all[df_all['Monat'] > (last_date - pd.DateOffset(years=1))]
        sum_curr = df_all[(df_all['Monat'] > (last_date - pd.DateOffset(years=1))) & (df_all['Monat'] <= last_date)]['Betrag'].sum()
        sum_prev = df_all[(df_all['Monat'] > (last_date - pd.DateOffset(years=2))) & (df_all['Monat'] <= (last_date - pd.DateOffset(years=1)))]['Betrag'].sum()
    elif st.session_state.filter == "3j":
        df_plot = df_all[df_all['Monat'] > (last_date - pd.DateOffset(years=3))]
        sum_curr = df_all[(df_all['Monat'] > (last_date - pd.DateOffset(years=3))) & (df_all['Monat'] <= last_date)]['Betrag'].sum()
        sum_prev = df_all[(df_all['Monat'] > (last_date - pd.DateOffset(years=6))) & (df_all['Monat'] <= (last_date - pd.DateOffset(years=3)))]['Betrag'].sum()
    else:
        sum_curr = df_all['Betrag'].sum()

    if sum_prev > 0:
        diff_text = f"{((sum_curr / sum_prev) - 1) * 100:+.1f} %"

    # --- 4. ANZEIGE ---
    st.markdown(f"""
        <div class="kachel-grid">
            <div class="kachel-container"><div class="kachel-titel">Letzter Monat</div><div class="kachel-wert">{format_euro(df_raw['Betrag'].iloc[-1])}</div></div>
            <div class="kachel-container"><div class="kachel-titel">Trend-Faktor</div><div class="kachel-wert">{trend:.3f}</div></div>
            <div class="kachel-container"><div class="kachel-titel">Forecast (Folgem.)</div><div class="kachel-wert">{format_euro(df_all[df_all['Monat']>last_date]['prognose'].iloc[0])}</div></div>
            <div class="kachel-container"><div class="kachel-titel">Ø 12 Monate</div><div class="kachel-wert">{format_euro(df_raw['Betrag'].tail(12).mean())}</div></div>
            <div class="kachel-container"><div class="kachel-titel">Summe (Zeitraum)</div><div class="kachel-wert">{format_euro(sum_curr)}</div></div>
            <div class="kachel-container"><div class="kachel-titel">vs. Vor-Zeitraum</div><div class="kachel-wert">{diff_text}</div></div>
        </div>
    """, unsafe_allow_html=True)

    # Chart
    fig = go.Figure()
    # Prognose-Fläche
    fig.add_trace(go.Scatter(x=df_plot['Monat'], y=df_plot['prognose'], fill='tozeroy', mode='none', name='Prognose', fillcolor='rgba(169, 169, 169, 0.2)'))
    # Ist-Linie + Ampel
    colors = ['#2e7d32' if i >= p else '#ff9800' for i, p in zip(df_plot['Betrag'], df_plot['prognose'])]
    fig.add_trace(go.Scatter(x=df_plot['Monat'], y=df_plot['Betrag'], mode='lines+markers', name='Ist', line=dict(color='#424242', width=2), marker=dict(size=9, color=colors, line=dict(width=1, color='white'))))
    
    fig.update_layout(hovermode="x unified", margin=dict(l=10, r=10, t=10, b=10), yaxis=dict(title="€"), xaxis=dict(tickformat="%b %y"))
    st.plotly_chart(fig, use_container_width=True)

except Exception as e:
    st.error(f"Fehler: {e}")
