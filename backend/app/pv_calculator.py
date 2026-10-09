import pandas as pd
import pvlib
from pvlib.location import Location

import pandas as pd
import pvlib
from pvlib.location import Location
from pvlib.iotools import get_pvgis_tmy
import warnings
import sqlite3
import json
import os

# Suppress FutureWarnings from pvlib
warnings.simplefilter(action='ignore', category=FutureWarning)

# Teplotní koeficient Pmax pro monokrystalický PERC panel: −0,4 %/°C nad 25 °C.
# Není to parametr v UI — konstanta modulu (design 8.2).
TEMP_COEFF_PER_C = -0.004


def apply_temperature_derate(production, cell_temp, coeff=TEMP_COEFF_PER_C):
    """Teplotní korekce DC výkonu podle teploty článku.

    `production` i `cell_temp` mohou být pandas Series nebo skaláry —
    operace je elementwise. Aplikuje se PŘED systémovými ztrátami.
    """
    return production * (1 + coeff * (cell_temp - 25.0))

def fetch_pvgis_tmy_data(latitude, longitude, tz='UTC'):
    """
    Fetches TMY weather data from PVGIS for a given location.

    Args:
        latitude (float): Latitude of the location.
        longitude (float): Longitude of the location.
        tz (str): The timezone of the location.

    Returns:
        pd.DataFrame: A DataFrame containing TMY weather data (GHI, DNI, DHI, temp_air, wind_speed).
    """
    # Cache setup
    db_dir = "data"
    db_path = os.path.join(db_dir, "weather_cache.db")
    os.makedirs(db_dir, exist_ok=True)
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS tmy_cache (lat REAL, lon REAL, data TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
        
        # Check cache (matching to 3 decimal places ~ 100m)
        cursor.execute("SELECT data FROM tmy_cache WHERE ABS(lat - ?) < 0.001 AND ABS(lon - ?) < 0.001", (latitude, longitude))
        row = cursor.fetchone()
        
        if row:
            # print(f"DEBUG: Using cached TMY data for {latitude}, {longitude}")
            tmy_data = pd.read_json(row[0], orient='split')
            # Ensure the index is timezone-aware
            if tmy_data.index.tz is None:
                tmy_data.index = tmy_data.index.tz_localize('UTC').tz_convert(tz)
            else:
                tmy_data.index = tmy_data.index.tz_convert(tz)
            
            # Normalize year to 2024
            tmy_data.index = tmy_data.index.map(lambda x: x.replace(year=2024))
            conn.close()
            return tmy_data

        # PVGIS TMY data typically returns a tuple (data, meta)
        tmy_data, _ = get_pvgis_tmy(latitude, longitude, outputformat='json', url='https://re.jrc.ec.europa.eu/api/v5_2/')
        
        # Ensure the index is timezone-aware and set to the correct timezone
        tmy_data.index = tmy_data.index.tz_convert(tz)
        
        # Store in cache before normalization (raw TMY data)
        # We use orient='split' to preserve index and columns cleanly
        cursor.execute("INSERT INTO tmy_cache (lat, lon, data) VALUES (?, ?, ?)", 
                       (latitude, longitude, tmy_data.to_json(orient='split')))
        conn.commit()
        conn.close()

        # Normalize years to 2024 for matching with consumption data
        tmy_data.index = tmy_data.index.map(lambda x: x.replace(year=2024))
        
        return tmy_data
    except Exception as e:
        print(f"Error handling PVGIS TMY data for {latitude}, {longitude}: {e}")
        if 'conn' in locals(): conn.close()
        return None

def get_pv_production(latitude, longitude, surface_tilt, surface_azimuth, kwp, tz='UTC', system_loss_factor=14.0, winter_loss_factor=None, weather_data=None):
    """
    Calculates the PV production for a given location, panel orientation, and capacity,
    applying system losses and optional winter losses. Uses provided weather data if available,
    otherwise falls back to clear-sky model.

    Args:
        latitude (float): Latitude of the location.
        longitude (float): Longitude of the location.
        surface_tilt (float): The tilt of the panels in degrees.
        surface_azimuth (float): The azimuth of the panels in degrees (180 = south).
        kwp (float): The peak power of the PV system in kWp.
        tz (str): The timezone of the location.
        system_loss_factor (float): General system loss factor in percentage (e.g., 14.0 for 14% loss).
        winter_loss_factor (float, optional): Additional loss factor for winter months (Dec, Jan, Feb) in percentage.
        weather_data (pd.DataFrame, optional): TMY weather data (GHI, DNI, DHI, etc.). If None, clear-sky model is used.

    Returns:
        tuple: A tuple containing:
            - pd.DataFrame: A DataFrame with a 'production_kWh' column.
            - float: The total annual production in kWh.
    """
    location = Location(latitude, longitude, tz=tz)
    
    if weather_data is not None:
        # Use provided weather data
        times = weather_data.index
        # Ensure weather data has required columns
        if not all(col in weather_data.columns for col in ['ghi', 'dni', 'dhi', 'temp_air', 'wind_speed']):
            raise ValueError("Provided weather_data DataFrame is missing required columns (ghi, dni, dhi, temp_air, wind_speed).")
        
        # For simplicity, we'll use temperature and wind speed for cell temperature model,
        # but the core irradiance will come directly from weather_data.
        ghi = weather_data['ghi']
        dni = weather_data['dni']
        dhi = weather_data['dhi']
        temp_air = weather_data['temp_air']
        wind_speed = weather_data['wind_speed']

    else:
        # Fallback to clear-sky model if no weather data is provided
        times = pd.date_range(start='2024-01-01', end='2024-12-31 23:00:00', freq='h', tz=tz)
        clearsky = location.get_clearsky(times)
        ghi = clearsky['ghi']
        dni = clearsky['dni']
        dhi = clearsky['dhi']
        temp_air = 25 # Assume constant temperature for clear sky if no temp data
        wind_speed = 1 # Assume constant wind speed

    solar_position = location.get_solarposition(times=times)

    # Calculate Plane of Array (POA) irradiance
    poa_irradiance = pvlib.irradiance.get_total_irradiance(
        surface_tilt=surface_tilt,
        surface_azimuth=surface_azimuth,
        solar_zenith=solar_position['apparent_zenith'],
        solar_azimuth=solar_position['azimuth'],
        dni=dni,
        ghi=ghi,
        dhi=dhi
    )

    # Calculate cell temperature
    # Using Faiman model for simplicity
    cell_temp = pvlib.temperature.faiman(poa_irradiance['poa_global'], temp_air, wind_speed)

    # DC výkon při referenčních podmínkách (1000 W/m^2, 25 °C).
    production = poa_irradiance['poa_global'] / 1000 * kwp

    # Teplotní ztráta PŘED systémovými ztrátami (design 8.2). Riziko
    # dvojího započtení se měří proti PVGIS SARAH3 — viz závěrečné ověření.
    production = apply_temperature_derate(production, cell_temp)

    # Apply general system loss factor
    production *= (1 - system_loss_factor / 100)

    # Apply additional winter loss factor if specified
    if winter_loss_factor is not None:
        winter_months = [12, 1, 2] # December, January, February
        winter_mask = pd.Series(times).dt.month.isin(winter_months).values
        production[winter_mask] *= (1 - winter_loss_factor / 100)
    
    total_production = production.sum()
    
    return pd.DataFrame({'datetime': times, 'production_kWh': production}), total_production

def get_optimal_pv_production(latitude, longitude, kwp, tz='UTC',
                              system_loss_factor=14.0, winter_loss_factor=None,
                              weather_data=None):
    """Nejlepší roční výroba přes sklon 10–70° při azimutu 180° (jih).

    Původní `surface_tilt=latitude` dávalo pro 50°N nesmyslných ~102 %.
    Prohledáme sklon po 5° a vezmeme maximum. `winter_loss_factor`
    propouštíme, aby se reálná výroba a optimum lišily POUZE orientací —
    jinak by poměr mohl přesáhnout 100 %.
    """
    best = None
    for tilt in range(10, 71, 5):
        _, total = get_pv_production(
            latitude=latitude,
            longitude=longitude,
            surface_tilt=tilt,
            surface_azimuth=180,
            kwp=kwp,
            tz=tz,
            system_loss_factor=system_loss_factor,
            winter_loss_factor=winter_loss_factor,
            weather_data=weather_data,
        )
        if best is None or total > best:
            best = total
    return best
