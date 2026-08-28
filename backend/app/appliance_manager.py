import pandas as pd
from datetime import date

class ApplianceManager:
    """
    Manages the profiles and consumption calculations for various electrical appliances.
    """

    def __init__(self):
        self.appliances = self._load_appliance_profiles()
        print(f"DEBUG: Loaded appliances: {list(self.appliances.keys())}")
        self.cz_holidays_2024 = [
            date(2024, 1, 1), date(2024, 3, 29), date(2024, 4, 1),
            date(2024, 5, 1), date(2024, 5, 8), date(2024, 7, 5),
            date(2024, 7, 6), date(2024, 9, 28), date(2024, 10, 28),
            date(2024, 11, 17), date(2024, 12, 24), date(2024, 12, 25),
            date(2024, 12, 26)
        ]

    def _load_appliance_profiles(self):
        """
        Loads predefined profiles for various appliances.
        Returns a dictionary where keys are appliance names and values are their profiles.
        A profile includes:
        - 'power_kW': Base power consumption in kW
        - 'daily_hours': Default daily operating hours
        - 'type': Category of the appliance (e.g., 'fixed', 'variable', 'EV', 'heating')
        - 'description': A brief description of the appliance
        - 'seasonal': (Optional) Boolean, True if the appliance operates only in certain months.
        - 'seasonal_months': (Optional) List of months (1-12) when the appliance is active.
        - 'regulatable': (Optional) Boolean, True if the appliance's consumption can be shifted to periods of high PV production.
        """
        return {
            "Bazén - Filtrace": {
                "power_kW": 0.650,
                "daily_hours": 8,
                "type": "fixed",
                "description": "Filtrace bazénu. Běží pouze při přebytku z FVE (regulovatelné).",
                "seasonal": True,
                "seasonal_months": [5, 6, 7, 8, 9],
                "regulatable": True,
                "only_surplus": True
            },
            "Bojler - 200l": {
                "power_kW": 2.2,
                "daily_hours": 2,
                "type": "heating",
                "description": "Ohřev TUV, 200l. V zimě (XI-II) se dohřeje ze sítě, jinak z přebytků.",
                "regulatable": True,
                "force_winter_charge": True
            },
            "Bojler": { # Alias for 200l
                "power_kW": 2.2,
                "daily_hours": 2,
                "type": "heating",
                "description": "Ohřev TUV, základní (vazba na stará nastavení).",
                "regulatable": True,
                "force_winter_charge": True
            },
            "Bojler - 300l": {
                "power_kW": 3.5,
                "daily_hours": 2,
                "type": "heating",
                "description": "Ohřev TUV, 300l. V zimě (XI-II) se dohřeje ze sítě, jinak z přebytků.",
                "regulatable": True,
                "force_winter_charge": True
            },
            "Bojler - 500l": {
                "power_kW": 4.5,
                "daily_hours": 3,
                "type": "heating",
                "description": "Ohřev TUV, 500l. V zimě (XI-II) se dohřeje ze sítě, jinak z přebytků.",
                "regulatable": True,
                "force_winter_charge": True
            },
            "Bojler - 1000l": {
                "power_kW": 6.0,
                "daily_hours": 4,
                "type": "heating",
                "description": "Ohřev TUV, 1000l. V zimě (XI-II) se dohřeje ze sítě, jinak z přebytků.",
                "regulatable": True,
                "force_winter_charge": True
            },
            "Sušička": {
                "power_kW": 2.5,
                "daily_hours": 1,
                "type": "variable",
                "description": "Sušička prádla. Odložený start na víkend při dostatku FVE.",
                "regulatable": True,
                "weekend_only": True
            },
            "Pračka": {
                "power_kW": 2.0,
                "daily_hours": 1.5,
                "type": "variable",
                "description": "Pračka prádla. Odložený start na víkend při dostatku FVE.",
                "regulatable": True,
                "weekend_only": True
            },
            "Myčka": {
                "power_kW": 1.5,
                "daily_hours": 1,
                "type": "variable",
                "description": "Myčka nádobí. Přednostně z FVE, jinak start v 8:00.",
                "regulatable": True,
                "preferred_start_hour": 8
            },
            "EV - Jaecoo 7 (Týdně)": {
                "power_kW": 4.6,
                "min_power_kW": 1.38,
                "max_power_kW": 4.6,
                "charge_kwh": 30.0,
                "type": "EV",
                "description": "Nabíjení 1x týdně (např. v pondělí). Celkem 30 kWh.",
                "regulatable": True,
                "charging_strategy": "weekly"
            },
            "EV - Jaecoo 7 (Víkendy)": {
                "power_kW": 4.6,
                "min_power_kW": 1.38,
                "max_power_kW": 4.6,
                "charge_kwh": 10.0,
                "type": "EV",
                "description": "Nabíjení v Sobotu, Neděli a Svátky (10 kWh na den).",
                "regulatable": True,
                "charging_strategy": "non_working"
            },
            "EV - Jaecoo 7 (Denně)": {
                "power_kW": 4.6,
                "min_power_kW": 1.38,
                "max_power_kW": 4.6,
                "charge_kwh": 5.0,
                "type": "EV",
                "description": "Nabíjení každý den (5 kWh na den). Vhodné pro dojíždění.",
                "regulatable": True,
                "charging_strategy": "daily"
            },
            "EV - Jaecoo 7": { # Alias for Weekly
                "power_kW": 4.6,
                "min_power_kW": 1.38,
                "max_power_kW": 4.6,
                "charge_kwh": 30.0,
                "type": "EV",
                "description": "Nabíjení (vazba na stará nastavení - Týdně).",
                "regulatable": True,
                "charging_strategy": "weekly"
            },
            "EV - Enyaq (Týdně)": {
                "power_kW": 13.2,
                "min_power_kW": 3.2,
                "max_power_kW": 13.2,
                "charge_kwh": 60.0,
                "type": "EV",
                "description": "Nabíjení 1x týdně. Celkem 60 kWh.",
                "regulatable": True,
                "charging_strategy": "weekly"
            },
            "EV - Enyaq (Víkendy)": {
                "power_kW": 13.2,
                "min_power_kW": 3.2,
                "max_power_kW": 13.2,
                "charge_kwh": 20.0,
                "type": "EV",
                "description": "Nabíjení v Sobotu, Neděli a Svátky (20 kWh na den).",
                "regulatable": True,
                "charging_strategy": "non_working"
            },
            "EV - Enyaq": { # Alias for Weekly
                "power_kW": 13.2,
                "min_power_kW": 3.2,
                "max_power_kW": 13.2,
                "charge_kwh": 60.0,
                "type": "EV",
                "description": "Nabíjení (vazba na stará nastavení - Týdně).",
                "regulatable": True,
                "charging_strategy": "weekly"
            },
            "Tepelné čerpadlo": {
                "power_kW": 3.0,
                "daily_hours": 6,
                "type": "heating",
                "description": "Tepelné čerpadlo. Vytápění a TUV."
            },
            "Zimní vytápění": {
                "power_kW": 2.2, 
                "daily_hours": 6, 
                "type": "heating", 
                "description": "Přímotop nebo el. topení. Aktivní pouze v zimních měsících (XI-II), bere ze sítě, pokud není FVE.", 
                "seasonal": True, 
                "seasonal_months": [1, 2, 11, 12], 
                "force_winter_charge": True
            },
            "Bazén - Ohřev vody": {
                "power_kW": 5.0,
                "daily_hours": 4,
                "type": "heating",
                "description": "Ohřev bazénu. Běží pouze při dostatku elektřiny z FVE.",
                "seasonal": True,
                "seasonal_months": [5, 6, 7, 8],
                "regulatable": True,
                "only_surplus": True
            },
            "Termální baterie": {
                "power_kW": 2.0,
                "capacity_kwh": 100.0,
                "type": "storage",
                "description": "Termální baterie (akumulace do vody/vzduchu)."
            }
        }

    def get_appliance_profile(self, appliance_name):
        """
        Returns the profile for a given appliance name.
        """
        return self.appliances.get(appliance_name)

    def calculate_appliance_consumption(self, appliance_name, usage_params, datetime_series, production_df=None):
        """
        Calculates the consumption series for a specific appliance based on usage parameters.
        Args:
            appliance_name (str): The name of the appliance.
            usage_params (dict): Dictionary of usage parameters (e.g., 'hours_per_day').
            datetime_series (pd.Series): A pandas Series of datetime objects for which to calculate consumption.
            production_df (pd.DataFrame): (Optional) DataFrame with PV production data, used for regulatable appliances.
        Returns:
            pd.Series: A Series with consumption in kWh for each datetime point.
        """
        if not isinstance(datetime_series, pd.Series):
            datetime_series = pd.Series(datetime_series, index=datetime_series)

        profile = self.get_appliance_profile(appliance_name)
        if not profile:
            raise ValueError(f"Appliance '{appliance_name}' not found.")

        consumption_series = pd.Series(0.0, index=datetime_series)
        power_kW = profile['power_kW']
        appliance_type = profile['type']
        is_seasonal = profile.get('seasonal', False)
        seasonal_months = profile.get('seasonal_months', [])
        is_regulatable = profile.get('regulatable', False)

        # Seasonal check
        if is_seasonal:
            seasonal_mask = datetime_series.dt.month.isin(seasonal_months)
            if not seasonal_mask.any():
                return consumption_series
            datetime_series = datetime_series[seasonal_mask]
            if production_df is not None:
                production_df = production_df[production_df.index.isin(datetime_series)]

        if is_regulatable and production_df is not None:
            default_daily_hours = profile.get('daily_hours', 0)
            daily_kwh_needed = profile['power_kW'] * usage_params.get('daily_hours', default_daily_hours)
            
            # For EV, we use charge_kwh instead of daily_hours
            if appliance_type == "EV":
                charge_kwh = usage_params.get('charge_kwh', profile.get('charge_kwh', 0))
                # EV logic usually spans multiple days or specific sessions, 
                # but for simplicity in this model, we'll try to cover charge_kwh whenever surplus exists.
                # However, the user wants "recommended charging", so let's optimize it.
                
            surplus_df = production_df.copy()
            surplus_df.rename(columns={'production_kWh': 'surplus_kWh'}, inplace=True)
            
            # Process day by day for regulatable appliances
            unique_days = datetime_series.dt.date.unique()
            for day in unique_days:
                # Weekend only check (Washer, Dryer)
                if profile.get('weekend_only', False) and day.weekday() < 5:
                    continue
                
                daily_mask = (datetime_series.dt.date == day)
                daily_surplus = surplus_df[daily_mask]
                
                # Special handling for EV charging (Intelligent modulation & Strategies)
                if appliance_type == "EV":
                    strategy = profile.get('charging_strategy', 'weekly')
                    
                    if strategy == "weekly":
                        # We assume charging is needed once a week (e.g. target session on Monday)
                        target_day = 0 
                        if day.weekday() != target_day:
                            continue
                        kwh_to_cover = usage_params.get('charge_kwh', profile.get('charge_kwh', 30.0))
                        search_period = 7 # week
                    elif strategy == "non_working":
                        is_non_working = day.weekday() >= 5 or day in self.cz_holidays_2024
                        if not is_non_working:
                            continue
                        kwh_to_cover = usage_params.get('charge_kwh', profile.get('charge_kwh', 10.0))
                        search_period = 1 # just this day
                    elif strategy == "daily":
                        kwh_to_cover = usage_params.get('charge_kwh', profile.get('charge_kwh', 5.0))
                        search_period = 1 # just this day
                    else:
                        continue
                        
                    min_p = profile.get('min_power_kW', 0.0)
                    max_p = profile.get('max_power_kW', power_kW)
                    
                    search_mask = (datetime_series.dt.date >= day) & (datetime_series.dt.date < day + pd.Timedelta(days=search_period))
                    period_slots = datetime_series[search_mask]
                    
                    # Priority 1: Surplus during Afternoons or Non-working hours (for weekly)
                    for index in period_slots.index:
                        if kwh_to_cover <= 0.001: break
                        dt = period_slots.loc[index]
                        
                        # Use surplus if it exists
                        s = surplus_df.loc[index, 'surplus_kWh']
                        
                        # Modulation logic
                        if s >= min_p:
                            p = min(max_p, s, kwh_to_cover)
                            consumption_series.loc[index] = p
                            kwh_to_cover -= p
                        elif s > 0 and strategy != "weekly":
                            # For daily/non_working, if HA is involved, we might pull min even if s < min?
                            # But let's stick to surplus modulation (100% target)
                            p = min(max_p, s, kwh_to_cover)
                            consumption_series.loc[index] = p
                            kwh_to_cover -= p

                    # Priority 2: Force night charging if not covered (BUT only if NOT only_surplus)
                    if kwh_to_cover > 0.001 and not profile.get('only_surplus', False):
                        # For weekly, we have a whole week to find surplus, but at the end of the window 
                        # we might need to top up. For daily, we top up at night.
                        for index in period_slots.index:
                            if kwh_to_cover <= 0.001: break
                            dt = period_slots.loc[index]
                            if dt.hour >= 22 or dt.hour <= 6:
                                p = min(max_p, kwh_to_cover)
                                consumption_series.loc[index] = p
                                kwh_to_cover -= p
                    continue

                # Standard regulatable (Bojler, Pool, Dishwasher)
                kwh_to_cover = daily_kwh_needed
                
                # 1. Fill from Surplus
                for index, row in daily_surplus.iterrows():
                    if kwh_to_cover <= 0: break
                    s = row['surplus_kWh']
                    p = min(power_kW, s, kwh_to_cover)
                    if p > 0:
                        consumption_series.loc[index] = p
                        kwh_to_cover -= p
                
                # 2. Fill from Grid if required
                if kwh_to_cover > 0:
                    if profile.get('only_surplus', False):
                        # Pool heating/filtration - strictly surplus
                        continue
                    
                    is_winter = day.month in [1, 2, 11, 12]
                    force_winter = profile.get('force_winter_charge', False)
                    pref_hour = profile.get('preferred_start_hour')

                    if force_winter and is_winter:
                        # Bojler winter force charge at night/morning
                        for index, dt in datetime_series[daily_mask].items():
                            if kwh_to_cover <= 0: break
                            if dt.hour >= 18 or dt.hour <= 8:
                                p = min(power_kW, kwh_to_cover)
                                consumption_series.loc[index] = p
                                kwh_to_cover -= p
                    elif pref_hour is not None:
                        # Dishwasher force charge at specific time
                        # Start from preferred hour
                        for index, dt in datetime_series[daily_mask].items():
                            if kwh_to_cover <= 0: break
                            if dt.hour >= pref_hour:
                                p = min(power_kW, kwh_to_cover)
                                consumption_series.loc[index] = p
                                kwh_to_cover -= p
                    else:
                        # 3. Default Fallback: Run in evening (e.g. 18:00) if no specific preference
                        # This covers Washing Machine/Dryer in winter/no-sun days
                        for index, dt in datetime_series[daily_mask].items():
                            if kwh_to_cover <= 0: break
                            if dt.hour >= 18:
                                p = min(power_kW, kwh_to_cover)
                                consumption_series.loc[index] = p
                                kwh_to_cover -= p
            
            return consumption_series

        # Fallback for non-regulatable or type-based logic
        if appliance_type == "fixed" or appliance_type == "variable" or appliance_type == "heating":
            daily_hours = usage_params.get('daily_hours', profile.get('daily_hours', 0))
            if daily_hours > 0:
                active_hours = int(daily_hours)
                if active_hours > 0:
                    consumption_per_active_hour = (power_kW * daily_hours) / active_hours
                    for date in datetime_series.dt.date.unique():
                        daily_mask = (datetime_series.dt.date == date)
                        active_period_mask = daily_mask & (datetime_series.dt.hour >= 8) & (datetime_series.dt.hour < 8 + active_hours)
                        # Fix for seasonal index mismatch: use the specific timestamps (index) where mask is true
                        valid_indices = active_period_mask.index[active_period_mask]
                        if not valid_indices.empty:
                            consumption_series.loc[valid_indices] = consumption_per_active_hour
        
        return consumption_series

    def get_recommendations(self, active_appliances):
        """
        Returns a list of recommendations for the active appliances.
        """
        recs = []
        for app_name in active_appliances:
            profile = self.get_appliance_profile(app_name)
            if not profile: continue
            
            if app_name.startswith("Bojler"):
                recs.append(f"**{app_name}**: V zimním období se Boiler nahřívá v nočních hodinách (pokud není dostatek FVE). V létě je prioritně nahříván z přebytků FVE.")
            elif "Bazén" in app_name:
                recs.append(f"**{app_name}**: Provoz je omezen výhradně na hodiny s dostatečným přebytkem z FVE. Tím se maximalizuje úspora.")
            elif app_name in ["Pračka", "Sušička"]:
                recs.append(f"**{app_name}**: Doporučujeme spouštět o víkendech v časech 10:00 - 15:00, kdy je nejvyšší pravděpodobnost přebytků z FVE.")
            elif app_name == "Myčka":
                recs.append(f"**{app_name}**: Ideální start je nastaven na 8:00 (nebo při přebytku FVE), aby se využilo dopolední slunce.")
            elif profile["type"] == "EV":
                strategy_desc = ""
                strategy = profile.get('charging_strategy', 'weekly')
                capacity_info = ""
                
                # Determine capacity info based on vehicle type
                if "Jaecoo" in app_name:
                    capacity_info = " (Baterie ~18 kWh)"
                elif "Enyaq" in app_name:
                    capacity_info = " (Baterie ~60-80 kWh)"

                if strategy == "daily":
                    strategy_desc = "Režim denního dobíjení (~40-50% kapacity nebo obden). Vhodné pro pravidelné dojíždění."
                elif strategy == "weekly":
                    strategy_desc = "Režim týdenního nabíjení (cyklus 0-100% jednou týdně). Vhodné pro víkendové řidiče."
                elif strategy == "non_working":
                    strategy_desc = "Režim nabíjení o víkendech a svátcích. Maximalizuje využití volného času a sluneční energie."

                recs.append(f"**{app_name}**{capacity_info}: {strategy_desc} Inteligentní modulace výkonu ({profile.get('min_power_kW', 0)} - {profile.get('max_power_kW', 0)} kW). Přednostně využívá přebytky FVE.")
        
        return recs

    def get_all_appliance_names(self):
        """
        Returns a list of all available appliance names.
        """
        return list(self.appliances.keys())

