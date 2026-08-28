import pandas as pd
from .appliance_manager import ApplianceManager

def calculate_energy_balance(consumption_df, production_df, appliance_manager, active_appliances_data, 
                           battery_capacity_kwh=10.0, grid_export_limit_kw=None,
                           thermal_battery_capacity_kwh=0.0, thermal_battery_charge_power_kw=2.0):
    """
    Calculates the energy balance including self-consumption, grid feed-in, battery usage,
    and integrates consumption from specified appliances, with an optional grid export limit
    and thermal battery storage.
    """
    # Ensure consumption_df has 'datetime' as a column and merge with production_df
    if consumption_df.index.name == 'datetime':
        consumption_df = consumption_df.reset_index()
    
    # Merge consumption and production data
    df = pd.merge(consumption_df, production_df, on='datetime')
    df.set_index('datetime', inplace=True)
    
    # Store individual appliance series for detailed tracking
    appliance_series_dict = {}
    
    # Ensure production_df handed to appliances also has datetime as index
    production_df_indexed = production_df.set_index('datetime') if 'datetime' in production_df.columns else production_df
    
    # Calculate iterative net surplus (production - base household consumption - other scheduled appliances)
    # Managed appliances should only use energy that is truly "free" after the house is powered.
    temp_df = pd.merge(consumption_df[['datetime', 'consumption_kWh']], production_df, on='datetime')
    temp_df.set_index('datetime', inplace=True)
    
    current_surplus_kWh = (temp_df['production_kWh'] - temp_df['consumption_kWh']).clip(lower=0)
    
    for app_name, usage_params in active_appliances_data.items():
        # Build a temporary surplus DF for the appliance
        net_surplus_df = production_df_indexed.copy()
        net_surplus_df['production_kWh'] = current_surplus_kWh
        
        # Calculate appliance consumption based on remaining surplus
        appliance_consumption = appliance_manager.calculate_appliance_consumption(
            app_name, usage_params, pd.Series(df.index, index=df.index), net_surplus_df
        )
        appliance_series_dict[app_name] = appliance_consumption
        
        # Subtract this appliance's consumption from the current surplus for the next appliance
        current_surplus_kWh = (current_surplus_kWh - appliance_consumption).clip(lower=0)
    
    # Add calculated appliance consumption to the existing consumption_kWh
    # We keep a copy of the base consumption for attribution
    df['consumption_base_kWh'] = df['consumption_kWh'].copy()
    
    total_appliance_cons = pd.Series(0.0, index=df.index)
    for app_cons in appliance_series_dict.values():
        total_appliance_cons += app_cons
    
    df['consumption_kWh'] += total_appliance_cons
    
    # Main loop setup
    
    battery_soc = 0.0
    thermal_battery_soc = 0.0
    battery_soc_history = []
    thermal_battery_soc_history = []
    grid_import = []
    grid_export = []
    battery_charge = []
    battery_discharge = []
    thermal_battery_charge = []
    
    appliance_self_consumption = {app: [] for app in appliance_series_dict.keys()}
    appliance_grid_import = {app: [] for app in appliance_series_dict.keys()}
    
    for idx, row in df.iterrows():
        prod = row['production_kWh']
        cons_total = row['consumption_kWh']
        cons_base = row['consumption_base_kWh']
        
        # Calculate how much total energy is available (prod + battery)
        total_available_energy = prod + battery_soc
        
        # Total self-consumption is limited by what we actually consume and what we have available
        total_self_consumed = min(cons_total, total_available_energy)
        
        # Attribution: Base load first
        self_cons_base = min(cons_base, total_self_consumed)
        remaining_self_cons = total_self_consumed - self_cons_base
        
        # Attribution: Appliances next
        for app_name, app_series in appliance_series_dict.items():
            app_cons_this_hour = app_series.loc[idx]
            app_self_cons = min(app_cons_this_hour, remaining_self_cons)
            appliance_self_consumption[app_name].append(app_self_cons)
            remaining_self_cons -= app_self_cons

        # Proceed with normal battery/energy balance logic
        surplus = prod - cons_total
        thermal_charge_this_hour = 0.0
        
        if surplus > 0:
            charge_potential = surplus
            charge_actual = min(charge_potential, battery_capacity_kwh - battery_soc)
            battery_soc += charge_actual
            
            remaining_surplus = surplus - charge_actual
            
            if thermal_battery_capacity_kwh > 0:
                thermal_charge_potential = min(remaining_surplus, thermal_battery_charge_power_kw)
                thermal_charge_actual = min(thermal_charge_potential, thermal_battery_capacity_kwh - thermal_battery_soc)
                thermal_battery_soc += thermal_charge_actual
                thermal_charge_this_hour = thermal_charge_actual
                remaining_surplus -= thermal_charge_actual
            
            export_potential = remaining_surplus
            export_actual = min(export_potential, grid_export_limit_kw) if grid_export_limit_kw is not None else export_potential
            
            grid_import.append(0.0)
            grid_export.append(export_actual)
            battery_discharge.append(0.0)
            battery_charge.append(charge_actual)
            
            # Appliance imports are all 0 in surplus case
            for app in appliance_series_dict.keys():
                appliance_grid_import[app].append(0.0)
        else:
            deficit = cons_total - prod
            discharge_actual = min(deficit, battery_soc)
            battery_soc -= discharge_actual
            import_actual = deficit - discharge_actual
            
            grid_import.append(import_actual)
            grid_export.append(0.0)
            battery_charge.append(0.0)
            battery_discharge.append(discharge_actual)
            
            # Attribution of import to appliances
            remaining_import = import_actual
            # Base load import first
            base_import = min(cons_base - self_cons_base, remaining_import)
            remaining_import -= base_import
            
            # Appliance imports
            for app_name, app_series in appliance_series_dict.items():
                app_cons = app_series.loc[idx]
                app_self = appliance_self_consumption[app_name][-1]
                app_imp = min(app_cons - app_self, remaining_import)
                appliance_grid_import[app_name].append(app_imp)
                remaining_import -= app_imp
        
        battery_soc_history.append(battery_soc)
        thermal_battery_soc_history.append(thermal_battery_soc)
        thermal_battery_charge.append(thermal_charge_this_hour)
        
    df['grid_import_kWh'] = grid_import
    df['grid_export_kWh'] = grid_export
    df['battery_charge_kWh'] = battery_charge
    df['battery_discharge_kWh'] = battery_discharge
    df['battery_soc_kWh'] = battery_soc_history
    df['thermal_battery_charge_kWh'] = thermal_battery_charge
    df['thermal_battery_soc_kWh'] = thermal_battery_soc_history
    
    # Add individual appliance columns
    for app_name in appliance_series_dict.keys():
        df[f'appliance_{app_name}_consumption_kWh'] = appliance_series_dict[app_name]
        df[f'appliance_{app_name}_self_consumption_kWh'] = appliance_self_consumption[app_name]
        df[f'appliance_{app_name}_grid_import_kWh'] = appliance_grid_import[app_name]
    
    return df.reset_index()

def calculate_financials(df, electricity_price_buy=5.0, electricity_price_sell=2.0, active_appliances=[]):
    """
    Calculates financial metrics and adds hourly cost/saving columns to the dataframe.
    """
    # 1. Base cost without PV
    df['cost_without_pv_czk'] = df['consumption_kWh'] * electricity_price_buy
    
    # 2. Revenue from Export
    if isinstance(electricity_price_sell, pd.Series):
        # Align series (assuming index is datetime)
        df['revenue_export_czk'] = df['grid_export_kWh'] * electricity_price_sell
    else:
        df['revenue_export_czk'] = df['grid_export_kWh'] * electricity_price_sell
        
    # 3. Cost with PV (import price)
    df['cost_import_czk'] = df['grid_import_kWh'] * electricity_price_buy
    
    # 4. Total savings (hourly)
    # Savings = (Consumption * buy_price) - (Import * buy_price - Export * sell_price)
    # Savings = (Consumption - Import) * buy_price + Export * sell_price
    # Self-consumption savings = (Consumption - Import) * buy_price
    df['savings_self_consumption_czk'] = (df['consumption_kWh'] - df['grid_import_kWh']) * electricity_price_buy
    df['savings_total_czk'] = df['savings_self_consumption_czk'] + df['revenue_export_czk']
    
    # 5. Appliance-specific metrics (hourly and summary)
    for app in active_appliances:
        col_self_cons = f'appliance_{app}_self_consumption_kWh'
        col_grid_import = f'appliance_{app}_grid_import_kWh'
        col_cons = f'appliance_{app}_consumption_kWh'
        
        if col_self_cons in df.columns:
            df[f'appliance_{app}_savings_czk'] = df[col_self_cons] * electricity_price_buy
        
        if col_grid_import in df.columns:
            # Grid cost per appliance
            df[f'appliance_{app}_grid_cost_czk'] = df[col_grid_import] * electricity_price_buy
            
    total_import = df['grid_import_kWh'].sum()
    total_export = df['grid_export_kWh'].sum()
    revenue_export = df['revenue_export_czk'].sum()
    cost_without_pv = df['cost_without_pv_czk'].sum()
    cost_with_pv = df['cost_import_czk'].sum() - revenue_export
    savings = cost_without_pv - cost_with_pv
    
    return {
        'df': df,
        'total_import_kWh': total_import,
        'total_export_kWh': total_export,
        'cost_without_pv_czk': cost_without_pv,
        'cost_with_pv_czk': cost_with_pv,
        'savings_czk': savings,
        'revenue_export_czk': revenue_export,
        'savings_self_consumption_czk': df['savings_self_consumption_czk'].sum()
    }

def calculate_investment_comparison(initial_investment_czk, annual_savings_czk, years=20, sp500_return_pct=8.0, inflation_pct=2.0, discount_rate_pct=8.0):
    """
    Compares PV investment vs S&P 500 investment.
    """
    # PV Cash Flow
    # Year 0: -Investment
    # Year 1..N: +Savings (adjusted for inflation/energy price increase?) 
    # For simplicity, let's assume savings grow with inflation (energy prices rise)
    
    pv_cash_flow = [-initial_investment_czk]
    pv_cumulative = [-initial_investment_czk]
    
    # S&P 500
    # Year 0: Invest the same amount into S&P 500
    # Year 1..N: Grow by return rate
    # BUT: In the PV scenario, you "save" money every year. 
    # To make it fair, we should compare:
    # Option A (PV): Pay for PV now, pay less for electricity later.
    # Option B (No PV): Keep money, invest in S&P 500, but pay full electricity bill.
    # Actually, the standard comparison is: 
    # "I have X CZK. Should I buy PV or put it in S&P 500?"
    # If I buy PV, I have X less cash, but I generate Y savings/year.
    # If I invest X in S&P 500, I have X * (1+r)^t, but I pay Y more for electricity.
    
    # Let's track "Net Wealth Change" relative to doing nothing (keeping cash under mattress and paying bills).
    
    # Scenario PV:
    # Wealth = -Investment + Sum(Savings_t)
    
    # Scenario S&P 500:
    # Wealth = Investment * (1 + r)^t - Investment (to see gain) 
    # Wait, this is tricky.
    
    # Let's use a simpler approach often used in sales:
    # 1. PV Cumulative Cash Flow: -Invest + Cumulative Savings
    # 2. S&P 500 Value: Investment grows. 
    # But this ignores that with S&P you still pay electricity bills.
    
    # Correct Comparison:
    # Baseline: Pay bills, no investment. Wealth = 0 (relative).
    
    # PV Path:
    # t=0: Spend Invest. Wealth = -Invest.
    # t=1..N: Save money. Wealth increases by Savings.
    
    # S&P Path:
    # t=0: Invest money. Wealth = 0 (Money is still yours, just in stocks).
    # t=1..N: Investment grows. BUT you pay full electricity bill (so you lose 'Savings' amount compared to PV user).
    # So effectively: Wealth = (Invest * (1+r)^t) - Sum(Savings_t) - Invest (since we spent it in PV scenario? No.)
    
    # Let's stick to the user request: "Porovnání investice do realizace FVE ... oproti investování do jiných ... příležitostí"
    # Usually this means:
    # PV Return = Cumulative Savings - Initial Cost
    # S&P Return = (Initial Cost * (1 + r)^t) - Initial Cost
    # This compares "Gain from PV" vs "Gain from S&P".
    # It ignores that S&P gain is liquid, while PV gain is avoided cost.
    
    sp500_value = [initial_investment_czk]
    sp500_gross_gain = [0.0]
    cumulative_savings_only = [0.0]
    
    # Discounted Cash Flow and NPV
    dcf = [] # Discounted cash flows
    pv_dcf = [-initial_investment_czk] # Year 0 investment is already present value
    cumulative_dcf = [-initial_investment_czk]
    
    # PV + Reinvestment
    pv_reinvest_value = [0.0] # Starts at 0, we invest savings at end of year
    pv_reinvest_net_result = [-initial_investment_czk] # Starts at -Investment
    
    current_savings = annual_savings_czk
    
    for t in range(1, years + 1):
        # PV Standard
        # Savings increase with inflation (energy price hike)
        current_savings = current_savings * (1 + inflation_pct/100)
        pv_cash_flow.append(current_savings)
        pv_cumulative.append(pv_cumulative[-1] + current_savings)
        
        cumulative_savings_only.append(cumulative_savings_only[-1] + current_savings)
        
        # PV + Reinvestment
        # Previous portfolio grows
        prev_reinvest_val = pv_reinvest_value[-1]
        new_reinvest_val = prev_reinvest_val * (1 + sp500_return_pct/100)
        # Add new savings to portfolio
        new_reinvest_val += current_savings
        pv_reinvest_value.append(new_reinvest_val)
        # Net result = Portfolio Value - Initial Investment
        pv_reinvest_net_result.append(new_reinvest_val - initial_investment_czk)
        
        # S&P 500
        prev_val = sp500_value[-1]
        new_val = prev_val * (1 + sp500_return_pct/100)
        sp500_value.append(new_val)
        sp500_gross_gain.append(new_val - initial_investment_czk)
        
        # NPV Logic
        # DCF_t = Savings_t / (1 + r)^t
        current_dcf = current_savings / ((1 + discount_rate_pct/100)**t)
        pv_dcf.append(current_dcf)
        cumulative_dcf.append(cumulative_dcf[-1] + current_dcf)
        
    # S&P 500 Net Result = Gross Gain - Cumulative Energy Costs (which are equal to Cumulative Savings)
    sp500_net_result = [gain - cost for gain, cost in zip(sp500_gross_gain, cumulative_savings_only)]
        
    return pd.DataFrame({
        'Year': range(years + 1),
        'PV_Cumulative_CashFlow': pv_cumulative,
        'PV_Reinvest_Net_Result': pv_reinvest_net_result,
        'SP500_Gross_Gain': sp500_gross_gain,
        'SP500_Net_Result': sp500_net_result,
        'SP500_Total_Value': sp500_value,
        'PV_DCF': pv_dcf,
        'PV_Cumulative_DCF': cumulative_dcf
    })

def analyze_spot_profitability(production_df, spot_prices_df, margin_czk_kwh=0.4, fixed_price_czk_kwh=2.5, analysis_year=2024):
    """
    Compares revenue from selling 1 kWp production on Spot market vs Fixed price.
    """
    # 1. Prepare Production
    # TMY data usually has a dummy year (e.g. 2016 or 2005). We overwrite it with analysis_year to align.
    prod = production_df.copy()
    if 'datetime' in prod.columns:
        prod['datetime'] = pd.to_datetime(prod['datetime'])
        # Replace year
        prod['datetime'] = prod['datetime'].apply(lambda x: x.replace(year=analysis_year))
        prod.set_index('datetime', inplace=True)
    elif prod.index.name == 'datetime':
         # If already indexed, rebuild index with correct year
         new_index = [t.replace(year=analysis_year) for t in prod.index]
         prod.index = pd.to_datetime(new_index)
         
    # Ensure propduction index is tz-naive to match spot prices
    if prod.index.tz is not None:
        prod.index = prod.index.tz_localize(None)
         
    # 2. Prepare Spot Prices
    spot = spot_prices_df.copy()
    spot['datetime'] = pd.to_datetime(spot['datetime'])
    # Convert to timezone naive if needed or align timezones
    # Usually TMY from PVGIS is UTC. Spot prices are usually Local or UTC.
    # Let's assume input spot prices are already UTC aligned or we ignore TZ for this estimation.
    # For robust alignment, we'll convert both to naive UTC.
    spot['datetime'] = spot['datetime'].dt.tz_localize(None) 
    spot.set_index('datetime', inplace=True)
    
    # 3. Merge
    # Use inner join to only keep overlapping times (e.g. if spot data is missing for some days)
    merged = pd.merge(prod[['production_kWh']], spot[['price_czk']], left_index=True, right_index=True, how='inner')
    
    # 4. Calculate Revenues
    # Spot Price is usually EUR/MWh or CZK/MWh in DB. 
    # Input spot_prices_df is expected to have 'price_czk' column.
    # If it is MWh, we divide by 1000 to get CZK/kWh.
    # Check magnitude: if price is > 100, it's likely MWh.
    # But let's assume caller handles unit conversion or we check.
    # Based on main.py, we load "price_czk". In DB it is MWh.
    
    # Let's handle unit directly here to be safe
    # If mean price is > 10, it's MWh.
    if merged['price_czk'].mean() > 10:
        merged['price_czk_kwh'] = merged['price_czk'] / 1000.0
    else:
        merged['price_czk_kwh'] = merged['price_czk']
        
    revenue_spot = merged['production_kWh'] * (merged['price_czk_kwh'] - margin_czk_kwh)
    revenue_fixed = merged['production_kWh'] * fixed_price_czk_kwh
    
    merged['revenue_spot_czk'] = revenue_spot
    merged['revenue_fixed_czk'] = revenue_fixed
    merged['diff_czk'] = revenue_spot - revenue_fixed
    
    # 5. Aggregate Monthly
    monthly = merged.resample('M').sum()
    monthly['month_name'] = monthly.index.strftime('%B')
    
    return {
        'total_revenue_spot': revenue_spot.sum(),
        'total_revenue_fixed': revenue_fixed.sum(),
        'monthly_data': monthly[['revenue_spot_czk', 'revenue_fixed_czk', 'diff_czk', 'month_name']].reset_index().to_dict(orient='records'),
        'hourly_data_sample': merged.head(100).reset_index().astype(str).to_dict(orient='records') # Sample for chart
    }


