import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from supabase import create_client
from datetime import date
from dateutil.relativedelta import relativedelta

# --- 1. KONFIGURATION ---
st.set_page_config(page_title="Provisions-Tracker", layout="centered")

def format_euro(val):
    if pd.isna(val) or val == 0: return "0,00 €"
    return "{:,.2f} €".format(val).replace(",", "X").replace(".", ",").replace("X", ".")

# CSS für das saubere 2x3 Grid
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

# --- 2. DATENBANK ---
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

# --- 3. MATHEMATISCHE KERN-LOGIK ---
def calculate_everything(df_db):
    df = df_db.sort_values('Monat').copy()
    last_ist_date = df['Monat'].max()
    
    # Faktor-Ermittlung (Ist / Vorjahr)
    df['monat_vj'] = df['Monat'] - pd.DateOffset(years=1)
    df = df.merge(
        df[['Monat', 'Betrag']].rename(columns={'Monat': 'monat_vj', 'Betrag': 'betrag_vj'}),
        on='monat_vj', how='left'
    )
    df['faktor'] = df['Betrag'] / df['betrag_vj']
    
    # Fixer Trendfaktor (Mittelwert der letzten 6 verfügbaren Faktoren)
    faktoren_liste = df.dropna(subset=['faktor'])['faktor']
    final_trend = faktoren_liste.tail(6).mean() if not faktoren_liste.empty else 1.0
    
    # Erstellung des Gesamt-Datensatzes (Feld-Ansatz)
    future_end = last_ist_date + pd.DateOffset(months=12)
    all_dates = pd.date_range(start=df['Monat'].min(), end=future_end, freq='MS')
    df_final = pd.DataFrame({'Monat': all_dates})
    
    # Ist-Werte mergen
    df_final = df_final.merge(df[['Monat', 'Betrag']], on='Monat', how='left')
    
    # Prognose berechnen: Für JEDEN Monat schauen, ob es ein Vorjahr gibt
    df_final['monat_vj'] = df_final['Monat'] - pd.DateOffset(years=1)
    df_final = df_final.merge(
        df[['Monat', 'Betrag']].rename(columns={'Monat': 'monat_vj', 'Betrag': 'betrag_vj_prog'}),
        on='monat_vj', how='left'
    )
    df_final['prognose'] = df_final['betrag_vj_prog'] * final_trend
    
    # Ampel-Farben & Hover-Texte
    def apply_styles(row):
        ist = row['Betrag']
        prog = row['prognose']
        if pd.isna(ist): # Zukunft
            return '#424242', f"Prognose: {format_euro(prog)}"
        color = '#2e7d32' if ist >= prog else '#ff9800'
        return color, f"Ist: {format_euro(ist)}<br>Prognose: {format_euro(prog)}"

    styles = df_final.apply(apply_styles, axis=1)
    df_final['farbe'] = [s[0] for s in styles]
    df_final['hover_text'] = [s[1] for s in styles]
    
    return df_final, final_trend, last_ist_date

# --- 4. UI ---
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
    df_all, trend_val, last_date = calculate_everything(load_data())
    
    if not df_all.empty:
        # Filter Buttons
        c1, c2, c3 = st.columns(3)
        if 'f' not in st.session_state: st.session_state.f = "alles"
        if c1.button("Alles", use_container_width=True): st.session_state.f = "alles"
        if c2.button("1 Zeitjahr", use_container_width=True): st.session_state.f = "1j"
        if c3.button("3 Zeitjahre", use_container_width=True): st.session_state.f = "3j"

        # Daten filtern
        if st.session_state.f == "1j":
            df_plot = df_all[df_all['Monat'] > (last_date - pd.DateOffset(years=1))]
            df_prev = df_all[(df_all['Monat'] <= (last_date - pd.DateOffset(years=1))) & (df_all['Monat'] > (last_date - pd.DateOffset(years=2)))]
        elif st.session_state.f == "3j":
            df_plot = df_all[df_all['Monat'] > (last_date - pd.DateOffset(years=3))]
            df_prev = df_all[(df_all['Monat'] <= (last_date - pd.DateOffset(years=3))) & (df_all['Monat'] > (last_date - pd.DateOffset(years=6)))]
        else:
            df_plot = df_all
            df_prev = pd.DataFrame()

        # Kachel-Werte
        sum_p = df_plot['Betrag'].sum()
        diff = f"{((sum_p / df_prev['Betrag'].sum()) - 1) * 100:+.1f} %" if not df_prev.empty and df_prev['Betrag'].sum() > 0 else "--"

        # Kacheln
        st.markdown(f"""
            <div class="kachel-grid">
                <div class="kachel-container"><div class="kachel-titel">Letzter Monat</div><div class="kachel-wert">{format_euro(df_all[df_all['Monat']==last_date]['Betrag'].values[0])}</div></div>
                <div class="kachel-container"><div class="kachel-titel">Wachstumsfaktor (Ø 6M)</div><div class="kachel-wert">{trend_val:.3f}</div></div>
                <div class="kachel-container"><div class="kachel-titel">Forecast (Folgem.)</div><div class="kachel-wert">{format_euro(df_all[df_all['Monat'] > last_date]['prognose'].iloc[0])}</div></div>
                <div class="kachel-container"><div class="kachel-titel">Ø 12 Monate</div><div class="kachel-wert">{format_euro(df_all.dropna(subset=['Betrag'])['Betrag'].tail(12).mean())}</div></div>
                <div class="kachel-container"><div class="kachel-titel">Summe Zeitraum</div><div class="kachel-wert">{format_euro(sum_p)}</div></div>
                <div class="kachel-container"><div class="kachel-titel">vs. Vor-Zeitraum</div><div class="kachel-wert">{diff}</div></div>
            </div>
        """, unsafe_allow_html=True)

        # --- CHART ---
        fig = go.Figure()
        
        # 1. Prognose-Fläche
        fig.add_trace(go.Scatter(
            x=df_plot['Monat'], y=df_plot['prognose'],
            fill='tozeroy', mode='none', name='Prognose',
            fillcolor='rgba(169, 169, 169, 0.2)', hoverinfo='skip'
        ))

        # 2. Ist-Linie + Forecast-Punkte (Einheitlicher Hover durch customdata)
        fig.add_trace(go.Scatter(
            x=df_plot['Monat'], y=df_plot['Betrag'].fillna(df_plot['prognose']),
            mode='lines+markers', name='Verlauf',
            line=dict(color='#424242', width=2),
            marker=dict(size=10, color=df_plot['farbe'], line=dict(width=1, color='white')),
            customdata=df_plot['hover_text'],
            hovertemplate="<b>%{x|%B %Y}</b><br>%{customdata}<extra></extra>"
        ))

        fig.update_layout(
            separators=".,", margin=dict(l=10, r=10, t=10, b=10),
            legend=dict(orientation="h", y=1.1, x=0.5, xanchor="center"),
            hovermode="closest",
            yaxis=dict(title="€", tickformat=",."),
            xaxis=dict(tickformat="%b %y")
        )
        st.plotly_chart(fig, use_container_width=True)

except Exception as e:
    st.error(f"Fehler in der Verarbeitung: {e}")
