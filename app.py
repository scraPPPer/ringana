import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from supabase import create_client, Client

# --- 1. SEITEN-KONFIGURATION ---
st.set_page_config(
    page_title="Provisions-Dashboard",
    page_icon="📈",
    layout="centered"
)

# CSS für bessere mobile Lesbarkeit der Metriken
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
        st.error("Verbindung zu Supabase fehlgeschlagen. Überprüfe deine Secrets!")
        st.stop()

supabase = init_connection()

# --- 3. DATEN LADEN ---
def load_data():
    response = supabase.table("commissions").select("month, amount").order("month").execute()
    df = pd.DataFrame(response.data)
    
    if df.empty:
        return df
        
    df['month'] = pd.to_datetime(df['month'])
    df['amount'] = pd.to_numeric(df['amount'])
    return df

# --- 4. DEINE EXCEL-LOGIK (TREND & FORECAST) ---
def calculate_forecast(df_historical):
    if len(df_historical) < 12:
        st.warning("⚠️ Zu wenig historische Daten für präzisen Vorjahresvergleich (min. 13 Monate empfohlen).")
    
    df = df_historical.sort_values('month').copy()
    
    # Vorjahreswerte zuordnen
    df['prev_year_amount'] = df['amount'].shift(12)
    
    # Steigerungsrate zum Vorjahr (YoY)
    df['yoy_growth'] = (df['amount'] / df['prev_year_amount']) - 1
    
    # Trend-Faktor: Durchschnitt der letzten 6 verfügbaren Monate
    growth_rates = df['yoy_growth'].dropna()
    if len(growth_rates) >= 6:
        trend_factor = growth_rates.tail(6).mean()
    else:
        trend_factor = growth_rates.mean() if not growth_rates.empty else 0
    
    # 12-Monats-Forecast generieren
    last_date = df['month'].max()
    forecast_list = []
    
    for i in range(1, 13):
        forecast_month = last_date + pd.DateOffset(months=i)
        target_prev_year = forecast_month - pd.DateOffset(years=1)
        
        # Vorjahresmonat suchen
        historical_row = df[df['month'] == target_prev_year]
        
        if not historical_row.empty:
            prev_year_value = historical_row['amount'].values[0]
            # Deine Formel: Vorjahresmonat + (Vorjahresmonat * Trend)
            forecast_amount = prev_year_value * (1 + trend_factor)
        else:
            # Fallback falls Datenlücke
            forecast_amount = df['amount'].tail(6).mean()
            
        forecast_list.append({
            'month': forecast_month,
            'amount': forecast_amount,
            'type': 'Forecast'
        })
    
    return pd.DataFrame(forecast_list), trend_factor

# --- 5. HAUPT-APP ---
st.title("📊 Provisions-Tracker")

try:
    df_raw = load_data()

    if not df_raw.empty:
        df_forecast, trend = calculate_forecast(df_raw)

        # Metriken für den schnellen Überblick (Mobil-freundlich)
        col1, col2 = st.columns(2)
        with col1:
            last_val = df_raw['amount'].iloc[-1]
            st.metric("Letzter Monat", f"{last_val:,.2f} €")
        with col2:
            st.metric("Trend (Ø 6M YoY)", f"{trend*100:+.1f} %")

        # --- PLOTLY CHART ---
        fig = go.Figure()

        # Ist-Daten
        fig.add_trace(go.Scatter(
            x=df_raw['month'], y=df_raw['amount'],
            mode='lines+markers', name='Ist-Daten',
            line=dict(color='#1f77b4', width=3),
            hovertemplate='%{x|%b %Y}: %{y:,.2f}€'
        ))

        # Forecast-Daten
        fig.add_trace(go.Scatter(
            x=df_forecast['month'], y=df_forecast['amount'],
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

        # --- FORECAST TABELLE ---
        with st.expander("Details: Forecast nächste 12 Monate"):
            st.table(df_forecast[['month', 'amount']].assign(
                month=lambda x: x['month'].dt.strftime('%b %Y'),
                amount=lambda x: x['amount'].map('{:,.2f} €'.format)
            ).set_index('month'))

    else:
        st.info("Noch keine Daten vorhanden. Bitte lade Daten in deine Supabase Tabelle hoch.")

except Exception as e:
    st.error(f"Ein Fehler ist aufgetreten: {e}")
