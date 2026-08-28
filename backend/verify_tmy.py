import pvlib
from pvlib.iotools import get_pvgis_tmy
import pandas as pd
import warnings

# Suppress warnings
warnings.simplefilter(action='ignore', category=FutureWarning)

latitude = 50.088
longitude = 14.4208

print(f"Fetching PVGIS TMY data for {latitude}, {longitude}...")
try:
    tmy_data, meta = get_pvgis_tmy(latitude, longitude, outputformat='json', url='https://re.jrc.ec.europa.eu/api/v5_2/')
    
    # Calculate monthly GHI sums
    monthly_ghi = tmy_data['ghi'].groupby(tmy_data.index.month).sum() / 1000 # kWh/m2
    
    print("\nMonthly Global Horizontal Irradiance (kWh/m2):")
    print(monthly_ghi)
    
    apr = monthly_ghi.loc[4]
    may = monthly_ghi.loc[5]
    
    print(f"\nApril GHI: {apr:.2f} kWh/m2")
    print(f"May GHI:   {may:.2f} kWh/m2")
    
    if apr > may:
        print("\nCONCLUSION: April has higher irradiance than May in this TMY dataset.")
    else:
        print("\nCONCLUSION: May has higher irradiance than April in this TMY dataset.")
        
except Exception as e:
    print(f"Error: {e}")
