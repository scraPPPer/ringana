import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from supabase import create_client, Client

# --- 1. SEITEN-KONFIGURATION ---
st.set_page_config(
    page_title="Provisions-Tracker",
    page_icon="📈",
    layout="centered"
)

# CSS für bessere mobile Lesbarkeit
st.markdown("""
    <style>
    [data-testid="stMetricValue"] { font-size: 1.8rem; }
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
        st.error("Verbindung fehlgeschlagen. Überprüfe deine Secrets!")
        st.stop()

supabase = init_connection()

# --- 3. DATEN LADEN ---
def load_data():
    # Tabellenname 'ring_prov' und Spalten 'Monat', 'Betrag'
    response = supabase.table("ring_prov").select("Monat, Betrag").order("Monat").execute()
    df = pd.DataFrame(response.data)
    
    if df.empty:
        return df
        
    # Umwandlung mit den korrekten Spaltennamen
    df['Monat'] = pd.to_datetime(df['Monat'])
    df['Betrag'] = pd.to_numeric(df['Betrag'])
    return df

# --- 4. DEINE EXCEL-LOGIK (TREND & FORECAST) ---
def calculate_forecast(df_historical):
    df = df_historical.sort_values('Monat').copy()
    
    # Vorjahreswerte zuordnen (Shift um 12 Zeilen, da 1 Zeile = 1 Monat)
    df['prev_year_amount'] = df['Betrag'].shift(12)
    
    # Steigerungsrate zum Vorjahr (YoY)
    # Formel: (Aktuell / Vorjahr) - 1
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
        
        # Vorjahresmonat suchen
        historical_row = df[df['Monat'] == target_prev_year]
        
        if not historical_row.empty:
            prev_year_value = historical_row['Betrag'].values[0]
            # Deine Formel: Vorjahresmonat * (1 + Trend)
            forecast_amount = prev_year_value * (1 + trend_factor)
        else:
            # Fallback: Falls keine Vorjahresdaten existieren, nimm Durchschnitt der letzten 6 Monate
            forecast_amount = df['Betrag'].tail(6).mean()
            
        forecast_list.append({
            'Monat': forecast_month,
            'Betrag': forecast_amount,
            'type': 'Forecast'
        })
    
    return pd.DataFrame(forecast_list), trend_factor

# --- 5. HAUPT-APP ---
st.title("📊 Provisions-Dashboard")

try:
    df_raw = load_data()

    if not df_raw.empty:
        df_forecast, trend = calculate_forecast(df_raw)

        # Metriken (oben im Dashboard)
        col1, col2 = st.columns(2)
        with col1:
            last_val = df_raw['Betrag'].iloc[-1]
            st.metric("Letzter Monat", f"{last_val:,.2f} €")
        with col2:
            st.metric("Trend (Ø 6M YoY)", f"{trend*100:+.1f} %")

        # --- PLOTLY CHART ---
        fig = go.Figure()

        # Ist-Daten (Blau)
        fig.add_trace(go.Scatter(
            x=df_raw['Monat'], y=df_raw['Betrag'],
            mode='lines+markers', name='Ist-Daten',
            line=dict(color='#1f77b4', width=3),
            hovertemplate='%{x|%b %Y}: %{y:,.2f}€'
        ))

        # Forecast-Daten (Orange gestrichelt)
        fig.add_trace(go.Scatter(
            x=df_forecast['Monat'], y=df_forecast['Betrag'],
            mode='lines', name='Excel-Forecast',
            line=dict(color='#ff7f0e', width=3, dash='dot'),
            hovertemplate='%{x|%b %Y}: %{y:,.2f}€'
        ))

        fig.update_layout(
            margin=dict(l=10, r=10, t=30, b=10),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
            hovermode="x unified",
            xaxis=dict(showgrid=False),
            yaxis=dict(title="Euro (€)", showgrid=True, gridcolor='LightGray'),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
        )

        st.plotly_chart(fig, use_container_width=True)

        # --- DETAILS TABELLE ---
        with st.expander("Details: Forecast Tabelle"):
            st.table(df_forecast[['Monat', 'Betrag']].assign(
                Monat=lambda x: x['Monat'].dt.strftime('%b %Y'),
                Betrag=lambda x: x['Betrag'].map('{:,.2f} €'.format)
            ).set_index('Monat'))

    else:
        st.info("Keine Daten in 'ring_prov' gefunden. Bitte Daten hochladen.")

except Exception as e:
    st.error(f"Ein Fehler ist aufgetreten: {e}")
