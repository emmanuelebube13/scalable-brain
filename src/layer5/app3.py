import dash
from dash import dcc, html, dash_table
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output, State
import pandas as pd
import sqlalchemy as sa
import urllib.parse
from dotenv import load_dotenv, find_dotenv
import os
import plotly.express as px
import plotly.graph_objects as go
from oandapyV20 import API
from oandapyV20.endpoints.pricing import PricingStream
from oandapyV20.endpoints.instruments import InstrumentsCandles
from oandapyV20.exceptions import V20Error
from datetime import datetime, timedelta
import threading
from collections import deque

# Load environment variables explicitly
load_dotenv(find_dotenv())

DB_SERVER = os.getenv('DB_SERVER', 'localhost')
DB_USER = os.getenv('DB_USER')
DB_PASS = os.getenv('DB_PASS')
DB_NAME = 'ForexBrainDB'
OANDA_TOKEN = os.getenv('OANDA_API_KEY')
OANDA_ENV = 'practice'
OANDA_ACCOUNT_ID = os.getenv('OANDA_ACCOUNT_ID')

# Database connection
try:
    params = urllib.parse.quote_plus(
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={DB_SERVER};"
        f"DATABASE={DB_NAME};"
        f"UID={DB_USER};"
        f"PWD={DB_PASS}"
    )
    engine = sa.create_engine(f"mssql+pyodbc:///?odbc_connect={params}", connect_args={'timeout': 5})
except Exception as e:
    print(f"Engine creation failed: {e}")
    engine = None

# Main trade query
QUERY_TRADES = """
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
FROM
    Fact_Live_Trades flt
INNER JOIN Dim_Asset da ON flt.Asset_ID = da.Asset_ID
INNER JOIN Dim_Strategy_Registry dsr ON flt.Strategy_ID = dsr.Strategy_ID
ORDER BY flt.Timestamp DESC
"""

def load_trade_data():
    if engine is None:
        return pd.DataFrame()
    try:
        df = pd.read_sql(QUERY_TRADES, engine)
        if not df.empty:
            df['Status'] = df['Is_Approved'].map({1: 'Approved', 0: 'Vetoed'})
            df['Timestamp'] = pd.to_datetime(df['Timestamp'])
        return df
    except Exception as e:
        print(f"🚨 Database Error: {e}")
        return pd.DataFrame()

def fetch_historical_candles(asset_symbol: str, start_time: datetime = None, hours_back: int = 72):
    # Fetch directly from Oanda
    try:
        params = {"count": 200, "granularity": "H1", "price": "M"}
        r = InstrumentsCandles(instrument=asset_symbol, params=params)
        response = api.request(r)
        
        candles = response['candles']
        df = pd.DataFrame([{
            'Timestamp': pd.to_datetime(c['time']).tz_localize(None),
            'Open': float(c['mid']['o']),
            'High': float(c['mid']['h']),
            'Low': float(c['mid']['l']),
            'Close': float(c['mid']['c'])
        } for c in candles])
        return df
    except Exception as e:
        print(f"🚨 Oanda API Replay error: {e}")
        return pd.DataFrame()

# Oanda API Client for streaming
api = API(access_token=OANDA_TOKEN, environment=OANDA_ENV)
ASSETS = ['EUR_USD', 'GBP_USD', 'USD_JPY']
live_prices = {asset: deque(maxlen=100) for asset in ASSETS}

def stream_prices():
    if not OANDA_ACCOUNT_ID:
        print("No Oanda Account ID provided. Skipping live stream.")
        return
    try:
        params = {"instruments": ",".join(ASSETS)}
        r = PricingStream(accountID=OANDA_ACCOUNT_ID, params=params)
        for tick in api.request(r):
            if 'prices' in tick:
                for price in tick['prices']:
                    live_prices[price['instrument']].append({
                        'Asset': price['instrument'],
                        'Bid': float(price['bids'][0]['price']),
                        'Ask': float(price['asks'][0]['price']),
                        'Time': pd.to_datetime(price['time'])
                    })
    except Exception as e:
        print(f"Streaming error: {e}")

threading.Thread(target=stream_prices, daemon=True).start()

# ========================= DASH APP =========================
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.CYBORG], suppress_callback_exceptions=True)
app.title = "Scalable Brain Telemetry"

app.layout = dbc.Container([
    html.H1("Scalable Brain | Live Telemetry", className="text-center mb-4 mt-4", style={"color": "#00FF9F", "fontWeight": "bold"}),
    
    dbc.Row([
        dbc.Col(dcc.Dropdown(id='asset-filter', multi=True, placeholder="Filter by Asset", style={'color': '#000'}), width=4),
        dbc.Col(dcc.Dropdown(id='strategy-filter', multi=True, placeholder="Filter by Strategy", style={'color': '#000'}), width=4),
        dbc.Col(dcc.DatePickerRange(id='date-filter', display_format='YYYY-MM-DD', style={'backgroundColor': '#1E1E1E'}), width=4),
    ], className="mb-4"),
    
    dcc.Interval(id='interval-trades', interval=60000, n_intervals=0),
    dcc.Interval(id='interval-prices', interval=5000, n_intervals=0),

    dbc.Row(id='kpi-row', className="mb-4"),
    
    dbc.Row([
        dbc.Col(dbc.Card(dcc.Graph(id='pie-chart'), body=True, style={"backgroundColor": "#121212"}), md=4),
        dbc.Col(dbc.Card(dcc.Graph(id='scatter-chart'), body=True, style={"backgroundColor": "#121212"}), md=8),
    ], className="mb-4"),

    dbc.Row([
        dbc.Col([
            html.H5("Formal AI Trade Ledger (Click row to plot candlestick replay)", style={"color": "#A0A0A0"}),
            dash_table.DataTable(
                id='data-table',
                page_size=10,
                sort_action='native',
                row_selectable='single',
                style_table={'overflowX': 'auto', 'borderRadius': '5px'},
                style_cell={'textAlign': 'left', 'backgroundColor': '#1E1E1E', 'color': '#E0E0E0'},
                style_header={'backgroundColor': '#0D1117', 'color': '#00FF9F', 'fontWeight': 'bold'},
                style_data_conditional=[
                    {'if': {'filter_query': '{Status} = "Approved"'}, 'color': '#00FF9F'},
                    {'if': {'filter_query': '{Status} = "Vetoed"'}, 'color': '#FF4444'}
                ]
            )
        ])
    ], className="mb-5"),

    dbc.Row([
        dbc.Col([
            html.H5("Real-Time Price Stream", style={"color": "#A0A0A0"}),
            dcc.Dropdown(id='live-asset-select', options=[{'label': a, 'value': a} for a in ASSETS], value=ASSETS[0], style={'color': '#000', 'marginBottom': '10px'}),
            dbc.Card(dcc.Graph(id='live-price-chart', style={'height': '350px'}), body=True, style={"backgroundColor": "#121212"})
        ])
    ], className="mb-5"),

    dbc.Row([
        dbc.Col([
            html.H5(id='replay-title', style={"color": "#A0A0A0"}),
            dbc.Card(dcc.Graph(id='replay-chart', style={'height': '600px'}), body=True, style={"backgroundColor": "#121212"})
        ])
    ])
], fluid=True, style={"backgroundColor": "#0A0A0A", "padding": "20px", "minHeight": "100vh"})

@app.callback(
    [Output('asset-filter', 'options'), Output('strategy-filter', 'options')],
    Input('interval-trades', 'n_intervals')
)
def update_filters(_):
    df = load_trade_data()
    if df.empty: return [], []
    return [{'label': x, 'value': x} for x in sorted(df['Asset_Symbol'].unique())], \
           [{'label': x, 'value': x} for x in sorted(df['Strategy_Name'].unique())]

@app.callback(
    [Output('kpi-row', 'children'), Output('pie-chart', 'figure'), Output('scatter-chart', 'figure'),
     Output('data-table', 'data'), Output('data-table', 'columns')],
    [Input('interval-trades', 'n_intervals'), Input('asset-filter', 'value'),
     Input('strategy-filter', 'value'), Input('date-filter', 'start_date'), Input('date-filter', 'end_date')]
)
def update_main_dashboard(_, assets, strategies, start_date, end_date):
    df = load_trade_data()
    if df.empty:
        return [dbc.Col(html.H4("NO DATABASE CONNECTION OR NO DATA", style={'color': 'red'}))], px.pie(), px.scatter(), [], []

    if assets: df = df[df['Asset_Symbol'].isin(assets)]
    if strategies: df = df[df['Strategy_Name'].isin(strategies)]
    if start_date: df = df[df['Timestamp'] >= pd.to_datetime(start_date)]
    if end_date: df = df[df['Timestamp'] <= pd.to_datetime(end_date)]

    total = len(df)
    approval = df['Is_Approved'].mean() * 100 if total else 0
    avg_conf = df['Confidence_Score'].mean() if total else 0

    kpis = [
        dbc.Col(dbc.Card(dbc.CardBody([html.H6("Total Signals"), html.H3(total, style={"color": "#E0E0E0"})]), style={"backgroundColor": "#121212"}), width=4),
        dbc.Col(dbc.Card(dbc.CardBody([html.H6("AI Approval Rate"), html.H3(f"{approval:.1f}%", style={"color": "#00FF9F"})]), style={"backgroundColor": "#121212"}), width=4),
        dbc.Col(dbc.Card(dbc.CardBody([html.H6("Avg Confidence"), html.H3(f"{avg_conf:.4f}", style={"color": "#64FFDA"})]), style={"backgroundColor": "#121212"}), width=4),
    ]

    pie = px.pie(df, names='Status', title="Approved vs Vetoed", hole=0.5, color='Status', color_discrete_map={'Approved':'#00FF9F','Vetoed':'#FF4444'})
    pie.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="white")

    scatter = px.scatter(df.sort_values('Timestamp'), x='Timestamp', y='Confidence_Score', color='Status', title="AI Confidence Over Time", color_discrete_map={'Approved':'#00FF9F','Vetoed':'#FF4444'})
    scatter.add_hline(y=0.535, line_dash="dash", annotation_text="Threshold 0.535", line_color="gray")
    scatter.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="white", xaxis_gridcolor="#333", yaxis_gridcolor="#333")

    table_df = df.copy()
    table_df['Timestamp'] = table_df['Timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')
    table_df['Confidence_Score'] = table_df['Confidence_Score'].apply(lambda x: f"{x:.4f}")
    
    columns = [{"name": i, "id": i} for i in ['Timestamp','Asset_Symbol','Strategy_Name','Entry_Price','Stop_Loss','Take_Profit','Confidence_Score','Status']]
    return kpis, pie, scatter, table_df.head(50).to_dict('records'), columns

@app.callback(
    Output('live-price-chart', 'figure'),
    [Input('interval-prices', 'n_intervals'), Input('live-asset-select', 'value')]
)
def update_live_price_chart(_, asset):
    prices = list(live_prices.get(asset, []))
    if prices:
        df_prices = pd.DataFrame(prices)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df_prices['Time'], y=df_prices['Bid'], mode='lines', name='Bid', line_color='#FF4444'))
        fig.add_trace(go.Scatter(x=df_prices['Time'], y=df_prices['Ask'], mode='lines', name='Ask', line_color='#00FF9F'))
        fig.update_layout(title=f"Live Streaming: {asset}", template="plotly_dark", height=350, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        return fig
    return go.Figure().update_layout(title=f"Waiting for live stream... {asset}", template="plotly_dark", height=350, paper_bgcolor="rgba(0,0,0,0)")

@app.callback(
    [Output('replay-chart', 'figure'), Output('replay-title', 'children')],
    [Input('data-table', 'selected_rows')],
    State('data-table', 'data')
)
def update_replay_chart(selected_rows, table_data):
    if not selected_rows or not table_data:
        asset = 'GBP_USD'
        candles = fetch_historical_candles(asset)
        fig = go.Figure()
        if not candles.empty:
            fig.add_trace(go.Candlestick(x=candles['Timestamp'], open=candles['Open'], high=candles['High'], low=candles['Low'], close=candles['Close'], name="Price"))
        fig.update_layout(title="Awaiting Trade Selection...", template="plotly_dark", height=600, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", xaxis_rangeslider_visible=False)
        return fig, "Select a trade from the table to validate"

    row = table_data[selected_rows[0]]
    asset = row['Asset_Symbol']
    trade_time = pd.to_datetime(row['Timestamp'])
    entry, sl, tp = float(row['Entry_Price']), float(row['Stop_Loss']), float(row['Take_Profit'])
    status = row.get('Status', 'Unknown')

    candles = fetch_historical_candles(asset)
    fig = go.Figure()
    
    if not candles.empty:
        fig.add_trace(go.Candlestick(x=candles['Timestamp'], open=candles['Open'], high=candles['High'], low=candles['Low'], close=candles['Close'], name="Price"))
        
        # EXACT LOGIC FOR RED OR GREEN ENTRY DOT
        dot_color = '#00FF9F' if status == 'Approved' else '#FF4444'
        fig.add_trace(go.Scatter(x=[trade_time], y=[entry], mode='markers+text', marker=dict(size=18, color=dot_color, symbol='star-diamond', line=dict(width=2, color='white')), text=f"AI {status.upper()}", textposition="top center", name="Entry Signal"))
        fig.add_hline(y=sl, line_dash="dash", line_color="#FF4444", annotation_text="STOP LOSS")
        fig.add_hline(y=tp, line_dash="dash", line_color="#00FF9F", annotation_text="TAKE PROFIT")
        fig.add_vline(x=trade_time, line_dash="dot", line_color="gray", opacity=0.5)

    fig.update_layout(template="plotly_dark", height=600, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", xaxis_rangeslider_visible=False)
    return fig, f"Forward Validation: {asset} | Status: {status}"

if __name__ == '__main__':
    app.run(debug=True, port=8051)