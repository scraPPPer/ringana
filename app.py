import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from supabase import create_client, Client
from datetime import datetime

# --- 1. SEITEN-KONFIGURATION ---
st.set_page_config(page_title="Provisions-Tracker", page_icon="📈", layout="centered")

# --- CUSTOM CSS FÜR KACHELN & MOBILE OPTIMIERUNG ---
st.markdown("""
    <style>
    .kachel-container {
        background-color: #f0f2f6;
        border-radius: 10px;
        padding: 15px;
        text-align: center;
        margin-bottom: 10px;
        border: 1px solid #e6e9ef;
    }
    .kachel-titel {
        font-size: 0.9rem;
        color: #5f6368;
        margin-bottom: 5px;
    }
    .kachel-wert {
        font-size: 1.4rem;
        font-weight: bold;
        color: #1f77b4;
    }
    .stButton>button { 
        width: 100%; 
        border-radius: 5px; 
        height: 3em; 
        background-color: #1f77b4; 
        color: white; 
        font-weight: bold;
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
        st.error("Verbindung zu Supabase fehlgeschlagen.")
        st.stop()

supabase = init_connection()

# --- 3. DATEN LADEN ---
def load_data():
    # Korrektur: .order("Monat") ohne das ungültige 'descending' Argument
    response = supabase.table("ring_prov").select("*").order("Monat").execute()
    
    if not response.data:
        return pd.DataFrame()
    
    df = pd.DataFrame(response.data)
    df['Monat'] = pd.to_datetime(df['Monat'])
    df['Betrag'] = pd.to_numeric(df['Betrag'])
    return df

# --- 4. EXCEL-LOGIK FÜR TREND & FORECAST ---
def calculate_forecast(df_historical):
    df = df_historical.sort_values('Monat').copy()
    
    # Vorjahreswerte zuordnen
    df['prev_year_amount'] = df['Betrag'].shift(12)
    
    # Steigerungsrate zum Vorjahr (YoY)
    df['yoy_growth'] = (df['Betrag'] / df['prev_year_amount']) - 1
    
    # Trend-Faktor: Durchschnitt der letzten 6 verfügbaren Monate
    growth_rates = df['yoy_growth'].dropna()
    if len(growth_rates) >= 6:
        trend_factor = growth_rates.tail(6).mean()
    else:
        trend_factor = growth_rates.mean() if not growth_rates.empty else 0
    
    # 12-Monats-Forecast generieren
    last_date = df['Monat'].max()
    forecast_list = []
    
    for i in range(1, 13):
        forecast_month = last_date + pd.DateOffset(months=i)
        target_prev_year = forecast_month - pd.DateOffset(years=1)
        
        hist_row = df[df['Monat'] == target_prev_year]
        if not hist_row.empty:
            forecast_amount = hist_row['Betrag'].values[0] * (1 + trend_factor)
        else:
            forecast_amount = df['Betrag'].tail(6).mean()
            
        forecast_list.append({
            'Monat': forecast_month,
            'Betrag': forecast_amount
        })
    
    return pd.DataFrame(forecast_list), trend_factor

# --- 5. HAUPT-APP ---
st.title("📊 Provisions-Tracker")

# --- ERFASSUNGS-BEREICH ---
with st.expander("➕ Neue Daten erfassen"):
    with st.form("input_form", clear_on_submit=True):
        default_date = datetime.now().replace(day=1)
        input_date = st.date_input("Monat auswählen", value=default_date)
        input_amount = st.number_input("Betrag in €", min_value=0.0, step=100.0, format="%.2f")
        
        if st.form_submit_button("In Datenbank speichern"):
            try:
                supabase.table("ring_prov").upsert({
                    "Monat": input_date.strftime("%Y-%m-%d"), 
                    "Betrag": input_amount
                }).execute()
                st.success(f"Speichern erfolgreich!")
                st.cache_data.clear()
                st.rerun()
            except Exception as e:
                st.error(f"Fehler beim Speichern: {e}")

# --- ANZEIGE-BEREICH ---
try:
    df_raw = load_data()

    if not df_raw.empty:
        df_forecast, trend = calculate_forecast(df_raw)

        # --- KACHELN NEBENEINANDER (2 pro Zeile) ---
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown(f"""<div class="kachel-container">
                <div class="kachel-titel">Letzter Monat</div>
                <div class="kachel-wert">{df_raw['Betrag'].iloc[-1]:,.2f} €</div>
            </div>""", unsafe_allow_html=True)
            
            st.markdown(f"""<div class="kachel-container">
                <div class="kachel-titel">Trend (Ø 6M YoY)</div>
                <div class="kachel-wert">{trend*100:+.1f} %</div>
            </div>""", unsafe_allow_html=True)

        with col2:
            st.markdown(f"""<div class="kachel-container">
                <div class="kachel-titel">Forecast (Nächster M)</div>
                <div class="kachel-wert">{df_forecast['Betrag'].iloc[0]:,.2f} €</div>
            </div>""", unsafe_allow_html=True)
            
            st.markdown(f"""<div class="kachel-container">
                <div class="kachel-titel">Ø Letzte 12 Monate</div>
                <div class="kachel-wert">{df_raw['Betrag'].tail(12).mean():,.2f} €</div>
            </div>""", unsafe_allow_html=True)

        # --- PLOTLY CHART ---
        fig = go.Figure()

        # Ist-Daten
        fig.add_trace(go.Scatter(
            x=df_raw['Monat'], y=df_raw['Betrag'],
            mode='lines+markers', name='Ist',
            line=dict(color='#1f77b4', width=3)
        ))

        # Forecast-Daten
        fig.add_trace(go.Scatter(
            x=df_forecast['Monat'], y=df_forecast['Betrag'],
            mode='lines', name='Forecast',
            line=dict(color='#ff7f0e', width=3, dash='dot')
        ))

        fig.update_layout(
            margin=dict(l=10, r=10, t=10, b=10),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
            hovermode="x unified",
            yaxis=dict(title="€")
        )
        st.plotly_chart(fig, use_container_width=True)

        # --- DETAILS ---
        with st.expander("Details: Forecast Tabelle"):
            st.table(df_forecast[['Monat', 'Betrag']].assign(
                Monat=lambda x: x['Monat'].dt.strftime('%b %Y'),
                Betrag=lambda x: x['Betrag'].map('{:,.2f} €'.format)
            ).set_index('Monat'))

    else:
        st.info("Noch keine Daten in 'ring_prov' vorhanden.")

except Exception as e:
    st.error(f"Ein Fehler ist aufgetreten: {e}")
