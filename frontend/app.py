"""
Live Trade Telemetry - Forex Trading Signals Dashboard
Standalone Dash Application
"""
import plotly.graph_objects as go
import os
import io
import urllib.parse
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import plotly.subplots as sp
from numpy import polyfit, poly1d  # For trendlines
import dash
import dash_ag_grid as dag
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.graph_objects as go
import requests
import sqlalchemy as sa
from dash import dcc, html, Input, Output, State, ALL
from dash import callback_context
from dotenv import load_dotenv

# Resolve project paths from the new frontend/ location.
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# STORY 7 – LIVE PULSE ANIMATION (CSS)
app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.DARKLY],
    suppress_callback_exceptions=True,
    assets_folder=os.path.join(PROJECT_ROOT, "assets")
)
app.index_string = f'''
<!DOCTYPE html>
<html>
    <head>
        {{%metas%}}
        <title>{{%title%}}</title>
        {{%favicon%}}
        {{%css%}}
        <link id="theme-light" rel="stylesheet" href="{dbc.themes.FLATLY}" disabled>
        <style>
            :root {{
                --app-bg: #0a0a0a;
                --card-bg: #141414;
                --border: #1f1f1f;
                --text: #e0e0e0;
                --text-secondary: #888888;
                --accent: #2d2d2d;
                --hover: #1a1a1a;
                --brand-accent: #00b4d8;
                --brand-soft: #a0aec0;
                --brand-panel-bg: #0d1520;
                --brand-panel-border: #1a3050;
                --brand-panel-shadow: 0 2px 10px rgba(0,180,216,0.12);
            }}

            body[data-theme="light"] {{
                --app-bg: #f8fafc;
                --card-bg: #ffffff;
                --border: #dbe3ef;
                --text: #1f2937;
                --text-secondary: #5b6474;
                --accent: #eef3f9;
                --hover: #f2f6fc;
                --brand-accent: #0369a1;
                --brand-soft: #475569;
                --brand-panel-bg: #f3f8ff;
                --brand-panel-border: #bfd4ef;
                --brand-panel-shadow: 0 2px 10px rgba(2, 132, 199, 0.18);
            }}

            body {{
                background-color: var(--app-bg);
                color: var(--text);
            }}

            #main-container {{
                background-color: var(--app-bg) !important;
                color: var(--text) !important;
            }}

            .card {{
                background-color: var(--card-bg) !important;
                border-color: var(--border) !important;
                color: var(--text) !important;
            }}

            .modal-content,
            .modal-header,
            .modal-body,
            .modal-footer {{
                background-color: var(--card-bg) !important;
                color: var(--text) !important;
                border-color: var(--border) !important;
            }}

            .ag-theme-alpine-dark,
            .ag-theme-alpine-dark .ag-root-wrapper,
            .ag-theme-alpine-dark .ag-header,
            .ag-theme-alpine-dark .ag-row {{
                --ag-background-color: var(--card-bg) !important;
                --ag-header-background-color: var(--accent) !important;
                --ag-odd-row-background-color: var(--card-bg) !important;
                --ag-foreground-color: var(--text) !important;
                --ag-header-foreground-color: var(--text-secondary) !important;
                --ag-border-color: var(--border) !important;
                --ag-row-hover-color: var(--hover) !important;
            }}

            .form-control,
            .Select-control,
            .DateInput_input,
            .DateRangePickerInput,
            input,
            textarea {{
                background-color: var(--card-bg) !important;
                color: var(--text) !important;
                border-color: var(--border) !important;
            }}

            .table-dark {{
                --bs-table-bg: var(--card-bg);
                --bs-table-striped-bg: var(--accent);
                --bs-table-color: var(--text);
                --bs-table-border-color: var(--border);
            }}

            @keyframes pulse {{
                0% {{ opacity: 1; }}
                50% {{ opacity: 0.3; }}
                100% {{ opacity: 1; }}
            }}
            .theme-toggle-btn {{
                background: transparent;
                border: 1px solid var(--border);
                border-radius: 20px;
                padding: 5px 14px;
                cursor: pointer;
                font-size: 0.85rem;
                letter-spacing: 0.5px;
                transition: all 0.2s ease;
                color: var(--text-secondary);
            }}
            .theme-toggle-btn:hover {{
                border-color: var(--brand-accent);
                color: var(--brand-accent);
            }}
        </style>
    </head>
    <body data-theme="dark">
        {{%app_entry%}}
        <footer>{{%config%}}{{%scripts%}}{{%renderer%}}</footer>
    </body>
</html>
'''

# =============================================================================
# CONFIGURATION & DATABASE CONNECTION
# =============================================================================

load_dotenv()
DB_SERVER = os.getenv('DB_SERVER')
DB_USER = os.getenv('DB_USER')
DB_PASS = os.getenv('DB_PASS')
OANDA_TOKEN = os.getenv('OANDA_API_KEY')
OANDA_ACCOUNT = os.getenv('OANDA_ACCOUNT_ID_DEMO')

params = urllib.parse.quote_plus(
    f"DRIVER={{ODBC Driver 17 for SQL Server}};"
    f"SERVER={DB_SERVER};DATABASE=ForexBrainDB;UID={DB_USER};PWD={DB_PASS}"
)
engine = sa.create_engine(f"mssql+pyodbc:///?odbc_connect={params}")

# =============================================================================
# SQL QUERIES
# =============================================================================

QUERY = """ 
SELECT flt.Timestamp, da.Symbol AS Asset_Symbol, dsr.Strategy_Name, flt.Signal_Value, 
       flt.Entry_Price, flt.Stop_Loss, flt.Take_Profit, flt.Confidence_Score, 
       flt.Is_Approved, flt.Actual_Outcome 
FROM Fact_Live_Trades flt 
INNER JOIN Dim_Asset da ON flt.Asset_ID = da.Asset_ID 
INNER JOIN Dim_Strategy_Registry dsr ON flt.Strategy_ID = dsr.Strategy_ID 
ORDER BY flt.Timestamp DESC 
"""

# =============================================================================
# DATA LOADING FUNCTIONS
# =============================================================================

# =============================================================================
# DATA LOADING FUNCTIONS
# =============================================================================

def load_data():
    """Load and process data from SQL Server."""
    try:
        df = pd.read_sql(QUERY, engine)
        df['Timestamp'] = pd.to_datetime(df['Timestamp'])
        
        # Convert decimal probability to percentage for UI
        if 'Confidence_Score' in df.columns:
            df['Confidence_Score'] = df['Confidence_Score'] * 100
            
        # Safely map Status 
        df['Status'] = df['Is_Approved'].apply(
            lambda x: 'Approved' if str(x).strip() in ['1', '1.0', 'True', 'true'] else 'Vetoed'
        )
        
        # BULLETPROOF OUTCOME MAPPING (Handles NaN, 1.0, 0.0)
        def map_outcome(x):
            if pd.isna(x):  # Catch SQL NULLs (which Pandas turns into NaN)
                return 'Pending'
            
            val_str = str(x).strip()
            if val_str in ['1', '1.0', 'True', 'true']:
                return 'Win'
            elif val_str in ['0', '0.0', 'False', 'false']:
                return 'Loss'
            return 'Pending'
            
        df['Outcome'] = df['Actual_Outcome'].apply(map_outcome)
        
        return df
    except Exception as e:
        print(f"Database error: {e}")
        return pd.DataFrame()

# =============================================================================
# OANDA API FUNCTIONS
# =============================================================================

# =============================================================================
# OANDA API FUNCTIONS
# =============================================================================

def fetch_candles(symbol: str, trade_time: datetime):
    """
    Fetch 1-minute candlestick data from OANDA.
    Fetches a 48-hour window (24h before, 24h after) to keep under the 5000 limit.
    """
    if not OANDA_TOKEN:
        print("Error: OANDA_TOKEN is missing from environment variables.")
        return None
    
    # Format symbol for OANDA (ensure it has an underscore, e.g., EURUSD -> EUR_USD)
    oanda_symbol = symbol.replace('/', '_')
    if '_' not in oanda_symbol and len(oanda_symbol) == 6:
        oanda_symbol = f"{oanda_symbol[:3]}_{oanda_symbol[3:]}"
    
    # Calculate time range
    window_start = trade_time - timedelta(hours=24)
    window_end = trade_time + timedelta(hours=24)
    
    # --- THE FIX FOR "TIME IS IN THE FUTURE" ---
    # Cap the requests to the current actual UTC time so OANDA doesn't reject mock future dates
    current_utc = datetime.utcnow()
    if window_start > current_utc:
        # Trade is in the future: fetch the most recent 48 hours of real data instead
        window_start = current_utc - timedelta(hours=48)
        window_end = current_utc
    elif window_end > current_utc:
        # Trade just happened: cap the end window to right now
        window_end = current_utc
    
    from_time = window_start.strftime('%Y-%m-%dT%H:%M:%S.000000Z')
    to_time = window_end.strftime('%Y-%m-%dT%H:%M:%S.000000Z')
    
    url = f"https://api-fxpractice.oanda.com/v3/instruments/{oanda_symbol}/candles"
    
    headers = {
        "Authorization": f"Bearer {OANDA_TOKEN}",
        "Content-Type": "application/json"
    }
    params = {
        "from": from_time,
        "to": to_time,
        "granularity": "M1",
        "price": "M"  
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status() 
        data = response.json()
        
        if 'candles' not in data or not data['candles']:
            print(f"Warning: OANDA returned no candle data for {oanda_symbol} between {from_time} and {to_time}")
            return None
            
        candles = []
        for candle in data['candles']:
            if candle['complete']:
                candles.append({
                    'time': pd.to_datetime(candle['time']),
                    'open': float(candle['mid']['o']),
                    'high': float(candle['mid']['h']),
                    'low': float(candle['mid']['l']),
                    'close': float(candle['mid']['c']),
                    'volume': int(candle['volume'])
                })
        
        return pd.DataFrame(candles)
    except requests.exceptions.HTTPError as e:
        print(f"OANDA HTTP Error: {e.response.status_code} - {e.response.text}")
        return None
    except Exception as e:
        print(f"OANDA API error: {e}")
        return None

# =============================================================================
# CHART CREATION
# =============================================================================


def calculate_sma(data, window):
    """Calculate Simple Moving Average."""
    return data['close'].rolling(window=window).mean()

def calculate_ema(data, window):
    """Calculate Exponential Moving Average."""
    return data['close'].ewm(span=window, adjust=False).mean()

def calculate_rsi(data, window=14):
    """Calculate Relative Strength Index."""
    delta = data['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_bollinger_bands(data, window=20, num_std=2):
    """Calculate Bollinger Bands."""
    sma = data['close'].rolling(window=window).mean()
    std = data['close'].rolling(window=window).std()
    upper_band = sma + (std * num_std)
    lower_band = sma - (std * num_std)
    return upper_band, sma, lower_band
#======================================================================================


import plotly.subplots as sp

def create_enhanced_chart(candles, entry, sl, tp, status, outcome, confidence, 
                          show_sma=True, sma_periods=[20, 50], 
                          show_ema=True, ema_periods=[12, 26],
                          show_rsi=True, rsi_period=14,
                          show_bb=True, bb_period=20,
                          show_trendlines=True,
                          theme='dark'):
    """
    Create an enhanced candlestick chart with technical indicators.
    Uses subplots for RSI and main chart area.
    """
    chart_theme = get_plotly_theme(theme)

    if candles is None or candles.empty:
        fig = go.Figure()
        fig.update_layout(
            template=chart_theme['template'],
            paper_bgcolor=chart_theme['paper_bgcolor'],
            plot_bgcolor=chart_theme['plot_bgcolor'],
            font=dict(color=chart_theme['font_color'])
        )
        fig.add_annotation(
            text="No candle data available from OANDA.<br>Check your Python terminal for API errors.",
            x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False, 
            font=dict(color=chart_theme['warn_color'], size=16)
        )
        return fig
    
    # Calculate indicators
    indicators = {}
    
    # Moving Averages
    if show_sma:
        for period in sma_periods:
            indicators[f'SMA_{period}'] = calculate_sma(candles, period)
    if show_ema:
        for period in ema_periods:
            indicators[f'EMA_{period}'] = calculate_ema(candles, period)
    
    # Bollinger Bands
    if show_bb:
        bb_upper, bb_middle, bb_lower = calculate_bollinger_bands(candles, bb_period)
        indicators['BB_Upper'] = bb_upper
        indicators['BB_Middle'] = bb_middle
        indicators['BB_Lower'] = bb_lower
    
    # RSI
    rsi_values = None
    if show_rsi:
        rsi_values = calculate_rsi(candles, rsi_period)
    
    # Determine subplot structure
    if show_rsi:
        fig = sp.make_subplots(
            rows=2, cols=1, 
            shared_xaxes=True,
            vertical_spacing=0.05,
            row_heights=[0.75, 0.25],
            subplot_titles=(f'Trade Replay - {status}', 'RSI')
        )
        rsi_row = 2
        main_row = 1
    else:
        fig = go.Figure()
        main_row = 1
    
    # Color scheme
    colors = {
        'sma': ['#FFD700', '#FF6B6B'],  # Gold, Coral
        'ema': ['#00CED1', '#FF1493'],  # DarkTurquoise, DeepPink
        'bb': '#9B59B6',  # Purple
        'entry': chart_theme['info'],
        'sl': chart_theme['danger'],
        'tp': chart_theme['success'],
        'win': chart_theme['success'],
        'loss': chart_theme['danger'],
        'pending': chart_theme['info']
    }
    
    # Add Candlesticks
    candlestick_trace = go.Candlestick(
        x=candles['time'],
        open=candles['open'],
        high=candles['high'],
        low=candles['low'],
        close=candles['close'],
        name='Price',
        increasing_line_color=chart_theme['success'],
        decreasing_line_color=chart_theme['danger'],
        increasing_fillcolor=chart_theme['success'],
        decreasing_fillcolor=chart_theme['danger']
    )
    
    if show_rsi:
        fig.add_trace(candlestick_trace, row=main_row, col=1)
    else:
        fig.add_trace(candlestick_trace)
    
    # Add Moving Averages
    if show_sma:
        for i, period in enumerate(sma_periods):
            sma_data = indicators[f'SMA_{period}'].dropna()
            if not sma_data.empty:
                trace = go.Scatter(
                    x=candles['time'].loc[sma_data.index],
                    y=sma_data,
                    mode='lines',
                    name=f'SMA {period}',
                    line=dict(color=colors['sma'][i % len(colors['sma'])], width=1.5),
                    opacity=0.8
                )
                fig.add_trace(trace, row=main_row, col=1) if show_rsi else fig.add_trace(trace)
    
    if show_ema:
        for i, period in enumerate(ema_periods):
            ema_data = indicators[f'EMA_{period}'].dropna()
            if not ema_data.empty:
                trace = go.Scatter(
                    x=candles['time'].loc[ema_data.index],
                    y=ema_data,
                    mode='lines',
                    name=f'EMA {period}',
                    line=dict(color=colors['ema'][i % len(colors['ema'])], width=1.5, dash='dash'),
                    opacity=0.8
                )
                fig.add_trace(trace, row=main_row, col=1) if show_rsi else fig.add_trace(trace)
    
    # Add Bollinger Bands
    if show_bb:
        for band, label, dash in [('BB_Upper', 'Upper', None), ('BB_Lower', 'Lower', None), ('BB_Middle', 'Middle', 'dot')]:
            bb_data = indicators[band].dropna()
            if not bb_data.empty:
                trace = go.Scatter(
                    x=candles['time'].loc[bb_data.index],
                    y=bb_data,
                    mode='lines',
                    name=f'BB {label}',
                    line=dict(color=colors['bb'], width=1, dash=dash),
                    opacity=0.6,
                    showlegend=(label == 'Upper')
                )
                fig.add_trace(trace, row=main_row, col=1) if show_rsi else fig.add_trace(trace)
    
    # Add RSI
    if show_rsi and rsi_values is not None:
        rsi_clean = rsi_values.dropna()
        fig.add_trace(
            go.Scatter(
                x=candles['time'].loc[rsi_clean.index],
                y=rsi_clean,
                mode='lines',
                name=f'RSI {rsi_period}',
                line=dict(color='#E74C3C', width=1.5),
                yaxis='y2'
            ),
            row=rsi_row, col=1
        )
        # Add RSI levels
        for level, color in [(70, chart_theme['danger']), (30, chart_theme['success']), (50, chart_theme['neutral'])]:
            fig.add_hline(y=level, line_dash="dash", line_color=color, 
                         line_width=1, opacity=0.5, row=rsi_row, col=1)
    
    # Add Trade Levels with Enhanced Visuals
    # Entry Price - Star marker
    entry_time = candles['time'].iloc[len(candles) // 2]
    
    # Determine trade direction for color coding
    is_long = tp > entry if tp and entry else True
    
    # Add shaded regions for SL/TP zones
    if is_long:
        # Long trade: SL below, TP above
        fig.add_hrect(
            y0=sl, y1=entry,
            fillcolor="rgba(255, 77, 77, 0.1)",
            line_width=0,
            annotation_text="Risk Zone",
            annotation_position="right",
            row=main_row, col=1
        )
        fig.add_hrect(
            y0=entry, y1=tp,
            fillcolor="rgba(0, 196, 140, 0.1)",
            line_width=0,
            annotation_text="Reward Zone",
            annotation_position="right",
            row=main_row, col=1
        )
    else:
        # Short trade: SL above, TP below
        fig.add_hrect(
            y0=entry, y1=sl,
            fillcolor="rgba(255, 77, 77, 0.1)",
            line_width=0,
            annotation_text="Risk Zone",
            annotation_position="right",
            row=main_row, col=1
        )
        fig.add_hrect(
            y0=tp, y1=entry,
            fillcolor="rgba(0, 196, 140, 0.1)",
            line_width=0,
            annotation_text="Reward Zone",
            annotation_position="right",
            row=main_row, col=1
        )
    
    # Entry line with star
    fig.add_hline(
        y=entry,
        line_dash="solid",
        line_color=colors['entry'],
        line_width=3,
        annotation_text=f"ENTRY: {entry:.5f}",
        annotation_position="right",
        annotation_font_color=colors['entry'],
        annotation_font_size=12,
        annotation_font_family="Segoe UI",
        row=main_row, col=1
    )
    
    fig.add_trace(
        go.Scatter(
            x=[entry_time],
            y=[entry],
            mode='markers+text',
            marker=dict(
                symbol='star',
                size=24,
                color=colors['entry'],
                line=dict(width=2, color='white')
            ),
            text=[f"AI Entry<br>Conf: {confidence:.1f}%"],
            textposition="top center",
            textfont=dict(size=10, color=colors['entry']),
            name='Entry',
            showlegend=False
        ),
        row=main_row, col=1
    ) if show_rsi else fig.add_trace(
        go.Scatter(
            x=[entry_time],
            y=[entry],
            mode='markers+text',
            marker=dict(
                symbol='star',
                size=24,
                color=colors['entry'],
                line=dict(width=2, color='white')
            ),
            text=[f"AI Entry<br>Conf: {confidence:.1f}%"],
            textposition="top center",
            textfont=dict(size=10, color=colors['entry']),
            name='Entry',
            showlegend=False
        )
    )
    
    # Stop Loss line
    fig.add_hline(
        y=sl,
        line_dash="dash",
        line_color=colors['sl'],
        line_width=2,
        annotation_text=f"SL: {sl:.5f}",
        annotation_position="right",
        annotation_font_color=colors['sl'],
        annotation_font_size=11,
        row=main_row, col=1
    )
    
    # Take Profit line
    fig.add_hline(
        y=tp,
        line_dash="dash",
        line_color=colors['tp'],
        line_width=2,
        annotation_text=f"TP: {tp:.5f}",
        annotation_position="right",
        annotation_font_color=colors['tp'],
        annotation_font_size=11,
        row=main_row, col=1
    )
    
    # Add Trendlines (if enabled - simple trend detection)
    if show_trendlines and len(candles) > 20:
        # Simple linear regression for trend
        from numpy import polyfit, poly1d
        x_vals = range(len(candles))
        y_vals = candles['close'].values
        coeffs = polyfit(x_vals, y_vals, 1)
        trend_line = poly1d(coeffs)
        trend_y = trend_line(x_vals)
        
        trend_color = '#F39C12' if coeffs[0] > 0 else '#E74C3C'
        trend_trace = go.Scatter(
            x=candles['time'],
            y=trend_y,
            mode='lines',
            name='Trend',
            line=dict(color=trend_color, width=2, dash='dashdot'),
            opacity=0.7
        )
        fig.add_trace(trend_trace, row=main_row, col=1) if show_rsi else fig.add_trace(trend_trace)
    
    # Add Outcome Badge at top left
    outcome_color = colors.get(outcome.lower(), colors['pending']) if outcome else colors['pending']
    outcome_text = outcome if outcome else 'PENDING'
    
    # Layout configuration
    layout_updates = {
        'template': chart_theme['template'],
        'paper_bgcolor': chart_theme['paper_bgcolor'],
        'plot_bgcolor': chart_theme['plot_bgcolor'],
        'font': dict(color=chart_theme['font_color'], family='Segoe UI, Arial, sans-serif'),
        'title': dict(
            text=f"<b>Trade Replay</b> | Status: {status} | Outcome: <span style='color:{outcome_color}'>{outcome_text}</span>",
            font=dict(size=16, color=chart_theme['font_color']),
            x=0.5
        ),
        'showlegend': True,
        'legend': dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            bgcolor=chart_theme['legend_bg'],
            bordercolor=chart_theme['legend_border'],
            borderwidth=1
        ),
        'margin': dict(l=60, r=150, t=100, b=50),
        'height': 700 if show_rsi else 600
    }
    
    if show_rsi:
        # Update axes for subplots
        fig.update_xaxes(
            gridcolor=chart_theme['grid_color'],
            zerolinecolor=chart_theme['grid_color'],
            showgrid=True,
            rangeslider=dict(visible=False),
            row=1, col=1
        )
        fig.update_xaxes(
            gridcolor=chart_theme['grid_color'],
            showgrid=True,
            row=2, col=1
        )
        fig.update_yaxes(
            gridcolor=chart_theme['grid_color'],
            zerolinecolor=chart_theme['grid_color'],
            showgrid=True,
            side='right',
            row=1, col=1
        )
        fig.update_yaxes(
            gridcolor=chart_theme['grid_color'],
            range=[0, 100],
            side='right',
            row=2, col=1
        )
    else:
        layout_updates['xaxis'] = dict(
            gridcolor=chart_theme['grid_color'],
            zerolinecolor=chart_theme['grid_color'],
            showgrid=True,
            rangeslider=dict(visible=False)
        )
        layout_updates['yaxis'] = dict(
            gridcolor=chart_theme['grid_color'],
            zerolinecolor=chart_theme['grid_color'],
            showgrid=True,
            side='right'
        )
    
    fig.update_layout(**layout_updates)
    return fig



def create_market_hours_fig(now: datetime, theme='dark'):
    """Generate Plotly figure for forex sessions timeline."""
    utc_hour_decimal = now.hour + now.minute / 60 + now.second / 3600
    hour_int = now.hour
    chart_theme = get_plotly_theme(theme)

    if theme == 'light':
        plot_bg = '#ffffff'
        paper_bg = '#ffffff'
        font_color = '#2d3748'
        tick_color = '#718096'
        grid_color = '#e2e8f0'
    else:
        plot_bg = chart_theme['plot_bgcolor']
        paper_bg = chart_theme['paper_bgcolor']
        font_color = chart_theme['font_color']
        tick_color = chart_theme['muted_text']
        grid_color = chart_theme['grid_color']

    overlap_fill = 'rgba(29, 78, 216, 0.15)' if theme == 'light' else 'rgba(92, 136, 199, 0.12)'
    overlap_line = 'rgba(29, 78, 216, 0.45)' if theme == 'light' else 'rgba(92, 136, 199, 0.3)'
    now_line_color = '#b91c1c' if theme == 'light' else '#dc2626'

    # Session definitions (UTC hours, Sydney wraps)
    sessions = {
        'Sydney': (22, 7),
        'Tokyo': (0, 9),
        'London': (8, 17),
        'New York': (13, 22)
    }
    colors = {
        'Sydney': '#5ba878',
        'Tokyo': '#e69a55',
        'London': '#5c88c7',
        'New York': '#bd5c9b'
    }
    markets = ['Sydney', 'Tokyo', 'London', 'New York']
    y_pos = {m: i for i, m in enumerate(markets)}

    fig = go.Figure()

    # Add session blocks as rectangles
    for market, (start, end) in sessions.items():
        y = y_pos[market] + 0.5
        color = colors[market]
        if start < end:
            # Normal session
            fig.add_shape(type='rect',
                          x0=start, x1=end,
                          y0=y - 0.4, y1=y + 0.4,
                          fillcolor=color, opacity=0.9,
                          line=dict(width=0))
        else:
            # Wrapping session (Sydney)
            fig.add_shape(type='rect',
                          x0=start, x1=24,
                          y0=y - 0.4, y1=y + 0.4,
                          fillcolor=color, opacity=0.9,
                          line=dict(width=0))
            fig.add_shape(type='rect',
                          x0=0, x1=end,
                          y0=y - 0.4, y1=y + 0.4,
                          fillcolor=color, opacity=0.9,
                          line=dict(width=0))

    # Overlap highlight (London/NY 13:00-17:00 UTC)
    fig.add_shape(type='rect',
                  x0=13, x1=17,
                  y0=0, y1=4,
                  fillcolor=overlap_fill,
                  line=dict(color=overlap_line, width=1))

    # Current time vertical line
    fig.add_shape(type='line',
                  x0=utc_hour_decimal, x1=utc_hour_decimal,
                  y0=0, y1=4,
                  line=dict(color=now_line_color, width=3, dash='solid'),
                  opacity=0.8)

    # Layout (white/light theme)
    fig.update_layout(
        height=380,
        margin=dict(l=110, r=30, t=20, b=80),
        template=chart_theme['template'],
        plot_bgcolor=plot_bg,
        paper_bgcolor=paper_bg,
        font=dict(color=font_color, family='Inter, sans-serif'),
        xaxis=dict(
            range=[0, 24],
            tickmode='array',
            tickvals=list(range(25)),
            ticktext=[f'{i:02d}' for i in range(25)],
            side='top',
            showgrid=True,
            gridcolor=grid_color,
            tickfont=dict(color=tick_color, size=12)
        ),
        yaxis=dict(
            tickvals=[0.5, 1.5, 2.5, 3.5],
            ticktext=markets,
            tickfont=dict(color=font_color, size=14, weight=600),
            showgrid=False
        ),
        annotations=[dict(
            x=15, y=-0.12, text='London/NY Overlap (Main Session)',
            showarrow=False, font=dict(size=12, color=tick_color)
        )]
    )

    return fig


# =============================================================================

# DASH APPLICATION SETUP
# =============================================================================

# Color scheme
COLORS = {
    'bg': '#0a0a0a',
    'card_bg': '#141414',
    'border': '#1f1f1f',
    'text': '#e0e0e0',
    'text_secondary': '#888888',
    'green': '#00C48C',
    'red': '#FF4D4D',
    'blue': '#4A90E2',
    'accent': '#2d2d2d'
}


def get_plotly_theme(theme='dark'):
    """Return theme-aware Plotly colors/templates."""
    is_light = theme == 'light'
    return {
        'template': 'plotly_white' if is_light else 'plotly_dark',
        'paper_bgcolor': '#ffffff' if is_light else COLORS['card_bg'],
        'plot_bgcolor': '#f8fafc' if is_light else COLORS['card_bg'],
        'font_color': '#1f2937' if is_light else COLORS['text'],
        'grid_color': '#dbe3ef' if is_light else '#1a1a1a',
        'legend_bg': 'rgba(255,255,255,0.85)' if is_light else 'rgba(10,10,10,0.8)',
        'legend_border': '#dbe3ef' if is_light else COLORS['border'],
        'muted_text': '#5b6474' if is_light else COLORS['text_secondary'],
        'warn_color': '#b42318' if is_light else COLORS['red'],
        'success': '#15803d' if is_light else COLORS['green'],
        'danger': '#b91c1c' if is_light else COLORS['red'],
        'info': '#1d4ed8' if is_light else COLORS['blue'],
        'neutral': '#475569' if is_light else '#888888'
    }

# =============================================================================
# LAYOUT COMPONENTS
# =============================================================================

def create_metric_card(title, value, subtitle=None, color='text'):
    """Create a metric display card."""
    color_class = {
        'green': 'success',
        'red': 'danger', 
        'blue': 'primary',
        'text': 'light'
    }.get(color, 'light')
    
    return dbc.Card(
        dbc.CardBody([
            html.H6(title, className="card-subtitle mb-2 text-muted", style={'fontSize': '0.75rem', 'textTransform': 'uppercase', 'letterSpacing': '1px'}),
            html.H3(value, className=f"card-title text-{color_class} mb-0", style={'fontSize': '1.75rem', 'fontWeight': '600'}),
            html.Small(subtitle, className="text-muted") if subtitle else None
        ]),
        style={
            'backgroundColor': COLORS['card_bg'],
            'border': f'1px solid {COLORS["border"]}',
            'borderRadius': '8px'
        },
        className="h-100"
    )

def create_filter_section(df=None):
    """Create the filter controls section."""
    # Safely extract options even if df is empty
    assets = sorted(df['Asset_Symbol'].unique()) if df is not None and not df.empty else []
    strategies = sorted(df['Strategy_Name'].unique()) if df is not None and not df.empty else []
    min_date = df['Timestamp'].min().date() if df is not None and not df.empty else datetime.now().date()
    max_date = df['Timestamp'].max().date() if df is not None and not df.empty else datetime.now().date()

    return dbc.Card(
        dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    html.Label("Assets", style={'color': COLORS['text_secondary'], 'fontSize': '0.75rem', 'textTransform': 'uppercase'}),
                    dcc.Dropdown(
                        id='asset-filter',
                        options=[{'label': a, 'value': a} for a in assets],
                        multi=True,
                        placeholder="All Assets",
                        style={'backgroundColor': COLORS['card_bg'], 'color': COLORS['text'], 'border': f'1px solid {COLORS["border"]}'},
                        className="dash-dropdown-dark"
                    )
                ], width=2),
                dbc.Col([
                    html.Label("Strategies", style={'color': COLORS['text_secondary'], 'fontSize': '0.75rem', 'textTransform': 'uppercase'}),
                    dcc.Dropdown(
                        id='strategy-filter',
                        options=[{'label': s, 'value': s} for s in strategies],
                        multi=True,
                        placeholder="All Strategies",
                        style={'backgroundColor': COLORS['card_bg'], 'color': COLORS['text'], 'border': f'1px solid {COLORS["border"]}'}
                    )
                ], width=3),
                dbc.Col([
                    html.Label("Status", style={'color': COLORS['text_secondary'], 'fontSize': '0.75rem', 'textTransform': 'uppercase'}),
                    dcc.Dropdown(
                        id='status-filter',
                        options=[
                            {'label': 'All', 'value': 'All'},
                            {'label': 'Approved', 'value': 'Approved'},
                            {'label': 'Vetoed', 'value': 'Vetoed'}
                        ],
                        value='All',
                        clearable=False,
                        style={'backgroundColor': COLORS['card_bg'], 'color': COLORS['text'], 'border': f'1px solid {COLORS["border"]}'}
                    )
                ], width=2),
                dbc.Col([
                    html.Label("Outcome", style={'color': COLORS['text_secondary'], 'fontSize': '0.75rem', 'textTransform': 'uppercase'}),
                    dcc.Dropdown(
                        id='outcome-filter',
                        options=[
                            {'label': 'All', 'value': 'All'},
                            {'label': 'Win', 'value': 'Win'},
                            {'label': 'Loss', 'value': 'Loss'},
                            {'label': 'Pending', 'value': 'Pending'}
                        ],
                        value='All',
                        clearable=False,
                        style={'backgroundColor': COLORS['card_bg'], 'color': COLORS['text'], 'border': f'1px solid {COLORS["border"]}'}
                    )
                ], width=2),
                dbc.Col([
                    html.Label("Date Range", style={'color': COLORS['text_secondary'], 'fontSize': '0.75rem', 'textTransform': 'uppercase'}),
                    dcc.DatePickerRange(
                        id='date-filter',
                        min_date_allowed=min_date,
                        max_date_allowed=max_date,
                        start_date=min_date,
                        end_date=max_date,
                        display_format='YYYY-MM-DD',
                        style={'backgroundColor': COLORS['card_bg']}
                    ),
                    # STORY 8 – OVERLAP BADGE + QUICK BUTTONS
                    html.Div(id='overlap-badge', style={'marginTop': '8px', 'fontSize': '0.8rem'}),
                    dbc.Row([
                        dbc.Col(dbc.Button("London/NY Overlap Today", id='btn-lon-ny', color='warning', size='sm', className='me-1'), width='auto'),
                        dbc.Col(dbc.Button("Sydney/Tokyo Overlap Today", id='btn-syd-tok', color='warning', size='sm'), width='auto')
                    ], className='mt-2 g-2')
                ], width=3)
            ], className="g-3")
        ]),
        style={
            'backgroundColor': COLORS['card_bg'],
            'border': f'1px solid {COLORS["border"]}',
            'borderRadius': '8px',
            'marginBottom': '20px'
        }
    )

# =============================================================================
# MAIN LAYOUT
# =============================================================================

app.layout = dbc.Container([
    # Store for data
    dcc.Store(id='stored-data'),
    dcc.Store(id='selected-trade'),
    dcc.Store(id='theme-store', data='dark', storage_type='local'),
    html.Div(id='theme-sync', style={'display': 'none'}),
   
    # Export downloads
    dcc.Download(id="download-csv"),
    dcc.Download(id="download-excel"),
   
    # Live clock & market hours
    dcc.Interval(id='live-clock-interval', interval=1000, n_intervals=0),  # 1-second refresh
    dcc.Store(id='current-utc-time'),
   
    # Auto-refresh interval (5 minutes)
    dcc.Interval(id='auto-refresh', interval=5*60*1000, n_intervals=0),
    
    # === HEADER ===
    dbc.Row([
        # Left: brand area
        dbc.Col([
            dbc.Row([
                # Logo card — leftmost
                dbc.Col(
                    dbc.Card([
                        dbc.CardBody(
                            html.Img(
                                src='/assets/logo.png',
                                style={
                                    'height': '46px',
                                    'width': 'auto',
                                    'objectFit': 'contain',
                                    'borderRadius': '4px',
                                    'display': 'block'
                                },
                                id='brand-logo-img'
                            ),
                            style={'padding': '7px 10px'}
                        )
                    ], style={
                        'backgroundColor': 'var(--brand-panel-bg)',
                        'border': '1px solid var(--brand-panel-border)',
                        'borderRadius': '8px',
                        'boxShadow': 'var(--brand-panel-shadow)'
                    }),
                    width="auto", className="align-self-center"
                ),
                # Icon
                dbc.Col(
                    html.I(className="bi bi-currency-exchange", style={'fontSize': '46px', 'color': 'var(--brand-accent)'}),
                    width="auto", className="px-3 align-self-center"
                ),
                # ADICA + subtitle + timer
                dbc.Col([
                    html.H1("ADICA", style={
                        'color': 'var(--text)',
                        'fontWeight': '800',
                        'letterSpacing': '3.5px',
                        'fontSize': '2.65rem',
                        'textShadow': '0 0 16px rgba(2, 132, 199, 0.22)',
                        'marginBottom': '2px'
                    }),
                    html.P("Advanced Institutional Currency Analytics", style={
                        'color': 'var(--brand-accent)', 'fontSize': '0.95rem', 'letterSpacing': '1.8px', 'marginBottom': '4px'
                    }),
                    html.Div(id='live-datetime', style={
                        'color': 'var(--brand-soft)', 'fontSize': '0.82rem',
                        'fontFamily': 'JetBrains Mono, monospace'
                    })
                ], width="auto")
            ], className="g-2 align-items-center"),
        ], width=True),

        # Right: theme toggle
        dbc.Col([
            html.Div([
                html.Button(
                    id='theme-toggle',
                    children=[html.Span("☀", style={'marginRight': '5px'}), "Light"],
                    className='theme-toggle-btn',
                    style={'color': 'var(--brand-soft)'}
                )
            ], style={'display': 'flex', 'justifyContent': 'flex-end', 'alignItems': 'center', 'height': '100%'})
        ], width="auto", className="align-self-center")
    ], className="mb-5 align-items-center"),

    # === FULL-WIDTH WHITE MARKET HOURS ===
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.Div(id='market-sessions-widget')
                ])
            ], style={
                'backgroundColor': 'var(--card-bg)',
                'border': '1px solid var(--border)',
                'borderRadius': '12px',
                'boxShadow': '0 10px 25px rgba(0,0,0,0.06)',
                'padding': '25px'
            })
        ], width=12)
    ], className="mb-5"),
    
    # === STORY 1 INSERT START ===
    dbc.Row([
        dbc.Col(
            dbc.Card([
                dbc.CardBody([
                    html.H6("Outcome Breakdown", style={'color': COLORS['text_secondary'], 'fontSize': '0.75rem', 'textTransform': 'uppercase'}),
                    dcc.Graph(id='outcome-pie', config={'displayModeBar': False}, style={'height': '200px'})
                ])
            ], style={'backgroundColor': COLORS['card_bg'], 'border': f'1px solid {COLORS["border"]}', 'borderRadius': '8px'})
        , width=6),
        dbc.Col(
            html.Div(id='outcome-count-cards', style={'display': 'flex', 'gap': '10px'})
        , width=6)
    ], style={'marginBottom': '20px'}),
    # === STORY 1 INSERT END ===


    # Metrics Row
    dbc.Row([
        dbc.Col(create_metric_card("Total Signals", "0", color='blue'), id='metric-total', width=2),
        dbc.Col(create_metric_card("Approval Rate", "0%", color='green'), id='metric-approval', width=2),
        dbc.Col(create_metric_card("Avg Confidence", "0%", color='blue'), id='metric-confidence', width=2),
        dbc.Col(create_metric_card("Win Rate", "0%", "Audited Only", color='green'), id='metric-winrate', width=2),
        dbc.Col(
            html.Div(create_metric_card("Audited", "0", color='text'), id='metric-audited', n_clicks=0, style={'cursor': 'pointer'}), 
            width=2
        ),
        dbc.Col(create_metric_card("Pending", "0", color='blue'), id='metric-pending', width=2),
    ], style={'marginBottom': '20px'}),
    

    # Model Health Score
    dbc.Row([
        dbc.Col([
            # Wrap the Card in an html.Div to capture clicks
            html.Div(
                dbc.Card(
                    dbc.CardBody([
                        html.Div([
                            html.Span("Model Health Score: ", style={'color': COLORS['text_secondary']}),
                            html.Span(id='health-score', style={'color': COLORS['green'], 'fontWeight': 'bold', 'fontSize': '1.2rem'}),
                            html.Div(id='health-bar', style={
                                'width': '100%',
                                'height': '4px',
                                'backgroundColor': COLORS['border'],
                                'marginTop': '8px',
                                'borderRadius': '2px',
                                'overflow': 'hidden'
                            }, children=html.Div(style={
                                'width': '0%',
                                'height': '100%',
                                'backgroundColor': COLORS['green'],
                                'transition': 'width 0.5s ease'
                            }, id='health-fill'))
                        ])
                    ]),
                    style={
                        'backgroundColor': COLORS['card_bg'],
                        'border': f'1px solid {COLORS["border"]}',
                        'borderRadius': '8px',
                    }
                ),
                id='health-card',
                n_clicks=0,
                style={
                    'marginBottom': '20px',
                    'cursor': 'pointer' # Moves the pointer cursor to the clickable wrapper
                }
            )
        ], width=12)
    ]),
    
    
    # Filters are rendered once; options and date bounds are synced from stored-data via callback.
    html.Div(create_filter_section(), id='filter-section'),
    
    # Tabs for different views
        # Tabs for different views
    dbc.Tabs([
        dbc.Tab(label="Trade Signals", tab_id="tab-signals", children=[
            html.Div([
                dbc.Row([
                    dbc.Col(
                        dbc.RadioItems(
                            id='pips-toggle',
                            options=[
                                {'label': 'Gross Pips & RR', 'value': 'gross'},
                                {'label': 'Net Pips & RR (−1.5 pip friction)', 'value': 'net'}
                            ],
                            value='gross',
                            inline=True,
                            className="mb-2"
                        ),
                        width=8
                    ),
                    dbc.Col([
                        dbc.Button("Export CSV", id="btn-csv", color="primary", size="sm", className="me-2"),
                        dbc.Button("Export Excel", id="btn-excel", color="success", size="sm")
                    ], width=4, className="text-end")
                ], className="mb-3"),
                html.Div(id='signals-table-container')
            ])
        ]),
        
        # STORY 9 – NEW PROJECT PROGRESS TAB
        dbc.Tab(label="Project Progress", tab_id="tab-progress", children=[
            dbc.Card([
                dbc.CardBody([
                    html.H4("Scalable Brain – Current Status & Roadmap", className="mb-4", style={'color': COLORS['text']}),
                    
                    html.P([
                        "The system is currently in transition from retail-style signal generation to a fully institutional-grade quantitative engine. ",
                        html.Strong("100% AI veto rate on signals"),
                        " is intentional and correct behavior — it indicates the current Layer 0 edge lacks positive net expectancy after friction."
                    ], className="lead"),
                    
                    html.Hr(className="my-4"),
                    
                    html.H5("Key Architectural Goals", style={'color': COLORS['green']}),
                    html.Ul([
                        html.Li("Multi-Timeframe (MTF) integration without look-ahead bias"),
                        html.Li("Dynamic volatility-adjusted exits instead of static RR"),
                        html.Li("Advanced ML classification (Random Forest / XGBoost / Deep Learning) with institutional features: volume profiles, volatility skew, macro NLP"),
                        html.Li("Robust execution friction modeling (1.5 pip baseline on EUR/USD)"),
                        html.Li("Fractional Kelly position sizing (0.1–0.25 of full Kelly)")
                    ]),
                    
                    html.Hr(className="my-4"),
                    
                    html.H5("Main Retail Strategy Failures Being Eliminated", style={'color': COLORS['red']}),
                    html.Ul([
                        html.Li("Lagging 50/200 EMA crossovers → severe phase lag & late entries"),
                        html.Li("Static 1:3 RR → path dependency & long losing streaks in ranging markets"),
                        html.Li("Ignoring fixed 1.5-pip execution friction → destroys micro-target strategies"),
                        html.Li("No MTF alignment → intraday signals fighting macro structure")
                    ]),
                    
                    html.Hr(className="my-4"),
                    
                    html.Div([
                        dbc.Button(
                            "View Full Scalable Brain Dashboard →",
                            color="primary",
                            size="lg",
                            href="https://scalable-brain.vercel.app/index.html",
                            target="_blank",
                            external_link=True,
                            className="d-block text-center"
                        )
                    ], className="mt-4")
                ])
            ], style={'backgroundColor': COLORS['card_bg'], 'border': f'1px solid {COLORS["border"]}'})
        ]),
        
        dbc.Tab(label="Performance Analytics", tab_id="tab-analytics", children=[
            html.Div(id='analytics-container', style={'marginTop': '20px'})
        ])
    ], id="main-tabs", active_tab="tab-signals", style={
        'borderBottom': f'1px solid {COLORS["border"]}',
        'marginBottom': '20px'
    }),
    
    # Chart Modal
        # Chart Modal with Controls
    dbc.Modal([
        dbc.ModalHeader([
            html.Div([
                html.H5("Trade Replay & Technical Analysis", style={'color': COLORS['text'], 'marginBottom': '0'}),
                html.Small(id='trade-details-header', style={'color': COLORS['text_secondary']})
            ]),
            dbc.Button("×", id="close-modal", className="ms-auto", style={
                'background': 'none',
                'border': 'none',
                'color': COLORS['text_secondary'],
                'fontSize': '1.5rem',
                'cursor': 'pointer'
            })
        ], style={'backgroundColor': COLORS['card_bg'], 'borderBottom': f'1px solid {COLORS["border"]}'}),
        
        # Controls Bar
        dbc.ModalBody([
            # Indicator Controls
            dbc.Card([
                dbc.CardBody([
                    html.H6("Technical Indicators", style={'color': COLORS['text_secondary'], 'fontSize': '0.75rem', 'textTransform': 'uppercase', 'marginBottom': '15px'}),
                    dbc.Row([
                        # SMA Controls
                        dbc.Col([
                            dbc.Checklist(
                                options=[{"label": "SMA", "value": 1}],
                                value=[1],
                                id="show-sma",
                                switch=True,
                                style={'color': COLORS['text']}
                            ),
                            dcc.Input(
                                id="sma-periods",
                                type="text",
                                placeholder="20,50",
                                value="20,50",
                                style={
                                    'backgroundColor': COLORS['bg'],
                                    'color': COLORS['text'],
                                    'border': f'1px solid {COLORS["border"]}',
                                    'borderRadius': '4px',
                                    'padding': '4px',
                                    'fontSize': '0.8rem',
                                    'marginTop': '5px',
                                    'width': '100%'
                                }
                            ),
                            html.Small("Periods (comma sep)", style={'color': COLORS['text_secondary'], 'fontSize': '0.7rem'})
                        ], width=2),
                        
                        # EMA Controls
                        dbc.Col([
                            dbc.Checklist(
                                options=[{"label": "EMA", "value": 1}],
                                value=[1],
                                id="show-ema",
                                switch=True,
                                style={'color': COLORS['text']}
                            ),
                            dcc.Input(
                                id="ema-periods",
                                type="text",
                                placeholder="12,26",
                                value="12,26",
                                style={
                                    'backgroundColor': COLORS['bg'],
                                    'color': COLORS['text'],
                                    'border': f'1px solid {COLORS["border"]}',
                                    'borderRadius': '4px',
                                    'padding': '4px',
                                    'fontSize': '0.8rem',
                                    'marginTop': '5px',
                                    'width': '100%'
                                }
                            ),
                            html.Small("Periods (comma sep)", style={'color': COLORS['text_secondary'], 'fontSize': '0.7rem'})
                        ], width=2),
                        
                        # RSI Controls
                        dbc.Col([
                            dbc.Checklist(
                                options=[{"label": "RSI", "value": 1}],
                                value=[1],
                                id="show-rsi",
                                switch=True,
                                style={'color': COLORS['text']}
                            ),
                            dcc.Slider(
                                id="rsi-period",
                                min=5,
                                max=30,
                                step=1,
                                value=14,
                                marks={5: '5', 14: '14', 30: '30'},
                                className="dash-slider-dark"
                            ),
                            html.Small("RSI Period", style={'color': COLORS['text_secondary'], 'fontSize': '0.7rem'})
                        ], width=3),
                        
                        # Bollinger Bands
                        dbc.Col([
                            dbc.Checklist(
                                options=[{"label": "Bollinger Bands", "value": 1}],
                                value=[1],
                                id="show-bb",
                                switch=True,
                                style={'color': COLORS['text']}
                            ),
                            dcc.Slider(
                                id="bb-period",
                                min=10,
                                max=50,
                                step=5,
                                value=20,
                                marks={10: '10', 20: '20', 50: '50'},
                                className="dash-slider-dark"
                            ),
                            html.Small("BB Period", style={'color': COLORS['text_secondary'], 'fontSize': '0.7rem'})
                        ], width=3),
                        
                        # Trendline
                        dbc.Col([
                            dbc.Checklist(
                                options=[{"label": "Trendline", "value": 1}],
                                value=[1],
                                id="show-trendline",
                                switch=True,
                                style={'color': COLORS['text']}
                            ),
                            html.Small("Auto trend detection", style={'color': COLORS['text_secondary'], 'fontSize': '0.7rem', 'marginTop': '20px'})
                        ], width=2),
                    ], className="g-2")
                ], style={'padding': '15px'})
            ], style={'backgroundColor': COLORS['accent'], 'border': f'1px solid {COLORS["border"]}', 'marginBottom': '15px'}),
            
            # Chart Area
            dcc.Loading(
                id="chart-loading",
                type="circle",
                color=COLORS['blue'],
                children=dcc.Graph(
                    id='candlestick-chart', 
                    config={
                        'displayModeBar': True,
                        'modeBarButtonsToAdd': ['drawline', 'drawopenpath', 'eraseshape'],
                        'displaylogo': False
                    },
                    style={'height': '65vh'}
                )
            ),
            
            # Trade Info Panel
            html.Div(id='trade-info-panel', style={
                'marginTop': '15px',
                'padding': '15px',
                'backgroundColor': COLORS['card_bg'],
                'border': f'1px solid {COLORS["border"]}',
                'borderRadius': '8px'
            })
        ], style={'backgroundColor': COLORS['bg'], 'padding': '20px'}),
        
        dbc.ModalFooter([
            html.Small("Data provided by OANDA | Technical indicators calculated locally", style={'color': COLORS['text_secondary']})
        ], style={'backgroundColor': COLORS['card_bg'], 'borderTop': f'1px solid {COLORS["border"]}'})
    ], id="chart-modal", size="xl", is_open=False, style={'maxWidth': '1400px'}),


    # === STORY 2 MODAL ===
    dbc.Modal([
        dbc.ModalHeader("Audit Breakdown – Won vs Lost", style={'backgroundColor': COLORS['card_bg']}),
        dbc.ModalBody(id='audit-modal-body', style={'backgroundColor': COLORS['bg']}),
        dbc.ModalFooter(dbc.Button("Close", id="close-audit-modal", className="ms-auto"), style={'backgroundColor': COLORS['card_bg']})
    ], id="audit-modal", is_open=False, size="xl"),

    # === STORY 5 SESSION MODAL ===
    dbc.Modal([
        dbc.ModalHeader(id='session-modal-header'),
        dbc.ModalBody(id='session-modal-body'),
        dbc.ModalFooter(dbc.Button("Close", id="close-session-modal"))
    ], id="session-modal", is_open=False, size="sm"),

    # === STORY 6 MODEL AUDIT MODAL ===
    dbc.Modal([
        dbc.ModalHeader("Model Health Audit – Full Diagnostics", id='audit-header'),
        dbc.ModalBody(id='model-audit-body', style={'backgroundColor': COLORS['bg'], 'padding': '20px'}),
        dbc.ModalFooter(dbc.Button("Close", id="close-model-audit", className="ms-auto"))
    ], id="model-audit-modal", is_open=False, size="xl", style={'maxWidth': '1200px'}),

], fluid=True, id="main-container", className="p-0", style={
    'backgroundColor': COLORS['bg'],
    'minHeight': '100vh',
    'padding': '20px',
    'fontFamily': 'Segoe UI, Arial, sans-serif'
})

# =============================================================================
# CALLBACKS
# =============================================================================

@app.callback(
    Output('stored-data', 'data'),
    Output('metric-total', 'children'),
    Output('metric-approval', 'children'),
    Output('metric-confidence', 'children'),
    Output('metric-winrate', 'children'),
    Output('metric-audited', 'children'),
    Output('metric-pending', 'children'),
    Output('health-score', 'children'),
    Output('health-fill', 'style'),
    Output('outcome-pie', 'figure'),
    Output('outcome-count-cards', 'children'),
    Input('auto-refresh', 'n_intervals'),
    Input('theme-store', 'data')
)
def update_data(n, theme):
    """Load data and update all metrics."""
    df = load_data()
    
    if df.empty:
        empty_card = create_metric_card("No Data", "-", color='text')
        empty_style = {'width': '0%', 'height': '100%', 'backgroundColor': COLORS['red']}
        return {}, empty_card, empty_card, empty_card, empty_card, empty_card, empty_card, "N/A", empty_style, go.Figure(), []
    
    # Calculate metrics
    total_signals = len(df)
    approval_rate = (df['Is_Approved'].sum() / total_signals * 100) if total_signals > 0 else 0
    avg_confidence = df['Confidence_Score'].mean() if not df.empty else 0
    
    audited_df = df[df['Actual_Outcome'].notna()]
    audited_count = len(audited_df)
    win_count = len(audited_df[audited_df['Actual_Outcome'] == 1])
    win_rate = (win_count / audited_count * 100) if audited_count > 0 else 0
    
    pending_count = len(df[df['Actual_Outcome'].isna()])
    
    # Model Health Score (weighted composite)
    health_score = (approval_rate * 0.4) + (win_rate * 0.3) + (avg_confidence * 0.3)
    health_score = min(100, max(0, health_score))
    
    # Determine health color
    if health_score >= 70:
        health_color = COLORS['green']
    elif health_score >= 40:
        health_color = COLORS['blue']
    else:
        health_color = COLORS['red']
    
    health_style = {
        'width': f'{health_score}%',
        'height': '100%',
        'backgroundColor': health_color,
        'transition': 'width 0.5s ease'
    }
    
    # Create metric cards
    total_card = create_metric_card("Total Signals", str(total_signals), color='blue')
    approval_card = create_metric_card("Approval Rate", f"{approval_rate:.1f}%", color='green' if approval_rate > 50 else 'red')
    confidence_card = create_metric_card("Avg Confidence", f"{avg_confidence:.1f}%", color='blue')
    winrate_card = create_metric_card("Win Rate", f"{win_rate:.1f}%", f"{audited_count} audited", color='green' if win_rate > 50 else 'red')
    audited_card = create_metric_card("Audited", str(audited_count), color='text')
    pending_card = create_metric_card("Pending", str(pending_count), color='blue')
    
    # Store data as dict
    data_dict = df.to_dict('records')

    # === STORY 1 CALCULATIONS ===
    wins = win_count
    losses = audited_count - win_count if audited_count > 0 else 0
    pending = pending_count
    
    chart_theme = get_plotly_theme(theme)
    pie_fig = go.Figure(data=[go.Pie(
        labels=['Wins', 'Losses', 'Pending'],
        values=[wins, losses, pending],
        marker_colors=[chart_theme['success'], chart_theme['danger'], chart_theme['info']],
        hole=0.6
    )])
    pie_fig.update_layout(
        template=chart_theme['template'],
        paper_bgcolor=chart_theme['paper_bgcolor'],
        plot_bgcolor=chart_theme['plot_bgcolor'],
        font=dict(color=chart_theme['font_color']),
        height=200,
        showlegend=True,
        margin=dict(l=0, r=0, t=0, b=0)
    )
    
    count_cards = dbc.Row([
        dbc.Col(create_metric_card("Wins", str(wins), color='green'), width=4),
        dbc.Col(create_metric_card("Losses", str(losses), color='red'), width=4),
        dbc.Col(create_metric_card("Pending", str(pending), color='blue'), width=4)
    ], className="w-100")

    return data_dict, total_card, approval_card, confidence_card, winrate_card, audited_card, pending_card, f"{health_score:.0f}/100", health_style, pie_fig, count_cards


@app.callback(
    Output('asset-filter', 'options'),
    Output('strategy-filter', 'options'),
    Output('date-filter', 'min_date_allowed'),
    Output('date-filter', 'max_date_allowed'),
    Output('date-filter', 'start_date'),
    Output('date-filter', 'end_date'),
    Input('stored-data', 'data'),
    Input('btn-lon-ny', 'n_clicks'),
    Input('btn-syd-tok', 'n_clicks'),
    State('date-filter', 'start_date'),
    State('date-filter', 'end_date')
)
def sync_filter_controls(data, n_lon, n_tok, start_date, end_date):
    """Keep filter options/date bounds aligned with current stored data."""
    today = datetime.now().date()

    if not data:
        return [], [], today, today, today, today

    df = pd.DataFrame(data)
    if df.empty or 'Timestamp' not in df.columns:
        return [], [], today, today, today, today

    df['Timestamp'] = pd.to_datetime(df['Timestamp'], errors='coerce')
    df = df[df['Timestamp'].notna()]
    if df.empty:
        return [], [], today, today, today, today

    assets = sorted(df['Asset_Symbol'].dropna().unique().tolist()) if 'Asset_Symbol' in df.columns else []
    strategies = sorted(df['Strategy_Name'].dropna().unique().tolist()) if 'Strategy_Name' in df.columns else []
    asset_options = [{'label': a, 'value': a} for a in assets]
    strategy_options = [{'label': s, 'value': s} for s in strategies]

    min_date = df['Timestamp'].min().date()
    max_date = df['Timestamp'].max().date()

    ctx = callback_context
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else None

    # Quick buttons intentionally jump to "today", clamped to available data bounds.
    if trigger_id in ('btn-lon-ny', 'btn-syd-tok'):
        target = min(max(today, min_date), max_date)
        return asset_options, strategy_options, min_date, max_date, target, target

    def parse_or_none(raw):
        if not raw:
            return None
        try:
            return pd.to_datetime(raw).date()
        except Exception:
            return None

    start = parse_or_none(start_date)
    end = parse_or_none(end_date)

    # If current picker values are missing/invalid/out of data bounds, reset to full available range.
    if start is None or end is None or start > end or start < min_date or end > max_date:
        start, end = min_date, max_date

    return asset_options, strategy_options, min_date, max_date, start, end
    

@app.callback(
    Output('signals-table-container', 'children'),
    Input('stored-data', 'data'),
    Input('asset-filter', 'value'),
    Input('strategy-filter', 'value'),
    Input('status-filter', 'value'),
    Input('outcome-filter', 'value'),
    Input('date-filter', 'start_date'),
    Input('date-filter', 'end_date'),
    Input('pips-toggle', 'value')
)
def update_table(data, assets, strategies, status, outcome_val, start_date, end_date, pips_mode):
    """Update the signals table based on filters."""
    if not data:
        return html.Div("No data available", style={'color': COLORS['text_secondary'], 'textAlign': 'center', 'padding': '40px'})
    
    df = pd.DataFrame(data)

    if not df.empty:
        df['Timestamp'] = pd.to_datetime(df['Timestamp'])
    
    # Apply filters
    if assets:
        df = df[df['Asset_Symbol'].isin(assets)]
    if strategies:
        df = df[df['Strategy_Name'].isin(strategies)]
    if status and status != 'All':
        df = df[df['Status'] == status]
    if outcome_val and outcome_val != 'All':
        df = df[df['Outcome'] == outcome_val]
    if start_date and end_date:
        df = df[(df['Timestamp'].dt.date >= pd.to_datetime(start_date).date()) & 
                (df['Timestamp'].dt.date <= pd.to_datetime(end_date).date())]
                
    # Prepare data for AG Gridtunnel
    display_df = df.copy()
    display_df['Timestamp'] = display_df['Timestamp'].dt.strftime('%Y-%m-%d %H:%M')
    
    # === STORY 3 – NET/GROSS CALC (fixed) ===
    def calc_pips_rr(row, mode):
        e = row.get('Entry_Price')
        sl = row.get('Stop_Loss')
        tp = row.get('Take_Profit')
        if pd.isna(e) or pd.isna(sl) or pd.isna(tp):
            return None, "N/A"
        
        gross_tp = abs((tp - e) * 10000)
        gross_sl = abs((e - sl) * 10000)
        
        if mode == 'net':
            pips = round(gross_tp - 1.5, 1)
            rr = round((gross_tp - 1.5) / (gross_sl + 1.5), 2) if gross_sl > 0 else None
        else:
            pips = round(gross_tp, 1)
            rr = round(gross_tp / gross_sl, 2) if gross_sl > 0 else None
            
        return pips, f"1:{rr}" if rr else "N/A"
    
    display_df['Pips_Targeted'] = display_df.apply(lambda r: calc_pips_rr(r, pips_mode)[0], axis=1)
    display_df['RR'] = display_df.apply(lambda r: calc_pips_rr(r, pips_mode)[1], axis=1)
    
    # Column definitions using Native AG Grid Conditional Styling
    column_defs = [
        {
            'field': 'Asset_Symbol',
            'headerName': 'Asset',
            'cellStyle': {'color': '#4A90E2', 'fontWeight': 'bold', 'cursor': 'pointer'},
            'width': 100,
            'sortable': True,
            'filter': True
        },
        {
            'field': 'Timestamp',
            'headerName': 'Time',
            'width': 150,
            'sortable': True
        },
        {
            'field': 'Strategy_Name',
            'headerName': 'Strategy',
            'width': 150,
            'sortable': True,
            'filter': True
        },
        {
            'field': 'Signal_Value',
            'headerName': 'Signal',
            'width': 100,
            'cellStyle': {'textAlign': 'center'}
        },
        {
            'field': 'Entry_Price',
            'headerName': 'Entry',
            'width': 100,
            'valueFormatter': {'function': 'params.value ? params.value.toFixed(5) : ""'}
        },
        {
            'field': 'Stop_Loss',
            'headerName': 'SL',
            'width': 100,
            'valueFormatter': {'function': 'params.value ? params.value.toFixed(5) : ""'}
        },
        {
            'field': 'Take_Profit',
            'headerName': 'TP',
            'width': 100,
            'valueFormatter': {'function': 'params.value ? params.value.toFixed(5) : ""'}
        },

        {
            'field': 'RR', 
            'headerName': 'R:R', 
            'width': 80,
            'cellStyle': {'textAlign': 'center', 'fontWeight': 'bold'}
        },
        {
            'field': 'Pips_Targeted', 
            'headerName': 'Pips Targeted', 
            'width': 120,
            'cellStyle': {'color': '#00C48C', 'textAlign': 'center'}
        },


        {
            'field': 'Confidence_Score',
            'headerName': 'Confidence',
            'width': 110,
            'valueFormatter': {'function': 'params.value ? params.value.toFixed(1) + "%" : ""'},
            'cellStyle': {'textAlign': 'center'}
        },
        {
            'field': 'Status',
            'headerName': 'Status',
            'width': 110,
            'cellStyle': {
                'styleConditions': [
                    {
                        'condition': "params.value === 'Approved'",
                        'style': {'backgroundColor': 'rgba(0, 196, 140, 0.15)', 'color': '#00C48C', 'fontWeight': 'bold', 'textAlign': 'center'}
                    },
                    {
                        'condition': "params.value === 'Vetoed'",
                        'style': {'backgroundColor': 'rgba(255, 77, 77, 0.15)', 'color': '#FF4D4D', 'fontWeight': 'bold', 'textAlign': 'center'}
                    }
                ]
            }
        },
        {
            'field': 'Outcome',
            'headerName': 'Outcome',
            'width': 100,
            'cellStyle': {
                'styleConditions': [
                    {
                        'condition': "params.value === 'Pending'",
                        'style': {'backgroundColor': 'rgba(74, 144, 226, 0.15)', 'color': '#4A90E2', 'fontWeight': 'bold', 'textAlign': 'center'}
                    },
                    {
                        'condition': "params.value === 'Win'",
                        'style': {'backgroundColor': 'rgba(0, 196, 140, 0.15)', 'color': '#00C48C', 'fontWeight': 'bold', 'textAlign': 'center'}
                    },
                    {
                        'condition': "params.value === 'Loss'",
                        'style': {'backgroundColor': 'rgba(255, 77, 77, 0.15)', 'color': '#FF4D4D', 'fontWeight': 'bold', 'textAlign': 'center'}
                    }
                ]
            }
        }
    ]
    
    grid = dag.AgGrid(
        id='signals-grid',
        rowData=display_df.to_dict('records'),
        columnDefs=column_defs,
        defaultColDef={
            'resizable': True,
            'sortable': True,
            'filter': True,
            'suppressMovable': False
        },
        dashGridOptions={
            'pagination': True,
            'paginationPageSize': 20, # <-- Change to 20
            'paginationPageSizeSelector': [20, 50, 100], # <-- Match AG Grid's default array
            'rowSelection': {'mode': 'singleRow', 'enableClickSelection': True, 'checkBoxes': False},
            'rowHeight': 45,
            'headerHeight': 40,
            'domLayout': 'normal',
            'suppressCellFocus': True,
            'animateRows': True
        },
        style={
            'height': '600px',
            'width': '100%',
            '--ag-background-color': COLORS['card_bg'],
            '--ag-header-background-color': COLORS['accent'],
            '--ag-odd-row-background-color': COLORS['card_bg'],
            '--ag-header-foreground-color': COLORS['text_secondary'],
            '--ag-foreground-color': COLORS['text'],
            '--ag-border-color': COLORS['border'],
            '--ag-row-hover-color': '#1a1a1a',
            '--ag-selected-row-background-color': '#2a2a2a'
        },
        className="ag-theme-alpine-dark"
    )
    
    return grid



# =============================================================================
# COMBINED MODAL & ROW SELECTION CALLBACK
# =============================================================================
@app.callback(
    Output('chart-modal', 'is_open'),
    Output('selected-trade', 'data'),
    Output('trade-details-header', 'children'),
    Input('signals-grid', 'selectedRows'),
    Input('close-modal', 'n_clicks'),
    State('chart-modal', 'is_open'),
    prevent_initial_call=True
)
def handle_modal_and_selection(selected_rows, close_clicks, is_open):
    """Handle row click to open modal, store trade data, and update header."""
    ctx = dash.callback_context
    if not ctx.triggered:
        return is_open, dash.no_update, dash.no_update
    
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    # Close button clicked
    if trigger_id == 'close-modal':
        return False, dash.no_update, dash.no_update
    
    # Row selected in the AG Grid
    if trigger_id == 'signals-grid' and selected_rows:
        row = selected_rows[0]
        symbol = row.get('Asset_Symbol')
        timestamp = row.get('Timestamp')
        
        header_info = html.Div([
            html.Span(f"{symbol} | ", style={'fontWeight': 'bold', 'color': COLORS['blue']}),
            html.Span(f"{timestamp} | ", style={'color': COLORS['text']}),
            html.Span(f"Strategy: {row.get('Strategy_Name', 'N/A')}", style={'color': COLORS['text_secondary']})
        ])
        
        # Open modal, send row data to store, update header
        return True, row, header_info
    
    return is_open, dash.no_update, dash.no_update


# Chart update callback with indicators
@app.callback(
    Output('candlestick-chart', 'figure'),
    Output('trade-info-panel', 'children'),
    Input('selected-trade', 'data'),
    Input('theme-store', 'data'),
    Input('show-sma', 'value'),
    Input('sma-periods', 'value'),
    Input('show-ema', 'value'),
    Input('ema-periods', 'value'),
    Input('show-rsi', 'value'),
    Input('rsi-period', 'value'),
    Input('show-bb', 'value'),
    Input('bb-period', 'value'),
    Input('show-trendline', 'value'),
    prevent_initial_call=True
)
def update_chart_with_indicators(selected_trade, theme, show_sma, sma_periods_str, show_ema, ema_periods_str,
                                  show_rsi, rsi_period, show_bb, bb_period, show_trendline):
    """Update chart with selected technical indicators."""
    if not selected_trade:
        return go.Figure(), html.Div()
    
    symbol = selected_trade.get('Asset_Symbol')
    entry = selected_trade.get('Entry_Price')
    sl = selected_trade.get('Stop_Loss')
    tp = selected_trade.get('Take_Profit')
    status = selected_trade.get('Status', 'Unknown')
    outcome = selected_trade.get('Outcome', 'Pending')
    confidence = selected_trade.get('Confidence_Score', 0)
    timestamp = pd.to_datetime(selected_trade.get('Timestamp'))
    
    # Parse periods
    try:
        sma_periods = [int(x.strip()) for x in sma_periods_str.split(',') if x.strip().isdigit()] if sma_periods_str else [20, 50]
    except:
        sma_periods = [20, 50]
    
    try:
        ema_periods = [int(x.strip()) for x in ema_periods_str.split(',') if x.strip().isdigit()] if ema_periods_str else [12, 26]
    except:
        ema_periods = [12, 26]
    
    # Fetch candles
    candles = fetch_candles(symbol, timestamp)
    
    # Create chart
    fig = create_enhanced_chart(
        candles=candles,
        entry=entry,
        sl=sl,
        tp=tp,
        status=status,
        outcome=outcome,
        confidence=confidence,
        show_sma=bool(show_sma),
        sma_periods=sma_periods,
        show_ema=bool(show_ema),
        ema_periods=ema_periods,
        show_rsi=bool(show_rsi),
        rsi_period=int(rsi_period) if rsi_period else 14,
        show_bb=bool(show_bb),
        bb_period=int(bb_period) if bb_period else 20,
        show_trendlines=bool(show_trendline),
        theme=theme
    )
    
    # Create info panel
    outcome_color = COLORS['green'] if outcome == 'Win' else (COLORS['red'] if outcome == 'Loss' else COLORS['blue'])
    
    info_panel = dbc.Row([
        dbc.Col([
            html.H6("Trade Details", style={'color': COLORS['text_secondary'], 'fontSize': '0.75rem', 'textTransform': 'uppercase'}),
            html.Div([
                html.P([html.Strong("Signal: "), html.Span(selected_trade.get('Signal_Value', 'N/A'))], style={'margin': '4px 0'}),
                html.P([html.Strong("Entry: "), html.Span(f"{entry:.5f}" if entry else "N/A")], style={'margin': '4px 0'}),
                html.P([html.Strong("Stop Loss: "), html.Span(f"{sl:.5f}" if sl else "N/A", style={'color': COLORS['red']})], style={'margin': '4px 0'}),
                html.P([html.Strong("Take Profit: "), html.Span(f"{tp:.5f}" if tp else "N/A", style={'color': COLORS['green']})], style={'margin': '4px 0'}),
            ])
        ], width=3),
        dbc.Col([
            html.H6("AI Analysis", style={'color': COLORS['text_secondary'], 'fontSize': '0.75rem', 'textTransform': 'uppercase'}),
            html.Div([
                html.P([html.Strong("Confidence: "), html.Span(f"{confidence:.1f}%", style={'color': COLORS['blue'], 'fontWeight': 'bold'})], style={'margin': '4px 0'}),
                html.P([html.Strong("Status: "), html.Span(status, style={'color': COLORS['green'] if status == 'Approved' else COLORS['red']})], style={'margin': '4px 0'}),
                html.P([html.Strong("Outcome: "), html.Span(outcome, style={'color': outcome_color, 'fontWeight': 'bold', 'fontSize': '1.1rem'})], style={'margin': '4px 0'}),
            ])
        ], width=3),
        dbc.Col([
            html.H6("Risk Metrics", style={'color': COLORS['text_secondary'], 'fontSize': '0.75rem', 'textTransform': 'uppercase'}),
            html.Div([
                html.P([html.Strong("Risk/Reward: "), 
                       html.Span(f"1:{abs((tp-entry)/(entry-sl)):.1f}" if tp and sl and entry and entry != sl else "N/A")], 
                       style={'margin': '4px 0'}),
                html.P([html.Strong("Pips to SL: "), 
                       html.Span(f"{abs(entry-sl)*10000:.1f}" if entry and sl else "N/A")], 
                       style={'margin': '4px 0'}),
                html.P([html.Strong("Pips to TP: "), 
                       html.Span(f"{abs(tp-entry)*10000:.1f}" if tp and entry else "N/A")], 
                       style={'margin': '4px 0'}),
            ])
        ], width=3),
        dbc.Col([
            html.H6("Active Indicators", style={'color': COLORS['text_secondary'], 'fontSize': '0.75rem', 'textTransform': 'uppercase'}),
            html.Div([
                html.Span("SMA", className="badge me-1", style={'backgroundColor': COLORS['blue']}) if show_sma else None,
                html.Span("EMA", className="badge me-1", style={'backgroundColor': COLORS['blue']}) if show_ema else None,
                html.Span("RSI", className="badge me-1", style={'backgroundColor': COLORS['blue']}) if show_rsi else None,
                html.Span("BB", className="badge me-1", style={'backgroundColor': COLORS['blue']}) if show_bb else None,
                html.Span("Trend", className="badge me-1", style={'backgroundColor': COLORS['blue']}) if show_trendline else None,
            ])
        ], width=3),
    ])
    
    return fig, info_panel



# =============================================================================
# PERFORMANCE ANALYTICS CALLBACK
# =============================================================================
@app.callback(
    Output('analytics-container', 'children'),
    Input('stored-data', 'data'),
    Input('asset-filter', 'value'),
    Input('strategy-filter', 'value'),
    Input('status-filter', 'value'),
    Input('outcome-filter', 'value'), # <-- NEW INPUT
    Input('date-filter', 'start_date'),
    Input('date-filter', 'end_date'),
    Input('theme-store', 'data')
)
def update_analytics(data, assets, strategies, status, outcome_val, start_date, end_date, theme):
    """Generate performance charts for the analytics tab."""
    if not data:
        return html.Div("No data available.", style={'color': COLORS['text_secondary'], 'textAlign': 'center', 'padding': '40px'})
    
    df = pd.DataFrame(data)
    if df.empty:
        return html.Div("No data available.", style={'color': COLORS['text_secondary'], 'textAlign': 'center', 'padding': '40px'})
        
    df['Timestamp'] = pd.to_datetime(df['Timestamp'])
    
    # Apply the same filters so the charts match the table
    if assets:
        df = df[df['Asset_Symbol'].isin(assets)]
    if strategies:
        df = df[df['Strategy_Name'].isin(strategies)]
    if status and status != 'All':
        df = df[df['Status'] == status]
    if outcome_val and outcome_val != 'All':          # <-- APPLY NEW FILTER
        df = df[df['Outcome'] == outcome_val]         # <-- APPLY NEW FILTER
    if start_date and end_date:
        df = df[(df['Timestamp'].dt.date >= pd.to_datetime(start_date).date()) & 
                (df['Timestamp'].dt.date <= pd.to_datetime(end_date).date())]
                
    # ... KEEP THE REST OF YOUR GRAPH CODE THE SAME DOWN HERE ...
                
    # Filter for ONLY audited trades (Wins and Losses)
    audited_df = df[df['Outcome'].isin(['Win', 'Loss'])]
    
    if audited_df.empty:
        return html.Div([
            html.H4("Not Enough Data", style={'color': COLORS['text']}),
            html.P("There are no audited trades (Wins/Losses) matching your current filters.")
        ], style={'color': COLORS['text_secondary'], 'textAlign': 'center', 'padding': '40px'})
        
    # --- CHART 1: Performance by Strategy ---
    strat_df = audited_df.groupby(['Strategy_Name', 'Outcome']).size().unstack(fill_value=0).reset_index()
    # Ensure columns exist even if there are no wins or no losses
    for col in ['Win', 'Loss']:
        if col not in strat_df.columns: 
            strat_df[col] = 0
            
    chart_theme = get_plotly_theme(theme)
    fig_strat = go.Figure(data=[
        go.Bar(name='Wins', x=strat_df['Strategy_Name'], y=strat_df['Win'], marker_color=chart_theme['success']),
        go.Bar(name='Losses', x=strat_df['Strategy_Name'], y=strat_df['Loss'], marker_color=chart_theme['danger'])
    ])
    fig_strat.update_layout(
        title="Win/Loss by Strategy",
        template=chart_theme['template'],
        paper_bgcolor=chart_theme['paper_bgcolor'],
        plot_bgcolor=chart_theme['plot_bgcolor'],
        font=dict(color=chart_theme['font_color']),
        barmode='group',
        margin=dict(l=20, r=20, t=50, b=20)
    )
    
    # --- CHART 2: Performance by Asset ---
    asset_df = audited_df.groupby(['Asset_Symbol', 'Outcome']).size().unstack(fill_value=0).reset_index()
    for col in ['Win', 'Loss']:
        if col not in asset_df.columns: 
            asset_df[col] = 0
            
    fig_asset = go.Figure(data=[
        go.Bar(name='Wins', x=asset_df['Asset_Symbol'], y=asset_df['Win'], marker_color=chart_theme['success']),
        go.Bar(name='Losses', x=asset_df['Asset_Symbol'], y=asset_df['Loss'], marker_color=chart_theme['danger'])
    ])
    fig_asset.update_layout(
        title="Win/Loss by Asset",
        template=chart_theme['template'],
        paper_bgcolor=chart_theme['paper_bgcolor'],
        plot_bgcolor=chart_theme['plot_bgcolor'],
        font=dict(color=chart_theme['font_color']),
        barmode='group',
        margin=dict(l=20, r=20, t=50, b=20)
    )

    # Return the charts wrapped in a responsive Bootstrap row
    return dbc.Row([
        dbc.Col(
            dbc.Card(dbc.CardBody(dcc.Graph(figure=fig_strat, config={'displayModeBar': False})), 
                     style={'backgroundColor': COLORS['card_bg'], 'borderColor': COLORS['border']}), 
            width=6
        ),
        dbc.Col(
            dbc.Card(dbc.CardBody(dcc.Graph(figure=fig_asset, config={'displayModeBar': False})), 
                     style={'backgroundColor': COLORS['card_bg'], 'borderColor': COLORS['border']}), 
            width=6
        )
    ])

@app.callback(
    Output('audit-modal', 'is_open'),
    Output('audit-modal-body', 'children'),
    Input('metric-audited', 'n_clicks'),
    Input('close-audit-modal', 'n_clicks'),
    Input('theme-store', 'data'),
    State('audit-modal', 'is_open'),
    State('stored-data', 'data'),
    prevent_initial_call=True
)
def open_audit_modal(n1, n2, theme, is_open, data):
    ctx = dash.callback_context
    if not ctx.triggered:
        return is_open, dash.no_update
        
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    if trigger_id == 'close-audit-modal':
        return False, dash.no_update
        
    if trigger_id == 'metric-audited' and data:
        df = pd.DataFrame(data)
        audited_df = df[df['Outcome'].isin(['Win','Loss'])]
        
        if audited_df.empty:
            return True, html.Div("No audited data available to chart.", style={'color': COLORS['text']})
            
        # Strategy Chart
        strat_df = audited_df.groupby(['Strategy_Name', 'Outcome']).size().unstack(fill_value=0).reset_index()
        for col in ['Win', 'Loss']:
            if col not in strat_df.columns: strat_df[col] = 0
                
        chart_theme = get_plotly_theme(theme)
        fig_strat = go.Figure(data=[
            go.Bar(name='Wins', x=strat_df['Strategy_Name'], y=strat_df['Win'], marker_color=chart_theme['success']),
            go.Bar(name='Losses', x=strat_df['Strategy_Name'], y=strat_df['Loss'], marker_color=chart_theme['danger'])
        ])
        fig_strat.update_layout(
            title="Win/Loss by Strategy",
            template=chart_theme['template'],
            paper_bgcolor=chart_theme['paper_bgcolor'],
            plot_bgcolor=chart_theme['plot_bgcolor'],
            font=dict(color=chart_theme['font_color']),
            barmode='group'
        )
        
        # Asset Chart
        asset_df = audited_df.groupby(['Asset_Symbol', 'Outcome']).size().unstack(fill_value=0).reset_index()
        for col in ['Win', 'Loss']:
            if col not in asset_df.columns: asset_df[col] = 0
                
        fig_asset = go.Figure(data=[
            go.Bar(name='Wins', x=asset_df['Asset_Symbol'], y=asset_df['Win'], marker_color=chart_theme['success']),
            go.Bar(name='Losses', x=asset_df['Asset_Symbol'], y=asset_df['Loss'], marker_color=chart_theme['danger'])
        ])
        fig_asset.update_layout(
            title="Win/Loss by Asset",
            template=chart_theme['template'],
            paper_bgcolor=chart_theme['paper_bgcolor'],
            plot_bgcolor=chart_theme['plot_bgcolor'],
            font=dict(color=chart_theme['font_color']),
            barmode='group'
        )
        
        return True, dbc.Row([
            dbc.Col(dcc.Graph(figure=fig_strat), width=6), 
            dbc.Col(dcc.Graph(figure=fig_asset), width=6)
        ])
        
    return is_open, dash.no_update


# =============================================================================
# STORY 4 – EXPORT CALLBACK
# =============================================================================
@app.callback(
    Output('download-csv', 'data'),
    Output('download-excel', 'data'),
    Input('btn-csv', 'n_clicks'),
    Input('btn-excel', 'n_clicks'),
    State('stored-data', 'data'),
    State('asset-filter', 'value'),
    State('strategy-filter', 'value'),
    State('status-filter', 'value'),
    State('outcome-filter', 'value'),
    State('date-filter', 'start_date'),
    State('date-filter', 'end_date'),
    State('pips-toggle', 'value'),
    prevent_initial_call=True
)
def export_table(n_csv, n_excel, data, assets, strategies, status, outcome_val, start_date, end_date, pips_mode):
    """Export current filtered table as CSV or Excel."""
    if not data:
        return dash.no_update, dash.no_update
    
    df = pd.DataFrame(data)
    if df.empty:
        return dash.no_update, dash.no_update
    
    df['Timestamp'] = pd.to_datetime(df['Timestamp'])
    
    # Apply the exact same filters as the table
    if assets: df = df[df['Asset_Symbol'].isin(assets)]
    if strategies: df = df[df['Strategy_Name'].isin(strategies)]
    if status and status != 'All': df = df[df['Status'] == status]
    if outcome_val and outcome_val != 'All': df = df[df['Outcome'] == outcome_val]
    if start_date and end_date:
        df = df[(df['Timestamp'].dt.date >= pd.to_datetime(start_date).date()) &
                (df['Timestamp'].dt.date <= pd.to_datetime(end_date).date())]
    
    # Re-calculate RR & Pips with current toggle
    def calc_pips_rr(row, mode):
        e = row.get('Entry_Price')
        sl = row.get('Stop_Loss')
        tp = row.get('Take_Profit')
        if pd.isna(e) or pd.isna(sl) or pd.isna(tp): return None, "N/A"
        gross_tp = abs((tp - e) * 10000)
        gross_sl = abs((e - sl) * 10000)
        if mode == 'net':
            pips = round(gross_tp - 1.5, 1)
            rr = round((gross_tp - 1.5) / (gross_sl + 1.5), 2) if gross_sl > 0 else None
        else:
            pips = round(gross_tp, 1)
            rr = round(gross_tp / gross_sl, 2) if gross_sl > 0 else None
        return pips, f"1:{rr}" if rr else "N/A"
    
    df['Pips_Targeted'] = df.apply(lambda r: calc_pips_rr(r, pips_mode)[0], axis=1)
    df['RR'] = df.apply(lambda r: calc_pips_rr(r, pips_mode)[1], axis=1)
    
    # Clean columns for export
    export_df = df[['Timestamp', 'Asset_Symbol', 'Strategy_Name', 'Signal_Value',
                    'Entry_Price', 'Stop_Loss', 'Take_Profit', 'RR', 'Pips_Targeted',
                    'Confidence_Score', 'Status', 'Outcome']].copy()
    
    ctx = dash.callback_context
    triggered = ctx.triggered[0]['prop_id'].split('.')[0]
    
    if triggered == 'btn-csv':
        csv_string = export_df.to_csv(index=False)
        return dict(content=csv_string, filename=f"forex_trades_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"), dash.no_update
    
    elif triggered == 'btn-excel':
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            export_df.to_excel(writer, index=False, sheet_name='Trades')
        excel_bytes = output.getvalue()
        filename = f"forex_trades_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        return dash.no_update, dcc.send_bytes(excel_bytes, filename)
    
    return dash.no_update, dash.no_update


# =============================================================================
# STORY 5 – LIVE CLOCK + MARKET HOURS WIDGET
# =============================================================================
# =============================================================================
# STORY 5 – LIVE CLOCK + MARKET HOURS WIDGET
# =============================================================================
@app.callback(
    Output('live-datetime', 'children'),
    Output('market-sessions-widget', 'children'),
    Output('current-utc-time', 'data'),
    Output('overlap-badge', 'children'),
    Input('live-clock-interval', 'n_intervals'),
    Input('theme-store', 'data')
)
def update_live_clock(n, theme):
    """Live clock (multi-timezone) + full-width market hours."""
    now_utc = datetime.now(ZoneInfo("UTC"))
    chart_theme = get_plotly_theme(theme)
    label_color = '#0369a1' if theme == 'light' else '#00b4d8'
    time_color = chart_theme['font_color']
    muted_color = chart_theme['muted_text']
    sep_color = '#94a3b8' if theme == 'light' else '#333'

    def fmt(tz_name, label, abbr):
        t = now_utc.astimezone(ZoneInfo(tz_name))
        return html.Span([
            html.Span(label, style={'color': label_color, 'fontWeight': '600', 'marginRight': '4px'}),
            html.Span(t.strftime('%H:%M:%S'), style={'color': time_color}),
            html.Span(f" {abbr}", style={'color': muted_color, 'fontSize': '0.75rem'})
        ])

    sep = html.Span("  |  ", style={'color': sep_color, 'margin': '0 6px'})
    current_time_str = html.Div([
        fmt("Europe/London",   "LON",    "GMT/BST"), sep,
        fmt("America/New_York","NY",     "EST/EDT"), sep,
        fmt("Asia/Tokyo",      "TYO",   "JST"),     sep,
        fmt("Australia/Sydney","SYD",   "AEDT"),    sep,
        fmt("UTC",             "UTC",   ""),
    ], style={'display': 'flex', 'alignItems': 'center', 'flexWrap': 'wrap', 'gap': '2px'})

    fig = create_market_hours_fig(now_utc.replace(tzinfo=None), theme=theme)
    widget = dcc.Graph(figure=fig, config={'displayModeBar': False})
    overlap_badge = html.Span("")

    return current_time_str, widget, now_utc.isoformat(), overlap_badge


@app.callback(
    Output('session-modal', 'is_open'),
    Output('session-modal-header', 'children'),
    Output('session-modal-body', 'children'),
    Input({'type': 'session-btn', 'index': ALL}, 'n_clicks'),
    Input('close-session-modal', 'n_clicks'),  
    State('session-modal', 'is_open'),
    prevent_initial_call=True
)
def show_session_details(n_clicks_list, close_clicks, is_open):
    ctx = dash.callback_context
    if not ctx.triggered: 
        return is_open, dash.no_update, dash.no_update
        
    trigger_id = ctx.triggered[0]['prop_id']
    
    # 1. Check if the close button was clicked
    if 'close-session-modal' in trigger_id:
        return False, dash.no_update, dash.no_update
        
    # --- THE FIX ---
    # 2. Prevent the infinite loop: If buttons were re-rendered by the 1-second clock, 
    # their n_clicks will be 0 or None. Do nothing.
    if all(click is None or click == 0 for click in n_clicks_list):
        return dash.no_update, dash.no_update, dash.no_update
        
    # 3. Otherwise, a session button was actually clicked. 
    import json
    try:
        prop_dict = json.loads(trigger_id.split('.')[0])
        session_name = prop_dict['index']
    except:
        session_name = "Unknown"
        
    return True, f"{session_name} Session Details", html.Div([
        html.P("Open: 00:00 UTC", style={'color': COLORS['green']}),
        html.P("Close: 09:00 UTC", style={'color': COLORS['red']}),
        html.P("Current overlap status: Active", style={'color': '#F39C12', 'fontWeight': 'bold'})
    ])


# =============================================================================
# STORY 6 – MODEL HEALTH AUDIT MODAL (PDF-based)
# =============================================================================
@app.callback(
    Output('model-audit-modal', 'is_open'),
    Output('model-audit-body', 'children'),
    Output('audit-header', 'children'),
    Input('health-card', 'n_clicks'),
    Input('close-model-audit', 'n_clicks'),
    Input('theme-store', 'data'),
    State('model-audit-modal', 'is_open'),
    State('stored-data', 'data'),
    prevent_initial_call=True
)
def open_model_audit(n1, n2, theme, is_open, data):
    ctx = dash.callback_context
    if ctx.triggered[0]['prop_id'] == 'close-model-audit.n_clicks':
        return False, dash.no_update, dash.no_update
    
    if not data:
        return True, html.Div("No data yet", style={'color': COLORS['red']}), "Model Audit"
    
    df = pd.DataFrame(data)
    audited = df[df['Outcome'].isin(['Win', 'Loss'])]
    
    if audited.empty:
        return True, html.Div("Not enough audited trades for full audit", style={'color': COLORS['red']}), "Model Audit"

    calc_cols = ['Entry_Price', 'Take_Profit', 'Stop_Loss']
    audited_calc = audited.dropna(subset=calc_cols).copy()
    if audited_calc.empty:
        return True, html.Div("Not enough priced audited trades for full audit", style={'color': COLORS['red']}), "Model Audit"

    for col in calc_cols:
        audited_calc[col] = pd.to_numeric(audited_calc[col], errors='coerce')
    audited_calc = audited_calc.dropna(subset=calc_cols)
    if audited_calc.empty:
        return True, html.Div("Not enough valid priced audited trades for full audit", style={'color': COLORS['red']}), "Model Audit"

    winners = audited_calc[audited_calc['Outcome'] == 'Win'].copy()
    losers = audited_calc[audited_calc['Outcome'] == 'Loss'].copy()
    if winners.empty or losers.empty:
        return True, html.Div("Need at least one priced win and one priced loss for full audit", style={'color': COLORS['red']}), "Model Audit"

    winners['reward_dist'] = (winners['Take_Profit'] - winners['Entry_Price']).abs()
    losers['risk_dist'] = (losers['Entry_Price'] - losers['Stop_Loss']).abs()

    avg_reward = winners['reward_dist'].replace([float('inf'), -float('inf')], pd.NA).dropna().mean()
    avg_risk = losers['risk_dist'].replace([float('inf'), -float('inf')], pd.NA).dropna().mean()
    if pd.isna(avg_reward) or pd.isna(avg_risk) or avg_risk <= 0:
        return True, html.Div("Unable to compute empirical RR from current audited trades", style={'color': COLORS['red']}), "Model Audit"

    empirical_rr = float(avg_reward / avg_risk)

    win_count = len(winners)
    loss_count = len(losers)
    total_count = win_count + loss_count
    win_rate_dec = (win_count / total_count) if total_count > 0 else 0
    win_rate = round(win_rate_dec * 100, 1)

    total_profit_dist = winners['reward_dist'].sum()
    total_loss_dist = losers['risk_dist'].sum()
    profit_factor = round(total_profit_dist / total_loss_dist, 2) if total_loss_dist > 0 else 0

    kelly_raw = ((win_rate_dec * empirical_rr) - (1 - win_rate_dec)) / empirical_rr if empirical_rr > 0 else 0
    kelly = round(kelly_raw, 3)
    fractional_kelly = round(kelly_raw * 0.25, 3)

    break_even_wr = (1 / (1 + empirical_rr)) * 100
    target_wr = min(100.0, break_even_wr + 5.0)

    matrix = dbc.Table([
        html.Thead(html.Tr([
            html.Th("Metric"),
            html.Th("Value")
        ])),
        html.Tbody([
            html.Tr([html.Td("Empirical Average Net RR"), html.Td(f"1:{empirical_rr:.2f}")]),
            html.Tr([html.Td("Break-Even Win Rate"), html.Td(f"{break_even_wr:.1f}%")]),
            html.Tr([html.Td("Current Win Rate"), html.Td(f"{win_rate:.1f}%")]),
        ])
    ], bordered=True, striped=True, hover=True, responsive=True, size='sm', className='table-dark')

    chart_theme = get_plotly_theme(theme)
    wr_compare_fig = go.Figure(data=[
        go.Bar(
            x=['Current Win Rate', 'Target Win Rate'],
            y=[win_rate, target_wr],
            marker_color=[chart_theme['success'], chart_theme['info']]
        )
    ])
    wr_compare_fig.update_layout(
        title='Current vs Target Win Rate',
        template=chart_theme['template'],
        paper_bgcolor=chart_theme['paper_bgcolor'],
        plot_bgcolor=chart_theme['plot_bgcolor'],
        font=dict(color=chart_theme['font_color']),
        yaxis=dict(title='Win Rate (%)', range=[0, 100]),
        margin=dict(l=20, r=20, t=50, b=20)
    )
    
    body = dbc.Row([
        dbc.Col([
            html.H5("Current Performance", style={'color': chart_theme['success']}),
            html.P(f"Profit Factor: {profit_factor}"),
            html.P(f"Win Rate: {win_rate}%"),
            html.P(f"Kelly Fraction: {kelly}"),
            html.P(f"Recommended Kelly (safe 1/4): {fractional_kelly}"),
            html.Hr(),
            html.H6("Empirical Win-Rate Metrics", style={'color': COLORS['text_secondary']}),
            matrix
        ], width=6),
        dbc.Col([
            html.H5("Model Diagnostics", style={'color': chart_theme['danger']}),
            html.P("Data Source: ForexBrainDB – Fact_Live_Trades"),
            html.P(f"Last Update: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}"),
            html.P("Target Win Rate is dynamically set to Break-Even + 5% safety buffer."),
            dcc.Graph(figure=wr_compare_fig)
        ], width=6)
    ])
    
    return True, body, "Model Health Audit – Full Diagnostics"

# =============================================================================
# STORY 7 – LIVE TELEMETRY GAUGES
# =============================================================================
@app.callback(
    Output('approval-gauge', 'figure'),
    Output('confidence-progress', 'value'),
    Input('auto-refresh', 'n_intervals'),  # re-uses your existing 5-min refresh
    Input('theme-store', 'data')
)
def update_live_gauges(n, theme):
    """Live gauges for Approval Rate and Avg Confidence."""
    df = load_data()
    if df.empty:
        return go.Figure(), 0
    
    approval_rate = (df['Is_Approved'].sum() / len(df) * 100) if len(df) > 0 else 0
    avg_conf = df['Confidence_Score'].mean() if not df.empty else 0
    chart_theme = get_plotly_theme(theme)
    low_band = 'rgba(185,28,28,0.18)' if theme == 'light' else 'rgba(255,77,77,0.2)'
    high_band = 'rgba(21,128,61,0.20)' if theme == 'light' else 'rgba(0,196,140,0.2)'
    
    # Approval Rate Gauge
    gauge_fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=approval_rate,
        title={'text': "Approval Rate"},
        gauge={
            'axis': {'range': [0, 100]},
            'bar': {'color': chart_theme['success']},
            'steps': [{'range': [0, 50], 'color': low_band},
                      {'range': [50, 100], 'color': high_band}],
            'threshold': {'line': {'color': "#1f2937" if theme == 'light' else "white", 'width': 4}, 'thickness': 0.75, 'value': approval_rate}
        }
    ))
    gauge_fig.update_layout(
        height=90,
        margin=dict(l=0, r=0, t=0, b=0),
        template=chart_theme['template'],
        paper_bgcolor='rgba(0,0,0,0)',
        font=dict(color=chart_theme['font_color'])
    )
    
    return gauge_fig, round(avg_conf)

# =============================================================================
# =============================================================================
# THEME SWITCHER – clientside callback
# =============================================================================
app.clientside_callback(
    """
    function(n_clicks, current_theme) {
        if (!n_clicks) return window.dash_clientside.no_update;
        var new_theme = (current_theme === 'dark') ? 'light' : 'dark';

        var darkLink  = document.querySelector('link[href*="darkly"]');
        var lightLink = document.getElementById('theme-light');

        if (new_theme === 'light') {
            if (darkLink)  darkLink.disabled  = true;
            if (lightLink) lightLink.disabled = false;
            document.body.setAttribute('data-theme', 'light');
        } else {
            if (darkLink)  darkLink.disabled  = false;
            if (lightLink) lightLink.disabled = true;
            document.body.setAttribute('data-theme', 'dark');
        }
        return new_theme;
    }
    """,
    Output('theme-store', 'data'),
    Input('theme-toggle', 'n_clicks'),
    State('theme-store', 'data'),
    prevent_initial_call=True
)

app.clientside_callback(
    """
    function(theme) {
        var activeTheme = theme || 'dark';
        var darkLink  = document.querySelector('link[href*="darkly"]');
        var lightLink = document.getElementById('theme-light');

        if (activeTheme === 'light') {
            if (darkLink)  darkLink.disabled  = true;
            if (lightLink) lightLink.disabled = false;
            document.body.setAttribute('data-theme', 'light');
        } else {
            if (darkLink)  darkLink.disabled  = false;
            if (lightLink) lightLink.disabled = true;
            document.body.setAttribute('data-theme', 'dark');
        }
        return '';
    }
    """,
    Output('theme-sync', 'children'),
    Input('theme-store', 'data')
)

@app.callback(
    Output('theme-toggle', 'children'),
    Output('theme-toggle', 'style'),
    Input('theme-store', 'data')
)
def update_toggle_label(theme):
    if theme == 'light':
        return [html.Span("🌙", style={'marginRight': '5px'}), "Dark"], {'color': '#374151'}
    return [html.Span("☀", style={'marginRight': '5px'}), "Light"], {'color': '#a0aec0'}


# =============================================================================
# RUN APPLICATION
# =============================================================================

if __name__ == '__main__':
    app.run(debug=True, port=8050)