import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from supabase import create_client, Client
from datetime import datetime

# --- 1. SEITEN-KONFIGURATION ---
st.set_page_config(page_title="Provisions-Tracker", layout="centered")

# --- CUSTOM CSS ---
st.markdown("""
    <style>
    h1 { font-size: 1.6rem !important; margin-bottom: 0.5rem; }
    .kachel-container {
        background-color: #f0f2f6;
        border-radius: 10px;
        padding: 15px;
        text-align: center;
        margin-bottom: 10px;
        border: 1px solid #e6e9ef;
    }
    .kachel-titel { font-size: 0.85rem; color: #5f6368; margin-bottom: 5px; }
    .kachel-wert { font-size: 1.3rem; font-weight: bold; color: #2e7d32; }
    .stButton>button { 
        width: 100%; border-radius: 5px; height: 3em; 
        background-color: #2e7d32; color: white; font-weight: bold; border: none;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 2. VERBINDUNG ZU SUPABASE ---
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
    if not response.data:
        return pd.DataFrame()
    df = pd.DataFrame(response.data)
    df['Monat'] = pd.to_datetime(df['Monat'])
    df['Betrag'] = pd.to_numeric(df['Betrag'])
    return df

# --- 4. KORRIGIERTE LOGIK (ROLLIERENDER TREND & FORECAST) ---
def calculate_all_forecasts(df_historical):
    df = df_historical.sort_values('Monat').copy()
    
    # 1. Vorjahreswerte
    df['prev_year_amount'] = df['Betrag'].shift(12)
    
    # 2. Punktuelles YoY Wachstum
    df['yoy_growth'] = (df['Betrag'] / df['prev_year_amount']) - 1
    
    # 3. Rollierender Trend (Ø der jeweils letzten 6 verfügbaren Wachstumsraten)
    # .rolling(6).mean() sorgt dafür, dass für jeden Monat nur die 6 Vormonate zählen
    df['rolling_trend'] = df['yoy_growth'].shift(1).rolling(window=6, min_periods=1).mean()
    
    # 4. Historische Prognose (Soll-Fläche) basierend auf dem DAMALS gültigen Trend
    df['hist_forecast'] = df['prev_year_amount'] * (1 + df['rolling_trend'])
    
    # 5. Aktueller Trend-Faktor für die Zukunft (Heutiger Stand)
    current_trend = df['yoy_growth'].dropna().tail(6).mean() if not df['yoy_growth'].dropna().empty else 0
    
    # 6. Zukunft 12 Monate
    last_row = df.iloc[-1]
    last_date, last_amount = last_row['Monat'], last_row['Betrag']
    future_list = [{'Monat': last_date, 'Betrag': last_amount}]
    
    for i in range(1, 13):
        f_month = last_date + pd.DateOffset(months=i)
        target_prev_year = f_month - pd.DateOffset(years=1)
        hist_row = df[df['Monat'] == target_prev_year]
        
        if not hist_row.empty:
            f_amount = hist_row['Betrag'].values[0] * (1 + current_trend)
        else:
            f_amount = df['Betrag'].tail(6).mean()
        future_list.append({'Monat': f_month, 'Betrag': f_amount})
    
    return df, pd.DataFrame(future_list), current_trend

# --- 5. HAUPT-APP ---
st.title("Provisions-Dashboard")

with st.expander("➕ Neue Daten erfassen"):
    with st.form("input_form", clear_on_submit=True):
        input_date = st.date_input("Monat", value=datetime.now().replace(day=1))
        input_amount = st.number_input("Betrag in €", min_value=0.0, format="%.2f")
        if st.form_submit_button("Speichern"):
            supabase.table("ring_prov").upsert({"Monat": input_date.strftime("%Y-%m-%d"), "Betrag": input_amount}).execute()
            st.cache_data.clear()
            st.rerun()

try:
    df_raw, df_future, trend = calculate_all_forecasts(load_data())
    if not df_raw.empty:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f'<div class="kachel-container"><div class="kachel-titel">Letzter Monat</div><div class="kachel-wert">{df_raw["Betrag"].iloc[-1]:,.2f} €</div></div>', unsafe_allow_html=True)
            st.markdown(f'<div class="kachel-container"><div class="kachel-titel">Trend (Ø 6M YoY)</div><div class="kachel-wert">{trend*100:+.1f} %</div></div>', unsafe_allow_html=True)
        with c2:
            st.markdown(f'<div class="kachel-container"><div class="kachel-titel">Forecast (Nächster M)</div><div class="kachel-wert">{df_future["Betrag"].iloc[1]:,.2f} €</div></div>', unsafe_allow_html=True)
            st.markdown(f'<div class="kachel-container"><div class="kachel-titel">Ø Letzte 12 Monate</div><div class="kachel-wert">{df_raw["Betrag"].tail(12).mean():,.2f} €</div></div>', unsafe_allow_html=True)

        fig = go.Figure()

        # 1. Historische Prognose (Soll-Fläche) - jetzt zeitlich korrekt rollierend!
        # Wir filtern NaNs raus, damit die Fläche sauber beginnt
        df_plot_hist = df_raw.dropna(subset=['hist_forecast'])
        fig.add_trace(go.Scatter(
            x=df_plot_hist['Monat'], y=df_plot_hist['hist_forecast'],
            fill='tozeroy', mode='none', name='Prognose-Basis',
            fillcolor='rgba(169, 169, 169, 0.2)'
        ))

        # 2. Ist-Daten (Grün)
        fig.add_trace(go.Scatter(
            x=df_raw['Monat'], y=df_raw['Betrag'],
            mode='lines+markers', name='Ist',
            line=dict(color='#2e7d32', width=3), marker=dict(size=8)
        ))

        # 3. Zukünftiger Forecast (Graue Linie)
        fig.add_trace(go.Scatter(
            x=df_future['Monat'], y=df_future['Betrag'],
            mode='lines+markers', name='Forecast',
            line=dict(color='#A9A9A9', width=3), marker=dict(size=8)
        ))

        fig.update_layout(
            margin=dict(l=10, r=10, t=10, b=10),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
            hovermode="x unified", yaxis=dict(title="€")
        )
        st.plotly_chart(fig, use_container_width=True)

except Exception as e:
    st.error(f"Fehler: {e}")
