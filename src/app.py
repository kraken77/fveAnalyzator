import streamlit as st
import pandas as pd
import datetime
from data_loader import load_consumption_data, load_production_data
from analyzer import calculate_energy_balance, calculate_financials, calculate_investment_comparison
from visualizer import plot_energy_balance_daily, plot_monthly_stats, plot_investment_comparison, plot_savings_treemap, plot_savings_composition, plot_energy_treemap

def format_cz_number(val):
    """Formats a number to Czech standard: 1 234,56"""
    if isinstance(val, (int, float)):
        return "{:,.2f}".format(val).replace(",", " ").replace(".", ",")
    return val

st.set_page_config(page_title="Antelon Energy - FVE Analýza", layout="wide")


def render_energy_dashboard():
    st.title("🔋 Antelon Energy - Energetická Bilance")

    # Sidebar for inputs
    st.sidebar.header("Parametry FVE")
    kwp = st.sidebar.slider("Výkon FVE (kWp)", min_value=1.0, max_value=50.0, value=10.0, step=0.5)
    battery_capacity = st.sidebar.slider("Kapacita Baterie (kWh)", min_value=0.0, max_value=50.0, value=10.0, step=0.5)

    st.sidebar.header("Spotřeba")
    annual_consumption_mwh = st.sidebar.number_input("Roční spotřeba (MWh)", value=5.0, step=0.1)
    annual_consumption_kwh = annual_consumption_mwh * 1000

    st.sidebar.header("Ceny Energie (CZK/kWh)")
    price_power = st.sidebar.number_input("Cena silové elektřiny", value=3.0)
    price_distribution = st.sidebar.number_input("Cena distribuce", value=2.0)
    price_buy = price_power + price_distribution
    st.sidebar.info(f"Celková nákupní cena: {format_cz_number(price_buy)} Kč/kWh")
    
    price_sell = st.sidebar.number_input("Výkupní cena", value=2.0)

    # Load Data
    with st.spinner('Načítám a počítám data...'):
        consumption_df = load_consumption_data(target_annual_kwh=annual_consumption_kwh)
        production_df = load_production_data(kwp=kwp)
        
        # Analysis
        result_df = calculate_energy_balance(consumption_df, production_df, battery_capacity_kwh=battery_capacity)
        financials = calculate_financials(result_df, electricity_price_buy=price_buy, electricity_price_sell=price_sell)

        # Save savings to session state for the other page
        st.session_state['annual_savings'] = financials['savings_czk']
        
        # Calculate Metrics
        total_consumption = result_df['consumption_kWh'].sum()
        total_production = result_df['production_kWh'].sum()
        self_consumption = total_production - financials['total_export_kWh']
        
        cost_total_consumption = total_consumption * price_buy
        cost_import = financials['total_import_kWh'] * price_buy
        revenue_export = financials['total_export_kWh'] * price_sell
        savings_self_consumption = self_consumption * price_buy

    # Dashboard
    st.subheader("Finanční Bilance")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Roční Úspora", f"{format_cz_number(financials['savings_czk'])} Kč")
    with col2:
        st.metric("Náklady bez FVE", f"{format_cz_number(financials['cost_without_pv_czk'])} Kč")
    with col3:
        st.metric("Náklady s FVE", f"{format_cz_number(financials['cost_with_pv_czk'])} Kč")
            
    st.subheader("Energetická Bilance (kWh)")
    col_e1, col_e2, col_e3, col_e4 = st.columns(4)
    
    with col_e1:
        st.metric("Celková Spotřeba", f"{format_cz_number(total_consumption)} kWh")
    with col_e2:
        st.metric("Nákup ze sítě", f"{format_cz_number(financials['total_import_kWh'])} kWh")
    with col_e3:
        st.metric("Prodej do sítě", f"{format_cz_number(financials['total_export_kWh'])} kWh")
    with col_e4:
        st.metric("Vlastní spotřeba (Úspora)", f"{format_cz_number(self_consumption)} kWh")

    st.subheader("Ekonomická Bilance (CZK)")
    col_c1, col_c2, col_c3, col_c4 = st.columns(4)
    
    with col_c1:
        st.metric("Náklady na spotřebu (teoretické)", f"{format_cz_number(cost_total_consumption)} Kč")
    with col_c2:
        st.metric("Náklady na nákup", f"{format_cz_number(cost_import)} Kč")
    with col_c3:
        st.metric("Příjem z prodeje", f"{format_cz_number(revenue_export)} Kč")
    with col_c4:
        st.metric("Úspora vlastní spotřebou", f"{format_cz_number(savings_self_consumption)} Kč")

    st.markdown("---")
    
    # Savings Visualization
    st.subheader("Vizualizace Úspor")
    col_v1, col_v2 = st.columns(2)
    
    with col_v1:
        st.plotly_chart(plot_savings_composition(savings_self_consumption, revenue_export), use_container_width=True)
    with col_v2:
        st.plotly_chart(plot_savings_treemap(result_df, price_buy, price_sell), use_container_width=True)
    st.markdown("---")
    
    # Energy Visualization
    st.subheader("Vizualizace Energií (kWh)")
    col_e_v1, col_e_v2 = st.columns(2)
    
    with col_e_v1:
        st.plotly_chart(plot_savings_composition(self_consumption, financials['total_export_kWh'], labels=['Vlastní spotřeba', 'Export do sítě'], unit="kWh"), use_container_width=True)
    with col_e_v2:
        st.plotly_chart(plot_energy_treemap(result_df), use_container_width=True)
    st.markdown("---")

    # Plots
    st.subheader("Měsíční Přehled")
    st.plotly_chart(plot_monthly_stats(result_df), use_container_width=True)

    st.subheader("Data")
    
    # Translate and Format Data Table
    display_df = result_df.head(100).copy()
    # Ensure datetime is formatted nicely
    display_df['datetime'] = display_df['datetime'].dt.strftime('%d.%m.%Y %H:%M')
    
    # Rename columns
    column_mapping = {
        'datetime': 'Datum a čas',
        'consumption_kWh': 'Spotřeba',
        'production_kWh': 'Výroba',
        'grid_import_kWh': 'Nákup ze sítě',
        'grid_export_kWh': 'Prodej do sítě',
        'battery_charge_kWh': 'Nabíjení baterie',
        'battery_discharge_kWh': 'Vybíjení baterie',
        'battery_soc_kWh': 'Stav baterie'
    }
    display_df = display_df.rename(columns=column_mapping)
    
    # Format numbers with kWh
    format_dict = {col: lambda x: f"{format_cz_number(x)} kWh" for col in display_df.columns if col != 'Datum a čas'}
    
    st.dataframe(display_df.style.format(format_dict))

    st.markdown("---")

    st.subheader("Detailní Denní Průběh")
    selected_date = st.date_input("Vyberte den", datetime.date(2024, 6, 15))
    st.plotly_chart(plot_energy_balance_daily(result_df, selected_date), use_container_width=True)

def render_economic_dashboard():
    st.title("💰 Antelon Energy - Ekonomika a Investice")
    
    if 'annual_savings' not in st.session_state:
        st.warning("Nejprve prosím navštivte stránku 'Energetická Bilance' pro výpočet úspor.")
        annual_savings = st.number_input("Nebo zadejte roční úsporu ručně (CZK)", value=30000.0)
    else:
        annual_savings = st.session_state['annual_savings']
        st.info(f"Použita vypočtená roční úspora: {format_cz_number(annual_savings)} Kč")

    st.sidebar.header("Investiční Parametry")
    investment_cost = st.sidebar.number_input("Pořizovací cena FVE (CZK)", value=350000.0, step=10000.0)
    years = st.sidebar.slider("Horizont (roky)", 5, 30, 20)
    
    st.sidebar.header("Tržní Parametry")
    sp500_return = st.sidebar.slider("Očekávaný výnos S&P 500 (%)", 0.0, 15.0, 8.0, 0.1)
    inflation = st.sidebar.slider("Inflace / Růst cen energie (%)", 0.0, 10.0, 3.0, 0.1)

    # Calculation
    df = calculate_investment_comparison(
        initial_investment_czk=investment_cost,
        annual_savings_czk=annual_savings,
        years=years,
        sp500_return_pct=sp500_return,
        inflation_pct=inflation
    )
    
    # Metrics
    payback_years = df[df['PV_Cumulative_CashFlow'] >= 0]['Year'].min()
    if pd.isna(payback_years):
        payback_str = "> " + str(years)
    else:
        payback_str = str(payback_years)
        
    final_pv_gain = df['PV_Cumulative_CashFlow'].iloc[-1]
    final_pv_reinvest_gain = df['PV_Reinvest_Net_Result'].iloc[-1]
    final_sp500_net = df['SP500_Net_Result'].iloc[-1]
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Návratnost FVE (roky)", payback_str)
    with col2:
        st.metric(f"Zisk FVE po {years} letech", f"{format_cz_number(final_pv_gain)} Kč")
    with col3:
        st.metric(f"Zisk FVE + Reinvestice", f"{format_cz_number(final_pv_reinvest_gain)} Kč", delta=f"{format_cz_number(final_pv_reinvest_gain - final_pv_gain)} boost")
    with col4:
        st.metric(f"Zisk S&P 500 (Netto)", f"{format_cz_number(final_sp500_net)} Kč", delta=f"{format_cz_number(final_sp500_net - final_pv_reinvest_gain)} vs Reinvest")


    st.plotly_chart(plot_investment_comparison(df), use_container_width=True)
    
    # Translate and Format Investment Table
    display_inv_df = df.copy()
    
    inv_col_mapping = {
        'Year': 'Rok',
        'PV_Cumulative_CashFlow': 'FVE Cashflow',
        'PV_Reinvest_Net_Result': 'FVE + Reinvestice',
        'SP500_Gross_Gain': 'S&P 500 Hrubý zisk',
        'SP500_Net_Result': 'S&P 500 Čistý výsledek',
        'SP500_Total_Value': 'S&P 500 Celková hodnota'
    }
    display_inv_df = display_inv_df.rename(columns=inv_col_mapping)
    
    inv_format_dict = {col: lambda x: f"{format_cz_number(x)} Kč" for col in display_inv_df.columns if col != 'Rok'}
    inv_format_dict['Rok'] = '{:.0f}'
    
    st.dataframe(display_inv_df.style.format(inv_format_dict))

# Main Navigation
page = st.sidebar.radio("Stránka", ["Energetická Bilance", "Ekonomika - Investice"])

if page == "Energetická Bilance":
    render_energy_dashboard()
elif page == "Ekonomika - Investice":
    render_economic_dashboard()

