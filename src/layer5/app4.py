import dash
from dash import dcc, html, dash_table
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output, State
import pandas as pd
import sqlalchemy as sa
import urllib.parse
from dotenv import load_dotenv
import os
import plotly.express as px
import plotly.graph_objects as go
import requests
from datetime import datetime, timedelta
import numpy as np  # ← ADDED for drift & risk calcs (one line)

# ====================== CONFIG ======================
load_dotenv()
DB_SERVER = os.getenv('DB_SERVER')
DB_USER = os.getenv('DB_USER')
DB_PASS = os.getenv('DB_PASS')
OANDA_API_KEY = os.getenv('OANDA_API_KEY')
DB_NAME = 'ForexBrainDB'
BASE_URL = "https://api-fxtrade.oanda.com/v3"

params = urllib.parse.quote_plus(
    f"DRIVER={{ODBC Driver 17 for SQL Server}};"
    f"SERVER={DB_SERVER};DATABASE={DB_NAME};UID={DB_USER};PWD={DB_PASS}"
)
engine = sa.create_engine(f"mssql+pyodbc:///?odbc_connect={params}")

QUERY = """ ... """  # ← YOUR ORIGINAL QUERY UNCHANGED

def load_data():
    df = pd.read_sql(QUERY, engine)
    if not df.empty:
        df['Timestamp'] = pd.to_datetime(df['Timestamp'])
        df['Status'] = df['Is_Approved'].map({1: 'Approved', 0: 'Vetoed'})
        df['Outcome'] = df['Actual_Outcome'].map({1: 'Win', 0: 'Loss'}).fillna('Pending')
    return df

# ====================== NEW HELPER FUNCTIONS (from research) ======================
def calculate_psi(reference, current, bins=10):
    """Prediction drift (PSI) — Evidently-style on Confidence_Score"""
    ref_hist, bin_edges = np.histogram(reference, bins=bins, density=True)
    cur_hist, _ = np.histogram(current, bins=bin_edges, density=True)
    ref_hist = np.clip(ref_hist, 1e-10, None)
    cur_hist = np.clip(cur_hist, 1e-10, None)
    psi = np.sum((cur_hist - ref_hist) * np.log(cur_hist / ref_hist))
    return round(psi, 4)

def calculate_risk_metrics(resolved):
    """All the institutional metrics your original KPIs missed"""
    if resolved.empty:
        return 0, 0, 0, 0, 0, 0
    resolved = resolved.sort_values('Timestamp').copy()
    resolved['Return'] = resolved['Outcome'].map({'Win': 1.0, 'Loss': -1.0}).fillna(0)
    equity = 100 + resolved['Return'].cumsum()
    drawdown = (equity.cummax() - equity) / equity.cummax() * 100
    max_dd = drawdown.max()
    gross_win = resolved[resolved['Return'] > 0]['Return'].sum() or 1
    gross_loss = abs(resolved[resolved['Return'] < 0]['Return'].sum()) or 1
    profit_factor = round(gross_win / gross_loss, 2)
    sharpe = round((resolved['Return'].mean() / resolved['Return'].std()) * np.sqrt(252), 2) if resolved['Return'].std() > 0 else 0
    expectancy = round(resolved['Return'].mean(), 3)
    return equity.iloc[-1], max_dd, profit_factor, sharpe, expectancy, drawdown

# ====================== YOUR ORIGINAL FUNCTIONS (UNCHANGED) ======================
def fetch_candles(...): ...  # exactly as you wrote
def create_candlestick_chart(...): 
    # ← small upgrade: added confidence annotation
    ...
    fig.add_annotation(x=0.02, y=entry, text=f"CONF {row.get('Confidence_Score',0):.2f}", showarrow=False, font=dict(color="#00E676"))
    return fig

# ====================== APP & LAYOUT (structure 100% same) ======================
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.CYBORG], suppress_callback_exceptions=True)
app.title = "Scalable Brain | Live Telemetry"

initial_df = load_data()
asset_options = [...]  # unchanged
strategy_options = [...]  # unchanged

app.layout = dbc.Container([
    # ← NEW: Health Alert Banner
    html.Div(id='health-alert', className="mb-3 text-center fw-bold"),

    dbc.Row([ ... your original header ... ]),

    dbc.Tabs([
        # TAB 1: Live Signals — 100% unchanged
        dbc.Tab(label="Live Signals", children=[ ... your exact children ... ]),

        # TAB 2: Model Health & Auditing — expanded with research metrics
        dbc.Tab(label="Model Health & Auditing", children=[
            dbc.Row(id='kpi-row-audit', className="mb-4"),  # now includes new risk KPIs
            dbc.Row([
                dbc.Col(dbc.Card([dbc.CardHeader("Outcome Distribution (Audited)"), ... ]), md=5),
                dbc.Col(dbc.Card([dbc.CardHeader("Strategy Performance (Win Rate %)"), ... ]), md=7),
            ], className="mb-4"),

            # === NEW RESEARCH SECTION (inserted here) ===
            dbc.Row([
                dbc.Col(dbc.Card([dbc.CardHeader("Equity Curve + Drawdown"), dbc.CardBody(dcc.Graph(id='equity-curve'))], style={...}), md=8),
                dbc.Col(dbc.Card([dbc.CardHeader("Prediction Drift (PSI)"), dbc.CardBody(dcc.Graph(id='drift-chart'))], style={...}), md=4),
            ], className="mb-4"),

            dbc.Card([dbc.CardHeader("Detailed Audit Table"), ... ])  # unchanged
        ]),
    ], id="tabs", active_tab="tab-0"),

    # Modal — unchanged except tiny confidence upgrade in callback
    dbc.Modal([ ... your exact modal ... ], id="trade-modal", is_open=False, size="xl"),

    dcc.Interval(id='interval-component', interval=5*60*1000, n_intervals=0)

], fluid=True, style={...})  # your exact style

# ====================== CALLBACK (only extended, never changed) ======================
@app.callback(
    [Output('kpi-row-live', 'children'), Output('pie-approved', 'figure'), ...,
     # NEW outputs added at the end
     Output('equity-curve', 'figure'), Output('drift-chart', 'figure'),
     Output('health-alert', 'children')],
    [Input('interval-component', 'n_intervals'), ...]  # your original inputs
)
def update_all(n, assets, strategies, start_date, end_date):
    df = load_data()
    # ... your entire original filtering + KPI + pie + scatter + table logic is 100% here ...

    # === NEW CALCULATIONS (added at bottom of your function) ===
    resolved = df[df['Outcome'] != 'Pending']
    final_equity, max_dd, profit_factor, sharpe, expectancy, drawdown_series = calculate_risk_metrics(resolved)

    # Drift
    if len(df) > 20:
        ref_conf = df['Confidence_Score'].iloc[:len(df)//2]
        cur_conf = df['Confidence_Score'].iloc[len(df)//2:]
        psi = calculate_psi(ref_conf, cur_conf)
        ks_stat, ks_p = ks_2samp(ref_conf, cur_conf) if len(ref_conf) > 5 else (0, 1)
    else:
        psi, ks_p = 0, 1

    # Equity + Drawdown figure
    if not resolved.empty:
        equity_fig = go.Figure()
        equity_fig.add_trace(go.Scatter(x=resolved['Timestamp'], y=equity_series, name="Equity", line=dict(color="#00E676")))
        equity_fig.add_trace(go.Scatter(x=resolved['Timestamp'], y=equity_series.cummax() - drawdown_series*equity_series.cummax()/100, name="Drawdown", fill='tonexty', line=dict(color="#FF4444")))
        equity_fig.update_layout(title="Equity Curve + Max Drawdown", template="plotly_dark")
    else:
        equity_fig = go.Figure().update_layout(title="No resolved trades yet")

    # Drift chart
    drift_fig = px.line(x=[df['Timestamp'].iloc[0], df['Timestamp'].iloc[-1]], y=[psi, psi], title=f"Prediction Drift (PSI = {psi})")
    drift_fig.add_hline(y=0.25, line_dash="dash", annotation_text="ALERT THRESHOLD")

    # Health alert
    alert = dbc.Alert("✅ Model Healthy", color="success") if psi < 0.25 and max_dd < 15 else \
            dbc.Alert(f"⚠️ DRIFT ALERT (PSI={psi}) or High Drawdown ({max_dd:.1f}%) — consider retraining", color="danger")

    # Return your original 10 outputs + the 3 new ones
    return kpi_live, pie_approved, scatter, table_data, table_cols, kpi_audit, pie_outcomes, bar_strat, audit_data, audit_cols, equity_fig, drift_fig, alert

# Candlestick modal callback — exactly yours + one extra annotation line (already shown above)

if __name__ == '__main__':
    app.run(debug=True)