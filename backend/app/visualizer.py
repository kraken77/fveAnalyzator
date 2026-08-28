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
    fig.add_trace(go.Scatter(x=df['Year'], y=df['PV_Cumulative_DCF'], name='FVE Kumulativní DCF (NPV)', line=dict(color='orange', width=2, dash='dashdot')))
    fig.add_trace(go.Scatter(x=df['Year'], y=df['PV_Reinvest_Net_Result'], name='FVE + Reinvestice úspor do S&P 500', line=dict(color='purple', width=3, dash='dot')))
    fig.add_trace(go.Scatter(x=df['Year'], y=df['SP500_Net_Result'], name='S&P 500 (po zaplacení energií)', line=dict(color='blue', width=3, dash='dash')))
    fig.add_trace(go.Scatter(x=df['Year'], y=df['SP500_Total_Value'], name='S&P 500 (Hrubá hodnota)', line=dict(color='gray', width=1, dash='dot')))
    
    # Add zero line
    fig.add_hline(y=0, line_dash="dot", line_color="gray")

    
    fig.update_layout(
        title='Porovnání vývoje investice v čase',
        xaxis_title='Rok',
        yaxis_title='Hodnota (Kč)',
        hovermode='x unified',
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.3,
            xanchor="center",
            x=0.5
        )
    )
    return fig

def plot_hierarchical_composition(data_dict, unit="Kč"):
    """
    Plots a Sunburst chart showing the composition of savings or energy.
    data_dict example: {
        'labels': ['Vlastní spotřeba', 'Export do sítě'],
        'values': [5000, 2000],
        'subcategories': {
            'Vlastní spotřeba': {
                'labels': ['Bojler', 'Základní chod'],
                'values': [3000, 2000]
            }
        }
    }
    """
    labels = []
    parents = []
    values = []
    
    # Root level
    total_val = sum(data_dict['values'])
    root_label = f"Celkem ({unit})"
    labels.append(root_label)
    parents.append("")
    values.append(total_val)
    
    # Level 1: Main categories
    for i, label in enumerate(data_dict['labels']):
        labels.append(label)
        parents.append(root_label)
        values.append(data_dict['values'][i])
        
        # Level 2: Subcategories (e.g., appliances)
        if 'subcategories' in data_dict and label in data_dict['subcategories']:
            sub = data_dict['subcategories'][label]
            for j, sub_label in enumerate(sub['labels']):
                labels.append(sub_label)
                # Parent must be the EXACT label from level 1
                parents.append(label)
                values.append(sub['values'][j])

    fig = go.Figure(go.Sunburst(
        labels=labels,
        parents=parents,
        values=values,
        branchvalues="total",
        hovertemplate='<b>%{label}</b><br>Hodnota: %{value:.2f} ' + unit + '<br>Podíl: %{percentParent:.1%}',
    ))
    
    fig.update_layout(
        margin=dict(t=30, l=10, r=10, b=10),
        title=f'Složení ({unit})'
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

def plot_energy_treemap(result_df, active_appliances=[]):
    """
    Plots a treemap showing the composition of energy (Self-consumption vs Export vs Import) by Month,
    including appliance breakdown.
    """
    # Ensure datetime is the index for resampling
    temp_df = result_df.set_index('datetime')
    # Resample to monthly sums
    monthly_df = temp_df.resample('ME').sum()
    monthly_df['Month_En'] = monthly_df.index.strftime('%B')
    
    # Czech Month Names Mapping
    czech_months = {
        "January": "Leden", "February": "Únor", "March": "Březen", "April": "Duben",
        "May": "Květen", "June": "Červen", "July": "Červenec", "August": "Srpen",
        "September": "Září", "October": "Říjen", "November": "Listopad", "December": "Prosinec"
    }
    monthly_df['Month'] = monthly_df['Month_En'].map(czech_months)
    
    # Prepare data for Treemap
    data = []
    
    for i, month in enumerate(monthly_df['Month']):
        # 1. Self-consumption (FVE)
        total_sc = monthly_df['production_kWh'].iloc[i] - monthly_df['grid_export_kWh'].iloc[i]
        app_total_sc = 0
        for app in active_appliances:
            col = f'appliance_{app}_self_consumption_kWh'
            if col in monthly_df.columns:
                app_val = monthly_df[col].iloc[i]
                app_total_sc += app_val
                if app_val > 0.05:
                    data.append({
                        'Category': 'Vlastní spotřeba (FVE)',
                        'Subcategory': app,
                        'Month': month,
                        'Value': app_val
                    })
        base_sc = max(0, total_sc - app_total_sc)
        if base_sc > 0.05:
            data.append({
                'Category': 'Vlastní spotřeba (FVE)',
                'Subcategory': 'Základní dům',
                'Month': month,
                'Value': base_sc
            })

        # 2. Grid Import
        total_import = monthly_df['grid_import_kWh'].iloc[i]
        app_total_import = 0
        for app in active_appliances:
            col = f'appliance_{app}_grid_import_kWh'
            if col in monthly_df.columns:
                app_val = monthly_df[col].iloc[i]
                app_total_import += app_val
                if app_val > 0.05:
                    data.append({
                        'Category': 'Odběr ze sítě',
                        'Subcategory': app,
                        'Month': month,
                        'Value': app_val
                    })
        base_import = max(0, total_import - app_total_import)
        if base_import > 0.05:
            data.append({
                'Category': 'Odběr ze sítě',
                'Subcategory': 'Základní dům',
                'Month': month,
                'Value': base_import
            })
            
        # 3. Export
        export_val = monthly_df['grid_export_kWh'].iloc[i]
        if export_val > 0.05:
            data.append({
                'Category': 'Export do sítě',
                'Subcategory': 'Přetoky',
                'Month': month,
                'Value': export_val
            })
            
    df_treemap = pd.DataFrame(data)
    
    if df_treemap.empty:
        return go.Figure().update_layout(title='Složení energie - Žádná data')
    
    fig = px.treemap(df_treemap, path=['Category', 'Subcategory', 'Month'], values='Value',
                     color='Category',
                     color_discrete_map={'Vlastní spotřeba (FVE)': '#27ae60', 'Odběr ze sítě': '#e74c3c', 'Export do sítě': '#f1c40f'})
    
    fig.update_layout(title='Rozložení využití vyrobené energie (kWh)')
    return fig

def plot_savings_treemap(result_df, price_buy=None, price_sell=None, active_appliances=[]):
    """
    Plots a treemap showing the composition of total savings by Category and Subcategory.
    Uses pre-calculated hourly financial columns if available.
    """
    temp_df = result_df.set_index('datetime')
    # Resample to monthly sums
    monthly_df = temp_df.resample('ME').sum()
    monthly_df['Month_En'] = monthly_df.index.strftime('%B')
    
    # Czech Month Names Mapping
    czech_months = {
        "January": "Leden", "February": "Únor", "March": "Březen", "April": "Duben",
        "May": "Květen", "June": "Červen", "July": "Červenec", "August": "Srpen",
        "September": "Září", "October": "Říjen", "November": "Listopad", "December": "Prosinec"
    }
    monthly_df['Month'] = monthly_df['Month_En'].map(czech_months)
    
    data = []
    
    for i, month in enumerate(monthly_df['Month']):
        # 1. Export Revenue
        export_val = 0
        if 'revenue_export_czk' in monthly_df.columns:
            export_val = monthly_df['revenue_export_czk'].iloc[i]
        elif price_sell is not None:
            export_val = monthly_df['grid_export_kWh'].iloc[i] * price_sell
            
        data.append({
            'Category': 'Příjem z prodeje',
            'Subcategory': 'Prodej přebytků',
            'Month': month,
            'Value': export_val
        })
        
        # 2. Self-consumption savings breakdown
        app_total_savings = 0
        for app in active_appliances:
            col_savings = f'appliance_{app}_savings_czk'
            if col_savings in monthly_df.columns:
                app_val = monthly_df[col_savings].iloc[i]
                app_total_savings += app_val
                data.append({
                    'Category': 'Úspora spotřebou',
                    'Subcategory': app,
                    'Month': month,
                    'Value': app_val
                })
        
        # Base savings (Total Self-Cons Savings - Sum of Appliance Savings)
        total_sc_savings = 0
        if 'savings_self_consumption_czk' in monthly_df.columns:
            total_sc_savings = monthly_df['savings_self_consumption_czk'].iloc[i]
        elif price_buy is not None:
            total_sc_kwh = monthly_df['production_kWh'].iloc[i] - monthly_df['grid_export_kWh'].iloc[i]
            total_sc_savings = total_sc_kwh * price_buy
            
        base_savings = max(0, total_sc_savings - app_total_savings)
        data.append({
            'Category': 'Úspora spotřebou',
            'Subcategory': 'Základní spotřeba domu',
            'Month': month,
            'Value': base_savings
        })
        
    df_treemap = pd.DataFrame(data)
    
    if df_treemap.empty or df_treemap['Value'].sum() == 0:
        return go.Figure().update_layout(title='Složení úspor - Žádná data')
    
    df_treemap = df_treemap[df_treemap['Value'] > 0.1]
    
    # Path: Category -> Subcategory -> Month
    fig = px.treemap(df_treemap, path=['Category', 'Subcategory', 'Month'], values='Value',
                     color='Category',
                     color_discrete_map={'Úspora spotřebou': '#27ae60', 'Příjem z prodeje': '#f1c40f'})
    
    fig.update_layout(title='Složení celkové roční úspory (Kč)')
    return fig

