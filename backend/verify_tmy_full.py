import sys
import os
import pandas as pd
import warnings

# Add app directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from app.pv_calculator import get_pv_production, fetch_pvgis_tmy_data

# Suppress warnings
warnings.simplefilter(action='ignore', category=FutureWarning)

latitude = 50.088
longitude = 14.4208
surface_tilt = 35
surface_azimuth = 180
kwp = 10.0

print(f"Fetching PVGIS TMY data for {latitude}, {longitude}...")

try:
    weather_data = fetch_pvgis_tmy_data(latitude, longitude)
    
    production_df, total_prod = get_pv_production(
        latitude, longitude, surface_tilt, surface_azimuth, kwp,
        weather_data=weather_data
    )
    
    # Calculate monthly sums
    monthly_prod = production_df['production_kWh'].groupby(production_df.index.month).sum()
    
    print("\nMonthly Production (kWh):")
    print(monthly_prod)
    
    apr = monthly_prod.loc[4]
    may = monthly_prod.loc[5]
    
    print(f"\nApril Production: {apr:.2f} kWh")
    print(f"May Production:   {may:.2f} kWh")
    
    if apr > may:
        print("\nCONCLUSION: April has higher production than May.")
    else:
        print("\nCONCLUSION: May has higher production than April.")

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
