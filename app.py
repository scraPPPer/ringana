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
    .calc-box { background-color: #fff; border: 1px solid #ddd; padding: 15px; border-radius: 10px; margin-top: 20px; }
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

# --- 3. LOGIK ---
def calculate_logic(df_db):
    df = df_db.sort_values('Monat').copy()
    last_dt = df['Monat'].max()
    
    # 1. Vorjahres-Match
    df['vj_monat'] = df['Monat'] - pd.DateOffset(years=1)
    df = df.merge(df[['Monat', 'Betrag']].rename(columns={'Monat': 'vj_monat', 'Betrag': 'vj_val'}), on='vj_monat', how='left')
    
    # 2. Faktor berechnen
    df['yoy_factor'] = df['Betrag'] / df['vj_val']
    
    # 3. Trend aus den letzten 6 verfügbaren Faktoren
    debug_df = df.dropna(subset=['yoy_factor']).tail(6).copy()
    avg_trend = debug_df['yoy_factor'].mean() if not debug_df.empty else 1.0
    
    # 4. Prognose-Zeitachse
    all_dates = pd.date_range(start=df['Monat'].min(), end=last_dt + pd.DateOffset(months=12), freq='MS')
    df_total = pd.DataFrame({'Monat': all_dates})
    df_total = df_total.merge(df[['Monat', 'Betrag']], on='Monat', how='left')
    df_total['vj_monat'] = df_total['Monat'] - pd.DateOffset(years=1)
    df_total = df_total.merge(df[['Monat', 'Betrag']].rename(columns={'Monat': 'vj_monat', 'Betrag': 'vj_prog_basis'}), on='vj_monat', how='left')
    
    # Prognose berechnen (nur dort, wo kein Ist-Wert ist)
    df_total['prognose'] = df_total['vj_prog_basis'] * avg_trend
    
    # 5. Farben
    def get_color(row):
        if pd.isna(row['Betrag']) or pd.isna(row['prognose']): return '#424242'
        return '#2e7d32' if row['Betrag'] >= row['prognose'] else '#ff9800'
    df_total['farbe'] = df_total.apply(get_color, axis=1)
    
    return df_total, avg_trend, (last_dt, df['Betrag'].iloc[-1]), debug_df

# --- 4. APP ---
st.title("Provisions-Dashboard")

try:
    df_total, trend_val, last_pt, debug_df = calculate_logic(load_data())
    
    if not df_total.empty:
        # Filter Buttons
        c_f1, c_f2, c_f3 = st.columns(3)
        if 'filter' not in st.session_state: st.session_state.filter = "alles"
        if c_f1.button("Alles", use_container_width=True): st.session_state.filter = "alles"
        if c_f2.button("1 Zeitjahr", use_container_width=True): st.session_state.filter = "1j"
        if c_f3.button("3 Zeitjahre", use_container_width=True): st.session_state.filter = "3j"

        # Zeitraum-Filterung
        if st.session_state.filter == "1j":
            df_plot = df_total[df_total['Monat'] > (last_pt[0] - pd.DateOffset(years=1))]
            start_prev, end_prev = last_pt[0] - pd.DateOffset(years=2), last_pt[0] - pd.DateOffset(years=1)
        elif st.session_state.filter == "3j":
            df_plot = df_total[df_total['Monat'] > (last_pt[0] - pd.DateOffset(years=3))]
            start_prev, end_prev = last_pt[0] - pd.DateOffset(years=6), last_pt[0] - pd.DateOffset(years=3)
        else:
            df_plot = df_total
            start_prev, end_prev = None, None

        sum_period = df_plot['Betrag'].sum()
        diff_val = "--"
        if start_prev:
            sum_prev = df_total[(df_total['Monat'] > start_prev) & (df_total['Monat'] <= end_prev)]['Betrag'].sum()
            if sum_prev > 0:
                diff_val = f"{((sum_period / sum_prev) - 1) * 100:+.1f} %"

        # Kacheln
        forecast_next = df_total[df_total['Monat'] > last_pt[0]]['prognose'].iloc[0]
        st.markdown(f"""
            <div class="kachel-grid">
                <div class="kachel-container"><div class="kachel-titel">Letzter Monat</div><div class="kachel-wert">{format_euro(last_pt[1])}</div></div>
                <div class="kachel-container"><div class="kachel-titel">Wachstumsfaktor (Ø 6M)</div><div class="kachel-wert">{trend_val:.4f}</div></div>
                <div class="kachel-container"><div class="kachel-titel">Forecast (Folgem.)</div><div class="kachel-wert">{format_euro(forecast_next)}</div></div>
                <div class="kachel-container"><div class="kachel-titel">Ø 12 Monate</div><div class="kachel-wert">{format_euro(df_total.dropna(subset=['Betrag'])['Betrag'].tail(12).mean())}</div></div>
                <div class="kachel-container"><div class="kachel-titel">Summe Zeitraum</div><div class="kachel-wert">{format_euro(sum_period)}</div></div>
                <div class="kachel-container"><div class="kachel-titel">vs. Vor-Zeitraum</div><div class="kachel-wert">{diff_val}</div></div>
            </div>
        """, unsafe_allow_html=True)

        # CHART
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df_plot['Monat'], y=df_plot['prognose'], fill='tozeroy', mode='none', name='Prognose', fillcolor='rgba(169, 169, 169, 0.2)', hovertemplate="Prognose: %{y:,.2f} €<extra></extra>"))
        fig.add_trace(go.Scatter(x=df_plot['Monat'], y=df_plot['Betrag'], mode='lines+markers', name='Ist', line=dict(color='#424242', width=2), marker=dict(size=10, color=df_plot['farbe'], line=dict(width=1, color='white')), hovertemplate="Ist: %{y:,.2f} €<extra></extra>", connectgaps=False))
        fig.update_layout(separators=".,", margin=dict(l=5, r=5, t=10, b=10), legend=dict(orientation="h", y=1.1, x=0.5, xanchor="center"), hovermode="x unified", yaxis=dict(title="€"), xaxis=dict(tickformat="%b %y"))
        st.plotly_chart(fig, use_container_width=True)

        # --- DETAILLIERTE BERECHNUNG UNTER DER GRAFIK ---
        st.subheader("Details zur nächsten Prognose")
        
        # 1. Die 6 herangezogenen Monate
        st.write("Die letzten 6 Wachstumsraten (Ist / Vorjahr):")
        st.table(debug_df[['Monat', 'Betrag', 'vj_val', 'yoy_factor']].rename(columns={
            'Betrag': 'Ist-Wert',
            'vj_val': 'Vorjahresmonat',
            'yoy_factor': 'Wachstumsrate'
        }).style.format({'Ist-Wert': '{:,.2f} €', 'Vorjahresmonat': '{:,.2f} €', 'Wachstumsrate': '{:.4f}'}))

        # 2. Die finale Rechnung
        next_month = (last_pt[0] + pd.DateOffset(months=1))
        vj_basis = df_total[df_total['Monat'] == next_month]['vj_prog_basis'].values[0]
        
        st.markdown(f"""
        <div class="calc-box">
            <strong>Rechnung für {next_month.strftime('%B %Y')}:</strong><br>
            Durchschnittliche Wachstumsrate (Ø von oben): <b>{trend_val:.4f}</b><br>
            Multipliziert mit Vorjahresmonat ({ (next_month - pd.DateOffset(years=1)).strftime('%B %Y') }): <b>{format_euro(vj_basis)}</b><br><br>
            <span style="font-size: 1.2rem; color: #2e7d32;">
                = Prognose: <b>{format_euro(forecast_next)}</b>
            </span>
        </div>
        """, unsafe_allow_html=True)

except Exception as e:
    st.error(f"Fehler: {e}")
