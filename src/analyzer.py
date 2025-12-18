import pandas as pd

def calculate_energy_balance(consumption_df, production_df, battery_capacity_kwh=10.0):
    """
    Calculates the energy balance including self-consumption, grid feed-in, and battery usage.
    """
    df = pd.merge(consumption_df, production_df, on='datetime')
    
    battery_soc = 0.0 # State of Charge in kWh
    battery_soc_history = []
    
    grid_import = []
    grid_export = []
    battery_charge = []
    battery_discharge = []
    
    for i, row in df.iterrows():
        prod = row['production_kWh']
        cons = row['consumption_kWh']
        
        surplus = prod - cons
        
        if surplus > 0:
            # Production > Consumption
            # Charge battery
            charge_potential = surplus
            charge_actual = min(charge_potential, battery_capacity_kwh - battery_soc)
            battery_soc += charge_actual
            
            # Export rest to grid
            export_actual = surplus - charge_actual
            
            grid_import.append(0.0)
            grid_export.append(export_actual)
            battery_charge.append(charge_actual)
            battery_discharge.append(0.0)
            
        else:
            # Consumption > Production
            deficit = cons - prod
            
            # Discharge battery
            discharge_potential = deficit
            discharge_actual = min(discharge_potential, battery_soc)
            battery_soc -= discharge_actual
            
            # Import rest from grid
            import_actual = deficit - discharge_actual
            
            grid_import.append(import_actual)
            grid_export.append(0.0)
            battery_charge.append(0.0)
            battery_discharge.append(discharge_actual)
            
        battery_soc_history.append(battery_soc)
        
    df['grid_import_kWh'] = grid_import
    df['grid_export_kWh'] = grid_export
    df['battery_charge_kWh'] = battery_charge
    df['battery_discharge_kWh'] = battery_discharge
    df['battery_soc_kWh'] = battery_soc_history
    
    return df

def calculate_financials(df, electricity_price_buy=5.0, electricity_price_sell=2.0):
    """
    Calculates financial metrics based on energy flows.
    Prices are in CZK/kWh.
    """
    total_import = df['grid_import_kWh'].sum()
    total_export = df['grid_export_kWh'].sum()
    
    cost_without_pv = df['consumption_kWh'].sum() * electricity_price_buy
    cost_with_pv = (total_import * electricity_price_buy) - (total_export * electricity_price_sell)
    
    savings = cost_without_pv - cost_with_pv
    
    return {
        'total_import_kWh': total_import,
        'total_export_kWh': total_export,
        'cost_without_pv_czk': cost_without_pv,
        'cost_with_pv_czk': cost_with_pv,
        'savings_czk': savings
    }

def calculate_investment_comparison(initial_investment_czk, annual_savings_czk, years=20, sp500_return_pct=8.0, inflation_pct=2.0):
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
        
    # S&P 500 Net Result = Gross Gain - Cumulative Energy Costs (which are equal to Cumulative Savings)
    sp500_net_result = [gain - cost for gain, cost in zip(sp500_gross_gain, cumulative_savings_only)]
        
    return pd.DataFrame({
        'Year': range(years + 1),
        'PV_Cumulative_CashFlow': pv_cumulative,
        'PV_Reinvest_Net_Result': pv_reinvest_net_result,
        'SP500_Gross_Gain': sp500_gross_gain,
        'SP500_Net_Result': sp500_net_result,
        'SP500_Total_Value': sp500_value
    })


