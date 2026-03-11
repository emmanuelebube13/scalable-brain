import dash
from dash import dcc, html, dash_table
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output
import pandas as pd
import sqlalchemy as sa
import urllib.parse
from dotenv import load_dotenv
import os
import plotly.express as px
from datetime import datetime, timedelta

# Load environment variables
load_dotenv()

DB_SERVER = os.getenv('DB_SERVER')
DB_USER = os.getenv('DB_USER')
DB_PASS = os.getenv('DB_PASS')
DB_NAME = 'ForexBrainDB'

# Database connection
params = urllib.parse.quote_plus(
    f"DRIVER={{ODBC Driver 17 for SQL Server}};"
    f"SERVER={DB_SERVER};"
    f"DATABASE={DB_NAME};"
    f"UID={DB_USER};"
    f"PWD={DB_PASS}"
)
engine = sa.create_engine(f"mssql+pyodbc:///?odbc_connect={params}")

QUERY = """
SELECT 
    flt.Timestamp,
    da.Symbol AS Asset_Symbol,
    dsr.Strategy_Name,
    flt.Signal_Value,
    flt.Entry_Price,
    flt.Stop_Loss,
    flt.Take_Profit,
    flt.Confidence_Score,
    flt.Is_Approved
FROM Fact_Live_Trades flt
INNER JOIN Dim_Asset da ON flt.Asset_ID = da.Asset_ID
INNER JOIN Dim_Strategy_Registry dsr ON flt.Strategy_ID = dsr.Strategy_ID
ORDER BY flt.Timestamp DESC
"""

def load_data():
    df = pd.read_sql(QUERY, engine)
    if not df.empty:
        df['Status'] = df['Is_Approved'].map({1: 'Approved', 0: 'Vetoed'})
        df['Timestamp'] = pd.to_datetime(df['Timestamp'])
    return df

# Initialize Dash app
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.CYBORG], suppress_callback_exceptions=True)
app.title = "Scalable Brain Telemetry"

# Initial Data Load for Dropdown Options
initial_df = load_data()
asset_options = [{'label': i, 'value': i} for i in initial_df['Asset_Symbol'].unique()] if not initial_df.empty else []
strategy_options = [{'label': i, 'value': i} for i in initial_df['Strategy_Name'].unique()] if not initial_df.empty else []

# Layout
app.layout = dbc.Container([
    # Header
    dbc.Row([
        dbc.Col(html.H2("Scalable Brain | Live Telemetry", className="mt-4 mb-3", style={"color": "#E0E0E0", "font-weight": "300", "letter-spacing": "2px"}), width=12)
    ]),

    # --- NEW: FILTERS ROW ---
    dbc.Row([
        dbc.Col(dcc.Dropdown(
            id='asset-filter', options=asset_options, multi=True, placeholder="Filter by Asset",
            style={'color': '#000000'} # Keep text black so it's readable in the white dropdown box
        ), md=4),
        dbc.Col(dcc.Dropdown(
            id='strategy-filter', options=strategy_options, multi=True, placeholder="Filter by Strategy",
            style={'color': '#000000'}
        ), md=4),
        dbc.Col(dcc.DatePickerRange(
            id='date-filter',
            start_date=(datetime.now() - timedelta(days=7)).date(),
            end_date=datetime.now().date(),
            display_format='YYYY-MM-DD',
            style={'backgroundColor': '#1E1E1E'}
        ), md=4),
    ], className="mb-4"),

    dcc.Interval(id='interval-component', interval=5*60*1000, n_intervals=0),

    # KPIs Row
    dbc.Row(id='kpi-row', className="mb-4"),

    # Charts Row
    dbc.Row([
        dbc.Col(dbc.Card(dcc.Graph(id='pie-chart'), body=True, style={"backgroundColor": "#121212", "border": "none"}), md=4),
        dbc.Col(dbc.Card(dcc.Graph(id='scatter-chart'), body=True, style={"backgroundColor": "#121212", "border": "none"}), md=8),
    ], className="mb-4"),

    # Data Table Row
    dbc.Row([
        dbc.Col([
            html.H5("Recent AI Decisions", style={"color": "#A0A0A0", "margin-bottom": "15px"}),
            dash_table.DataTable(
                id='data-table',
                style_table={'overflowX': 'auto', 'borderRadius': '5px'},
                style_cell={'textAlign': 'left', 'backgroundColor': '#1E1E1E', 'color': '#E0E0E0', 'font-family': 'Segoe UI, sans-serif', 'border': '1px solid #333'},
                style_header={'backgroundColor': '#0D1117', 'color': '#8892B0', 'fontWeight': 'bold', 'border': '1px solid #333'},
                page_size=15,
                sort_action='native'
            )
        ], width=12)
    ])
], fluid=True, style={"backgroundColor": "#0A0A0A", "minHeight": "100vh", "padding": "30px"})

# Callback
@app.callback(
    [Output('kpi-row', 'children'),
     Output('pie-chart', 'figure'),
     Output('scatter-chart', 'figure'),
     Output('data-table', 'data'),
     Output('data-table', 'columns'),
     Output('data-table', 'style_data_conditional')],
    [Input('interval-component', 'n_intervals'),
     Input('asset-filter', 'value'),
     Input('strategy-filter', 'value'),
     Input('date-filter', 'start_date'),
     Input('date-filter', 'end_date')]
)
def update_dashboard(n, selected_assets, selected_strategies, start_date, end_date):
    df = load_data()

    if df.empty:
        return [dbc.Col(html.Div("No data available", className="text-white"))], px.pie(), px.scatter(), [], [], []

    # --- APPLY FILTERS ---
    if selected_assets:
        df = df[df['Asset_Symbol'].isin(selected_assets)]
    if selected_strategies:
        df = df[df['Strategy_Name'].isin(selected_strategies)]
    if start_date and end_date:
        df = df[(df['Timestamp'] >= start_date) & (df['Timestamp'] <= pd.to_datetime(end_date) + pd.Timedelta(days=1))]

    if df.empty: # Handle case where filters remove all data
        return [dbc.Col(html.Div("No data matches current filters.", className="text-white"))], px.pie(), px.scatter(), [], [], []

    # Calculations
    total_signals = len(df)
    approval_rate = (df['Is_Approved'].mean() * 100)
    avg_confidence = df['Confidence_Score'].mean()

    # KPI Cards
    kpi_cards = [
        dbc.Col(dbc.Card(dbc.CardBody([html.H6("TOTAL SIGNALS ANALYZED", style={"color": "#8892B0", "fontSize": "12px", "fontWeight": "bold"}), html.H3(f"{total_signals:,}", style={"color": "#E0E0E0"})]), style={"backgroundColor": "#121212", "border": "1px solid #222"}), width=4),
        dbc.Col(dbc.Card(dbc.CardBody([html.H6("AI APPROVAL RATE", style={"color": "#8892B0", "fontSize": "12px", "fontWeight": "bold"}), html.H3(f"{approval_rate:.1f}%", style={"color": "#00E676" if approval_rate > 0 else "#FF5252"})]), style={"backgroundColor": "#121212", "border": "1px solid #222"}), width=4),
        dbc.Col(dbc.Card(dbc.CardBody([html.H6("AVERAGE CONFIDENCE", style={"color": "#8892B0", "fontSize": "12px", "fontWeight": "bold"}), html.H3(f"{avg_confidence:.4f}", style={"color": "#64FFDA"})]), style={"backgroundColor": "#121212", "border": "1px solid #222"}), width=4),
    ]

    # Pie Chart
    pie_fig = px.pie(df, names='Status', hole=0.6, title="Trade Distribution", color='Status', color_discrete_map={'Approved': '#00E676', 'Vetoed': '#FF5252'})
    pie_fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="#A0A0A0", margin=dict(t=40, b=10, l=10, r=10))

    # Scatter Plot
    scatter_fig = px.scatter(df, x='Timestamp', y='Confidence_Score', color='Status', color_discrete_map={'Approved': '#00E676', 'Vetoed': '#FF5252'}, title="AI Confidence Over Time")
    scatter_fig.add_hline(y=0.535, line_dash="dash", line_color="#8892B0", annotation_text="Threshold (0.535)", annotation_font_color="#8892B0")
    scatter_fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="#A0A0A0", xaxis_gridcolor="#222", yaxis_gridcolor="#222", margin=dict(t=40, b=10, l=10, r=10))

    # Data Table
    table_df = df.head(50)[['Timestamp', 'Asset_Symbol', 'Strategy_Name', 'Entry_Price', 'Stop_Loss', 'Take_Profit', 'Confidence_Score', 'Status']]
    table_df['Confidence_Score'] = table_df['Confidence_Score'].apply(lambda x: f"{x:.4f}")
    table_df['Timestamp'] = table_df['Timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')
    columns = [{"name": i.replace("_", " "), "id": i} for i in table_df.columns]
    data = table_df.to_dict('records')

    # Conditional Styling
    style_data_conditional = [
        {'if': {'filter_query': '{Status} = "Approved"'}, 'backgroundColor': 'rgba(0, 230, 118, 0.1)', 'color': '#00E676'},
        {'if': {'filter_query': '{Status} = "Vetoed"'}, 'backgroundColor': 'rgba(255, 82, 82, 0.05)', 'color': '#FF8A80'}
    ]

    return kpi_cards, pie_fig, scatter_fig, data, columns, style_data_conditional

if __name__ == '__main__':
    app.run(debug=True)