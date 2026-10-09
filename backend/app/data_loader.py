import pandas as pd
import numpy as np

def load_consumption_data(target_annual_kwh=None):
    """
    Simulates loading consumption data.
    If target_annual_kwh is provided, scales the profile to match the total.
    """
    # Create a date range for a year with hourly frequency, explicitly setting UTC timezone
    dates = pd.date_range(start='2024-01-01', end='2024-12-31 23:00:00', freq='h', tz='UTC')
    
    # Simulate consumption pattern (higher in winter/evening, lower in summer/day)
    # This is a very basic mock
    # Simulate consumption pattern (higher in winter/evening, lower in summer/day)
    # This is a very basic mock
    base_load = 0.5  # kW
    # Use .to_numpy() to ensure we work with arrays, not pandas Index objects
    day_of_year = dates.dayofyear.to_numpy()
    hour = dates.hour.to_numpy()
    
    seasonal_variation = 0.2 * np.cos((day_of_year - 15) * 2 * np.pi / 365)
    daily_variation = 0.3 * np.sin((hour - 6) * 2 * np.pi / 24)
    random_noise = np.random.normal(0, 0.1, len(dates))
    
    consumption = base_load + seasonal_variation + daily_variation + random_noise
    consumption = np.maximum(consumption, 0) # Ensure no negative consumption
    
    print(f"DEBUG: Initial consumption sum: {consumption.sum()}")
    print(f"DEBUG: target_annual_kwh: {target_annual_kwh}")

    if target_annual_kwh is not None:
        current_total = consumption.sum()
        if current_total > 0:
            scaling_factor = target_annual_kwh / current_total
            print(f"DEBUG: Scaling factor: {scaling_factor}")
            consumption = consumption * scaling_factor
    
    print(f"DEBUG: Final consumption sum: {consumption.sum()}")
    print(f"DEBUG: Consumption head: {consumption[:5]}")
    
    return pd.DataFrame({'datetime': dates, 'consumption_kWh': consumption})

from .pv_calculator import get_pv_production, get_optimal_pv_production, fetch_pvgis_tmy_data

def load_production_data(kwp=10, latitude=50.6607, longitude=14.03227, surface_tilt=35, surface_azimuth=180, system_loss_factor=14.0, winter_loss_factor=10.0):
    """
    Calculates PV production data using pvlib and returns both actual and optimal production.
    Fetches TMY data from PVGIS for more realistic simulation.
    """
    # Fetch TMY weather data
    weather_data = fetch_pvgis_tmy_data(latitude, longitude)
    if weather_data is None:
        raise ValueError(f"Nepodařilo se načíst meteorologická data z PVGIS pro souřadnice: {latitude}, {longitude}.")

    production_df, total_production = get_pv_production(
        latitude=latitude,
        longitude=longitude,
        surface_tilt=surface_tilt,
        surface_azimuth=surface_azimuth,
        kwp=kwp,
        system_loss_factor=system_loss_factor,
        winter_loss_factor=winter_loss_factor,
        weather_data=weather_data
    )
    
    optimal_production = get_optimal_pv_production(
        latitude=latitude,
        longitude=longitude,
        kwp=kwp,
        system_loss_factor=system_loss_factor,
        weather_data=weather_data
    )
    
    return production_df, total_production, optimal_production
