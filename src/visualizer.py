import plotly.graph_objects as go
import plotly.express as px
import pandas as pd

def plot_energy_balance_daily(df, date):
    """
    Plots energy balance for a specific day.
    """
    daily_df = df[df['datetime'].dt.date == date]
    
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(x=daily_df['datetime'], y=daily_df['consumption_kWh'], name='Spotřeba', line=dict(color='red')))
    fig.add_trace(go.Scatter(x=daily_df['datetime'], y=daily_df['production_kWh'], name='Výroba FVE', line=dict(color='green')))
    fig.add_trace(go.Scatter(x=daily_df['datetime'], y=daily_df['battery_soc_kWh'], name='Stav Baterie', line=dict(color='blue', dash='dot')))
    
    fig.update_layout(title=f'Energetická Bilance - {date}', xaxis_title='Čas', yaxis_title='kWh')
    return fig

def plot_monthly_stats(df):
    """
    Plots monthly aggregation of import/export/production/consumption.
    """
    df['month'] = df['datetime'].dt.month_name()
    monthly = df.groupby('month')[['consumption_kWh', 'production_kWh', 'grid_import_kWh', 'grid_export_kWh']].sum().reset_index()
    
    # Sort by month index to ensure correct order
    # This is a quick hack, better to use categorical type
    months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
    monthly['month_index'] = monthly['month'].apply(lambda x: months.index(x))
    monthly = monthly.sort_values('month_index')
    
    fig = go.Figure()
    fig.add_trace(go.Bar(x=monthly['month'], y=monthly['consumption_kWh'], name='Spotřeba'))
    fig.add_trace(go.Bar(x=monthly['month'], y=monthly['production_kWh'], name='Výroba'))
    fig.add_trace(go.Bar(x=monthly['month'], y=monthly['grid_import_kWh'], name='Nákup ze sítě'))
    fig.add_trace(go.Bar(x=monthly['month'], y=monthly['grid_export_kWh'], name='Prodej do sítě'))
    
    fig.update_layout(title='Měsíční Statistiky', barmode='group')
    return fig

def plot_investment_comparison(df):
    """
    Plots PV Cumulative Cash Flow vs S&P 500 Net Result.
    """
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(x=df['Year'], y=df['PV_Cumulative_CashFlow'], name='FVE Kumulativní Cashflow', line=dict(color='green', width=3)))
    fig.add_trace(go.Scatter(x=df['Year'], y=df['PV_Reinvest_Net_Result'], name='FVE + Reinvestice úspor do S&P 500', line=dict(color='purple', width=3, dash='dot')))
    fig.add_trace(go.Scatter(x=df['Year'], y=df['SP500_Net_Result'], name='S&P 500 (po zaplacení energií)', line=dict(color='blue', width=3, dash='dash')))
    fig.add_trace(go.Scatter(x=df['Year'], y=df['SP500_Total_Value'], name='S&P 500 (Hrubá hodnota)', line=dict(color='gray', width=1, dash='dot')))
    
    # Add zero line
    fig.add_hline(y=0, line_dash="dot", line_color="gray")

    
    fig.update_layout(
        title='Porovnání Návratnosti: FVE vs S&P 500',
        xaxis_title='Roky',
        yaxis_title='CZK',
        hovermode="x unified"
    )
    return fig

def plot_savings_composition(value1, value2, labels=['Úspora vlastní spotřebou', 'Příjem z prodeje'], unit="CZK"):
    """
    Plots a pie chart showing the composition of savings or energy.
    """
    values = [value1, value2]
    
    # Helper for formatting
    def fmt(val):
        return "{:,.2f}".format(val).replace(",", " ").replace(".", ",")
        
    display_unit = "Kč" if unit == "CZK" else unit
    formatted_text = [f"{fmt(v)} {display_unit}" for v in values]
    
    fig = go.Figure(data=[go.Pie(labels=labels, values=values, hole=.3, 
                                 text=formatted_text,
                                 textinfo='label+text+percent')])
    fig.update_layout(title=f'Složení ({unit})')
    return fig

def plot_energy_treemap(result_df):
    """
    Plots a treemap showing the composition of energy (Self-consumption vs Export) by Month.
    """
    # Resample to monthly sums
    monthly_df = result_df.resample('ME', on='datetime').sum()
    monthly_df['Month_En'] = monthly_df.index.strftime('%B')
    
    # Czech Month Names Mapping
    czech_months = {
        "January": "Leden", "February": "Únor", "March": "Březen", "April": "Duben",
        "May": "Květen", "June": "Červen", "July": "Červenec", "August": "Srpen",
        "September": "Září", "October": "Říjen", "November": "Listopad", "December": "Prosinec"
    }
    monthly_df['Month'] = monthly_df['Month_En'].map(czech_months)
    
    # Calculate monthly values
    monthly_self_consumption_kwh = monthly_df['production_kWh'] - monthly_df['grid_export_kWh']
    monthly_export_kwh = monthly_df['grid_export_kWh']
    
    # Prepare data for Treemap
    data = []
    
    for i, month in enumerate(monthly_df['Month']):
        # Self-consumption item
        data.append({
            'Category': 'Vlastní spotřeba',
            'Month': month,
            'Value': monthly_self_consumption_kwh.iloc[i]
        })
        # Export item
        data.append({
            'Category': 'Export do sítě',
            'Month': month,
            'Value': monthly_export_kwh.iloc[i]
        })
        
    df_treemap = pd.DataFrame(data)
    
    # Filter out zero or negative values
    df_treemap = df_treemap[df_treemap['Value'] > 0]
    
    # Treemap with Month -> Category hierarchy
    fig = px.treemap(df_treemap, path=['Month', 'Category'], values='Value',
                     color='Category',
                     color_discrete_map={'Vlastní spotřeba': 'blue', 'Export do sítě': 'cyan'})
    
    fig.update_layout(title='Energetická Bilance (Treemap - kWh)')
    return fig

def plot_savings_treemap(result_df, price_buy, price_sell):
    """
    Plots a treemap showing the composition of total savings by Month and Category.
    """
    # Resample to monthly sums
    monthly_df = result_df.resample('ME', on='datetime').sum()
    monthly_df['Month_En'] = monthly_df.index.strftime('%B')
    
    # Czech Month Names Mapping
    czech_months = {
        "January": "Leden", "February": "Únor", "March": "Březen", "April": "Duben",
        "May": "Květen", "June": "Červen", "July": "Červenec", "August": "Srpen",
        "September": "Září", "October": "Říjen", "November": "Listopad", "December": "Prosinec"
    }
    monthly_df['Month'] = monthly_df['Month_En'].map(czech_months)
    
    # Calculate monthly values
    monthly_self_consumption_kwh = monthly_df['production_kWh'] - monthly_df['grid_export_kWh']
    
    # Calculate financial values
    savings_self_consumption_czk = monthly_self_consumption_kwh * price_buy
    revenue_export_czk = monthly_df['grid_export_kWh'] * price_sell
    
    # Prepare data for Treemap
    data = []
    
    for i, month in enumerate(monthly_df['Month']):
        # Self-consumption item
        data.append({
            'Category': 'Úspora vlastní spotřebou',
            'Month': month,
            'Value': savings_self_consumption_czk.iloc[i]
        })
        # Export item
        data.append({
            'Category': 'Příjem z prodeje',
            'Month': month,
            'Value': revenue_export_czk.iloc[i]
        })
        
    df_treemap = pd.DataFrame(data)
    
    # Filter out zero or negative values
    df_treemap = df_treemap[df_treemap['Value'] > 0]
    
    # Treemap with Month -> Category hierarchy
    fig = px.treemap(df_treemap, path=['Month', 'Category'], values='Value',
                     color='Category',
                     color_discrete_map={'Úspora vlastní spotřebou': 'green', 'Příjem z prodeje': 'orange'})
    
    fig.update_layout(title='Složení Celkové Úspory (Treemap - Měsíce)')
    return fig

