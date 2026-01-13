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

# CSS
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
    </style>
    """, unsafe_allow_html=True)

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
    df = df_db.sort_values('Monat').copy()
    last_dt = df['Monat'].max()
    
    # Faktor-Berechnung (VJ-Match)
    df['monat_vj'] = df['Monat'] - pd.DateOffset(years=1)
    df = df.merge(df[['Monat', 'Betrag']].rename(columns={'Monat': 'monat_vj', 'Betrag': 'betrag_vj'}), on='monat_vj', how='left')
    df['faktor'] = df['Betrag'] / df['betrag_vj']
    
    # Trend aus den letzten 6 verfügbaren Faktoren
    faktor_series = df.dropna(subset=['faktor'])['faktor']
    avg_f = faktor_series.tail(6).mean() if not faktor_series.empty else 1.0
    
    # Zeitachse (Feld-Ansatz)
    all_dates = pd.date_range(start=df['Monat'].min(), end=last_dt + pd.DateOffset(months=12), freq='MS')
    df_total = pd.DataFrame({'Monat': all_dates})
    df_total = df_total.merge(df[['Monat', 'Betrag']], on='Monat', how='left')
    
    # Prognose: VJ * avg_f
    df_total['monat_vj'] = df_total['Monat'] - pd.DateOffset(years=1)
    df_total = df_total.merge(df[['Monat', 'Betrag']].rename(columns={'Monat': 'monat_vj', 'Betrag': 'betrag_vj_prog'}), on='monat_vj', how='left')
    df_total['prognose'] = df_total['betrag_vj_prog'] * avg_f
    
    # Ampel-Logik & Trennung Hover
    def get_styles(row):
        ist_val = row['Betrag']
        prog_val = row['prognose']
        if pd.isna(ist_val):
            return '#424242', "Prognose: " + format_euro(prog_val)
        color = '#2e7d32' if ist_val >= prog_val else '#ff9800'
        return color, f"Ist: {format_euro(ist_val)}<br>Prognose: {format_euro(prog_val)}"

    styles = df_total.apply(get_styles, axis=1)
    df_total['farbe'] = [s[0] for s in styles]
    
    return df_total, avg_f, (last_dt, df['Betrag'].iloc[-1])

# --- UI ---
st.title("Provisions-Dashboard")

try:
    df_total, avg_f, last_pt = calculate_logic(load_data())
    
    if not df_total.empty:
        # Kacheln
        st.markdown(f"""
            <div class="kachel-grid">
                <div class="kachel-container"><div class="kachel-titel">Letzter Monat</div><div class="kachel-wert">{format_euro(last_pt[1])}</div></div>
                <div class="kachel-container"><div class="kachel-titel">Wachstumsfaktor (Ø 6M)</div><div class="kachel-wert">{avg_f:.3f}</div></div>
                <div class="kachel-container"><div class="kachel-titel">Forecast ({ (last_pt[0] + pd.DateOffset(months=1)).strftime('%m/%y') })</div><div class="kachel-wert">{format_euro(df_total[df_total['Monat'] > last_pt[0]]['prognose'].iloc[0])}</div></div>
                <div class="kachel-container"><div class="kachel-titel">Ø 12 Monate</div><div class="kachel-wert">{format_euro(df_total.dropna(subset=['Betrag'])['Betrag'].tail(12).mean())}</div></div>
                <div class="kachel-container"><div class="kachel-titel">Summe (Gesamt)</div><div class="kachel-wert">{format_euro(df_total['Betrag'].sum())}</div></div>
                <div class="kachel-container"><div class="kachel-titel">Status</div><div class="kachel-wert">Präzise</div></div>
            </div>
        """, unsafe_allow_html=True)

        # CHART
        fig = go.Figure()
        # Nur Prognose-Fläche
        fig.add_trace(go.Scatter(x=df_total['Monat'], y=df_total['prognose'], fill='tozeroy', mode='none', name='Prognose', fillcolor='rgba(169, 169, 169, 0.2)', hoverinfo='skip'))
        # Ist-Linie mit Ampel
        fig.add_trace(go.Scatter(x=df_total['Monat'], y=df_total['Betrag'], mode='lines+markers', name='Ist', line=dict(color='#424242', width=2), marker=dict(size=10, color=df_total['farbe'], line=dict(width=1, color='white')), hovertemplate="%{x|%b %y}<br>Ist: %{y:,.2f} €<extra></extra>", connectgaps=False))
        # Unsichtbarer Forecast-Hover
        df_f = df_total[df_total['Monat'] > last_pt[0]]
        fig.add_trace(go.Scatter(x=df_f['Monat'], y=df_f['prognose'], mode='markers', name='Forecast', marker=dict(color='#A9A9A9', size=8), hovertemplate="%{x|%b %y}<br>Forecast: %{y:,.2f} €<extra></extra>"))

        fig.update_layout(separators=".,", margin=dict(l=5, r=5, t=10, b=10), legend=dict(orientation="h", y=1.1, x=0.5, xanchor="center"), hovermode="closest", yaxis=dict(title="€"), xaxis=dict(tickformat="%b %y"))
        st.plotly_chart(fig, use_container_width=True)

except Exception as e:
    st.error(f"Fehler: {e}")
