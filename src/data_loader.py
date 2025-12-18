import pandas as pd
import numpy as np

def load_consumption_data(target_annual_kwh=None):
    """
    Simulates loading consumption data.
    If target_annual_kwh is provided, scales the profile to match the total.
    """
    # Create a date range for a year with hourly frequency
    dates = pd.date_range(start='2024-01-01', end='2024-12-31 23:00:00', freq='h')
    
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
    
    if target_annual_kwh is not None:
        current_total = consumption.sum()
        if current_total > 0:
            scaling_factor = target_annual_kwh / current_total
            consumption = consumption * scaling_factor
    
    return pd.DataFrame({'datetime': dates, 'consumption_kWh': consumption})

def load_production_data(kwp=10):
    """
    Simulates PV production data.
    """
    dates = pd.date_range(start='2024-01-01', end='2024-12-31 23:00:00', freq='h')
    
    # Simulate solar production (bell curve during the day, higher in summer)
    # Peak sun hours approx 10:00 to 16:00
    
    day_factor = np.maximum(0, np.sin((dates.hour - 6) * np.pi / 12)) # 0 at 6am and 6pm, 1 at noon
    season_factor = 0.5 + 0.5 * np.cos((dates.dayofyear - 172) * 2 * np.pi / 365) # Peak in summer (approx day 172)
    weather_factor = np.random.uniform(0.2, 1.0, len(dates)) # Clouds etc.
    
    production = kwp * day_factor * season_factor * weather_factor
    
    return pd.DataFrame({'datetime': dates, 'production_kWh': production})
