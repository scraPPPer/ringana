def calculate_forecast(df_historical):
    # Sicherstellen, dass die Daten chronologisch sind
    df = df_historical.sort_values('month').copy()
    
    # 1. Vorjahreswerte zuordnen (Shift um 12 Monate)
    # Wir erstellen eine Hilfsspalte, um die Steigerung zum Vorjahr zu berechnen
    df['prev_year_amount'] = df['amount'].shift(12)
    
    # 2. Steigerungsrate zum Vorjahr berechnen (YoY Growth)
    df['yoy_growth'] = (df['amount'] / df['prev_year_amount']) - 1
    
    # 3. Den Trend-Faktor ermitteln (Durchschnitt der letzten 6 Monate)
    # Wir nehmen nur Zeilen, in denen wir ein Wachstum berechnen konnten
    growth_rates = df['yoy_growth'].dropna()
    if len(growth_rates) >= 6:
        trend_factor = growth_rates.tail(6).mean()
    else:
        trend_factor = growth_rates.mean() if not growth_rates.empty else 0
    
    # 4. Forecast für die nächsten 12 Monate erstellen
    last_date = df['month'].max()
    forecast_list = []
    
    for i in range(1, 13):
        forecast_month = last_date + pd.DateOffset(months=i)
        
        # Finde den Wert genau ein Jahr vor dem Forecast-Monat
        target_prev_year = forecast_month - pd.DateOffset(years=1)
        
        # Suche diesen Wert in den historischen Daten
        historical_row = df[df['month'] == target_prev_year]
        
        if not historical_row.empty:
            prev_year_value = historical_row['amount'].values[0]
            # Deine Formel: Vorjahresmonat + (Vorjahresmonat * Trend)
            forecast_amount = prev_year_value * (1 + trend_factor)
        else:
            # Fallback, falls keine Vorjahresdaten existieren (z.B. bei sehr neuen Apps)
            forecast_amount = df['amount'].tail(6).mean()
            
        forecast_list.append({
            'month': forecast_month,
            'amount': forecast_amount,
            'type': 'Forecast'
        })
    
    return pd.DataFrame(forecast_list)
