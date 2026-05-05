#!/bin/bash
# =============================================================================
# Advanced Charting System Installation Script
# =============================================================================
# This script automates the installation of the Advanced Charting System
# for the Scalable Brain trading platform.
#
# Usage:
#   chmod +x install_advanced_charts.sh
#   ./install_advanced_charts.sh
#
# Or with options:
#   ./install_advanced_charts.sh --skip-db --skip-verify
# =============================================================================

set -e  # Exit on any error

# =============================================================================
# Configuration
# =============================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
UPGRADE_DIR="${PROJECT_ROOT}/newplannedlayer5upgrade/layer5_upgrade"
FRONTEND_DIR="${PROJECT_ROOT}/src/layer5/frontend"
BACKUP_DIR="${PROJECT_ROOT}/backups/$(date +%Y%m%d_%H%M%S)"

# Flags
SKIP_DB=false
SKIP_VERIFY=false
SKIP_FRONTEND=false
SKIP_BACKEND=false

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# =============================================================================
# Utility Functions
# =============================================================================

print_header() {
    echo ""
    echo -e "${CYAN}═══════════════════════════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}  $1${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════════════════════════════${NC}"
    echo ""
}

print_step() {
    echo -e "${BLUE}▶${NC} $1"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_info() {
    echo -e "${CYAN}ℹ${NC} $1"
}

backup_file() {
    local file="$1"
    if [ -f "$file" ]; then
        mkdir -p "$BACKUP_DIR"
        cp "$file" "${BACKUP_DIR}/$(basename "$file")"
        print_warning "Backed up: $file"
    fi
}

backup_dir() {
    local dir="$1"
    if [ -d "$dir" ]; then
        mkdir -p "$BACKUP_DIR"
        cp -r "$dir" "${BACKUP_DIR}/$(basename "$dir")"
        print_warning "Backed up directory: $dir"
    fi
}

# =============================================================================
# Argument Parsing
# =============================================================================

parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --skip-db)
                SKIP_DB=true
                shift
                ;;
            --skip-verify)
                SKIP_VERIFY=true
                shift
                ;;
            --skip-frontend)
                SKIP_FRONTEND=true
                shift
                ;;
            --skip-backend)
                SKIP_BACKEND=true
                shift
                ;;
            --help|-h)
                echo "Advanced Charting System Installation Script"
                echo ""
                echo "Usage: $0 [OPTIONS]"
                echo ""
                echo "Options:"
                echo "  --skip-db           Skip database migration"
                echo "  --skip-verify       Skip verification tests"
                echo "  --skip-frontend     Skip frontend installation"
                echo "  --skip-backend      Skip backend installation"
                echo "  --help, -h          Show this help message"
                echo ""
                exit 0
                ;;
            *)
                print_error "Unknown option: $1"
                exit 1
                ;;
        esac
    done
}

# =============================================================================
# Prerequisites Check
# =============================================================================

check_prerequisites() {
    print_header "Prerequisites Check"
    
    local has_errors=false
    
    # Check Python version
    print_step "Checking Python version..."
    if command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
        print_success "Python version: $PYTHON_VERSION"
        
        # Check if version is 3.11+
        if python3 -c "import sys; exit(0 if sys.version_info >= (3, 11) else 1)"; then
            print_success "Python version is 3.11+"
        else
            print_error "Python 3.11+ is required (found $PYTHON_VERSION)"
            has_errors=true
        fi
    elif command -v python &> /dev/null; then
        PYTHON_VERSION=$(python --version 2>&1 | awk '{print $2}')
        print_success "Python version: $PYTHON_VERSION"
    else
        print_error "Python is not installed"
        has_errors=true
    fi
    
    # Check Node.js version
    print_step "Checking Node.js version..."
    if command -v node &> /dev/null; then
        NODE_VERSION=$(node --version)
        print_success "Node.js version: $NODE_VERSION"
        
        # Extract major version
        NODE_MAJOR=$(echo $NODE_VERSION | cut -d'v' -f2 | cut -d'.' -f1)
        if [ "$NODE_MAJOR" -ge 18 ]; then
            print_success "Node.js version is 18+"
        else
            print_error "Node.js 18+ is required (found $NODE_VERSION)"
            has_errors=true
        fi
    else
        print_error "Node.js is not installed"
        has_errors=true
    fi
    
    # Check npm version
    print_step "Checking npm version..."
    if command -v npm &> /dev/null; then
        NPM_VERSION=$(npm --version)
        print_success "npm version: $NPM_VERSION"
    else
        print_error "npm is not installed"
        has_errors=true
    fi
    
    # Check if we're in the correct directory
    print_step "Checking project structure..."
    if [ ! -d "src/layer5" ]; then
        print_error "Project structure not found. Please run from project root."
        print_info "Expected: src/layer5 directory"
        has_errors=true
    else
        print_success "Project structure verified"
    fi
    
    # Check for upgrade files
    print_step "Checking upgrade files..."
    if [ ! -d "$UPGRADE_DIR" ]; then
        print_error "Upgrade files not found at: $UPGRADE_DIR"
        has_errors=true
    else
        print_success "Upgrade files found"
    fi
    
    # Check database connectivity (optional)
    print_step "Checking database connectivity..."
    if [ -f ".env" ]; then
        # Try to import pyodbc if available
        if python3 -c "import pyodbc" 2>/dev/null; then
            print_success "pyodbc is installed"
        else
            print_warning "pyodbc not installed (database connectivity may be limited)"
        fi
    fi
    
    if [ "$has_errors" = true ]; then
        print_error "Prerequisites check failed. Please install missing dependencies."
        exit 1
    fi
    
    print_success "All prerequisites met!"
    echo ""
}

# =============================================================================
# Python Dependencies Installation
# =============================================================================

install_python_deps() {
    print_header "Installing Python Dependencies"
    
    print_step "Activating virtual environment (if exists)..."
    if [ -d ".venv" ]; then
        source .venv/bin/activate 2>/dev/null || .venv/Scripts/activate 2>/dev/null
        print_success "Virtual environment activated"
    else
        print_warning "No virtual environment found at .venv"
    fi
    
    print_step "Installing numpy and pandas..."
    pip install -q numpy pandas
    print_success "numpy and pandas installed"
    
    print_step "Checking for existing dependencies..."
    pip show numpy pandas > /dev/null 2>&1 && print_success "Core dependencies verified"
    
    # Optional: Check for Redis
    print_step "Checking for Redis support..."
    if python3 -c "import redis" 2>/dev/null; then
        print_success "Redis client already installed"
    else
        print_info "Redis client not installed. Installing..."
        pip install -q redis
        print_success "Redis client installed"
    fi
    
    echo ""
}

# =============================================================================
# Backend Installation
# =============================================================================

install_backend() {
    print_header "Backend Installation"
    
    # Create necessary directories
    print_step "Creating backend directories..."
    mkdir -p src/layer5/api/routes
    mkdir -p src/layer5/services
    print_success "Directories created"
    
    # Copy API routes
    print_step "Installing new API routes..."
    
    if [ -f "${UPGRADE_DIR}/api/routes/charts.py" ]; then
        backup_file "src/layer5/api/routes/charts.py"
        cp "${UPGRADE_DIR}/api/routes/charts.py" src/layer5/api/routes/
        print_success "charts.py installed"
    fi
    
    if [ -f "${UPGRADE_DIR}/api/routes/indicators.py" ]; then
        backup_file "src/layer5/api/routes/indicators.py"
        cp "${UPGRADE_DIR}/api/routes/indicators.py" src/layer5/api/routes/
        print_success "indicators.py installed"
    fi
    
    if [ -f "${UPGRADE_DIR}/api/routes/alerts.py" ]; then
        backup_file "src/layer5/api/routes/alerts.py"
        cp "${UPGRADE_DIR}/api/routes/alerts.py" src/layer5/api/routes/
        print_success "alerts.py installed"
    fi
    
    # Copy services
    print_step "Installing new services..."
    
    if [ -f "${UPGRADE_DIR}/services/chart_data_client.py" ]; then
        backup_file "src/layer5/services/chart_data_client.py"
        cp "${UPGRADE_DIR}/services/chart_data_client.py" src/layer5/services/
        print_success "chart_data_client.py installed"
    fi
    
    if [ -f "${UPGRADE_DIR}/services/indicators_client.py" ]; then
        backup_file "src/layer5/services/indicators_client.py"
        cp "${UPGRADE_DIR}/services/indicators_client.py" src/layer5/services/
        print_success "indicators_client.py installed"
    fi
    
    if [ -f "${UPGRADE_DIR}/services/alerts_client.py" ]; then
        backup_file "src/layer5/services/alerts_client.py"
        cp "${UPGRADE_DIR}/services/alerts_client.py" src/layer5/services/
        print_success "alerts_client.py installed"
    fi
    
    # Update data_contracts.py if needed
    print_step "Updating data contracts..."
    if [ -f "${UPGRADE_DIR}/services/data_contracts.py" ]; then
        backup_file "src/layer5/services/data_contracts.py"
        cp "${UPGRADE_DIR}/services/data_contracts.py" src/layer5/services/
        print_success "data_contracts.py updated"
    fi
    
    # Update main.py
    print_step "Updating main.py..."
    if [ -f "${UPGRADE_DIR}/api/main.py" ]; then
        backup_file "src/layer5/api/main.py"
        cp "${UPGRADE_DIR}/api/main.py" src/layer5/api/main.py
        print_success "main.py updated"
    fi
    
    echo ""
}

# =============================================================================
# Frontend Installation
# =============================================================================

install_frontend() {
    print_header "Frontend Installation"
    
    # Check if frontend directory exists
    if [ ! -d "$FRONTEND_DIR" ]; then
        print_error "Frontend directory not found: $FRONTEND_DIR"
        exit 1
    fi
    
    cd "$FRONTEND_DIR"
    
    # Backup package.json
    print_step "Backing up package.json..."
    backup_file "package.json"
    
    # Install new dependencies
    print_step "Installing new npm dependencies..."
    print_info "This may take a few minutes..."
    
    # Install lightweight-charts
    npm install --silent lightweight-charts 2>&1 | grep -v "npm WARN" || true
    print_success "lightweight-charts installed"
    
    # Install theme support
    npm install --silent next-themes sonner 2>&1 | grep -v "npm WARN" || true
    print_success "next-themes and sonner installed"
    
    # Copy configuration files
    print_step "Copying configuration files..."
    
    if [ -f "${UPGRADE_DIR}/frontend/vite.config.ts" ]; then
        backup_file "vite.config.ts"
        cp "${UPGRADE_DIR}/frontend/vite.config.ts" .
        print_success "vite.config.ts updated"
    fi
    
    if [ -f "${UPGRADE_DIR}/frontend/tsconfig.json" ]; then
        backup_file "tsconfig.json"
        cp "${UPGRADE_DIR}/frontend/tsconfig.json" .
        print_success "tsconfig.json updated"
    fi
    
    if [ -f "${UPGRADE_DIR}/frontend/tailwind.config.js" ]; then
        backup_file "tailwind.config.js"
        cp "${UPGRADE_DIR}/frontend/tailwind.config.js" .
        print_success "tailwind.config.js updated"
    fi
    
    # Copy source files
    print_step "Copying source files..."
    
    # Create directories
    mkdir -p src/components/charts
    mkdir -p src/components/views
    mkdir -p src/components/layout
    mkdir -p src/hooks
    
    # Copy chart components
    if [ -d "${UPGRADE_DIR}/frontend/src/components/charts" ]; then
        backup_dir "src/components/charts"
        cp -r "${UPGRADE_DIR}/frontend/src/components/charts/"* src/components/charts/
        print_success "Chart components installed"
    fi
    
    # Copy view components
    if [ -d "${UPGRADE_DIR}/frontend/src/components/views" ]; then
        for file in "${UPGRADE_DIR}/frontend/src/components/views/"*.tsx; do
            if [ -f "$file" ]; then
                cp "$file" src/components/views/
            fi
        done
        print_success "View components installed"
    fi
    
    # Copy layout components
    if [ -f "${UPGRADE_DIR}/frontend/src/components/layout/ThemeToggle.tsx" ]; then
        cp "${UPGRADE_DIR}/frontend/src/components/layout/ThemeToggle.tsx" src/components/layout/
        print_success "ThemeToggle component installed"
    fi
    
    # Copy hooks
    if [ -f "${UPGRADE_DIR}/frontend/src/hooks/useTheme.tsx" ]; then
        cp "${UPGRADE_DIR}/frontend/src/hooks/useTheme.tsx" src/hooks/
        print_success "useTheme hook installed"
    fi
    
    # Copy services and types
    if [ -f "${UPGRADE_DIR}/frontend/src/services/api.ts" ]; then
        backup_file "src/services/api.ts"
        cp "${UPGRADE_DIR}/frontend/src/services/api.ts" src/services/
        print_success "API service updated"
    fi
    
    if [ -f "${UPGRADE_DIR}/frontend/src/types/index.ts" ]; then
        backup_file "src/types/index.ts"
        cp "${UPGRADE_DIR}/frontend/src/types/index.ts" src/types/
        print_success "Types updated"
    fi
    
    cd "$PROJECT_ROOT"
    echo ""
}

# =============================================================================
# Database Setup
# =============================================================================

setup_database() {
    print_header "Database Setup"
    
    if [ "$SKIP_DB" = true ]; then
        print_warning "Database migration skipped (--skip-db flag set)"
        echo ""
        return
    fi
    
    # Check if SQL Server tools are available
    if command -v sqlcmd &> /dev/null; then
        print_step "SQL Server tools found"
        
        # Create migration file
        MIGRATION_FILE="${PROJECT_ROOT}/migrations/004_advanced_charts.sql"
        mkdir -p "$(dirname "$MIGRATION_FILE")"
        
        cat > "$MIGRATION_FILE" << 'EOF'
/*
=============================================================================
Migration: Advanced Charting System
=============================================================================
*/

USE ForexBrainDB;
GO

-- Dim_Indicator_Library
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Dim_Indicator_Library')
BEGIN
    CREATE TABLE Dim_Indicator_Library (
        Indicator_ID INT PRIMARY KEY IDENTITY(1,1),
        Indicator_Name VARCHAR(50) NOT NULL UNIQUE,
        Category VARCHAR(20) NOT NULL CHECK (Category IN ('trend', 'momentum', 'volatility', 'volume')),
        Description VARCHAR(500),
        Default_Params NVARCHAR(MAX),
        Is_Active BIT DEFAULT 1,
        Created_At DATETIME DEFAULT GETDATE()
    );
    
    INSERT INTO Dim_Indicator_Library (Indicator_Name, Category, Description, Default_Params) VALUES
    ('sma', 'trend', 'Simple Moving Average', '{"period": 20}'),
    ('ema', 'trend', 'Exponential Moving Average', '{"period": 20}'),
    ('macd', 'trend', 'Moving Average Convergence Divergence', '{"fast": 12, "slow": 26, "signal": 9}'),
    ('adx', 'trend', 'Average Directional Index', '{"period": 14}'),
    ('rsi', 'momentum', 'Relative Strength Index', '{"period": 14, "overbought": 70, "oversold": 30}'),
    ('stochastic', 'momentum', 'Stochastic Oscillator', '{"kPeriod": 14, "dPeriod": 3}'),
    ('bollinger', 'volatility', 'Bollinger Bands', '{"period": 20, "stdDev": 2.0}'),
    ('atr', 'volatility', 'Average True Range', '{"period": 14}'),
    ('obv', 'volume', 'On-Balance Volume', '{}');
END
GO

-- Fact_Indicator_Values
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Fact_Indicator_Values')
BEGIN
    CREATE TABLE Fact_Indicator_Values (
        Value_ID BIGINT PRIMARY KEY IDENTITY(1,1),
        Timestamp DATETIME NOT NULL,
        Asset_ID INT NOT NULL,
        Indicator_ID INT NOT NULL,
        Timeframe VARCHAR(10) NOT NULL,
        Parameters NVARCHAR(MAX),
        Values_JSON NVARCHAR(MAX),
        Created_At DATETIME DEFAULT GETDATE(),
        CONSTRAINT FK_IndicatorValues_Asset FOREIGN KEY (Asset_ID) REFERENCES Dim_Asset(Asset_ID),
        CONSTRAINT FK_IndicatorValues_Indicator FOREIGN KEY (Indicator_ID) REFERENCES Dim_Indicator_Library(Indicator_ID)
    );
    
    CREATE INDEX IX_IndicatorValues_Lookup ON Fact_Indicator_Values(Asset_ID, Indicator_ID, Timeframe, Timestamp);
END
GO

-- Fact_Analysis_Metrics
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Fact_Analysis_Metrics')
BEGIN
    CREATE TABLE Fact_Analysis_Metrics (
        Metric_ID BIGINT PRIMARY KEY IDENTITY(1,1),
        Timestamp DATETIME NOT NULL,
        Asset_ID INT NOT NULL,
        Metric_Type VARCHAR(20) NOT NULL CHECK (Metric_Type IN ('correlation', 'volatility', 'strength', 'momentum')),
        Period VARCHAR(10) NOT NULL,
        Value FLOAT NOT NULL,
        Unit VARCHAR(20),
        Signal VARCHAR(10),
        Threshold FLOAT,
        Created_At DATETIME DEFAULT GETDATE(),
        CONSTRAINT FK_AnalysisMetrics_Asset FOREIGN KEY (Asset_ID) REFERENCES Dim_Asset(Asset_ID)
    );
    
    CREATE INDEX IX_AnalysisMetrics_Lookup ON Fact_Analysis_Metrics(Asset_ID, Metric_Type, Period, Timestamp);
END
GO

-- Dim_Alert_Configs
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Dim_Alert_Configs')
BEGIN
    CREATE TABLE Dim_Alert_Configs (
        Alert_ID VARCHAR(50) PRIMARY KEY,
        Name VARCHAR(100) NOT NULL,
        Alert_Type VARCHAR(20) NOT NULL,
        Asset_ID INT NOT NULL,
        Condition_Type VARCHAR(20) NOT NULL,
        Target_Value FLOAT NOT NULL,
        Timeframe VARCHAR(10) DEFAULT '1h',
        Status VARCHAR(20) DEFAULT 'active',
        Created_At DATETIME DEFAULT GETDATE(),
        CONSTRAINT FK_Alerts_Asset FOREIGN KEY (Asset_ID) REFERENCES Dim_Asset(Asset_ID)
    );
    
    CREATE INDEX IX_Alerts_Status ON Dim_Alert_Configs(Status);
END
GO

PRINT 'Advanced Charting System tables created successfully.';
EOF
        
        print_success "Migration file created: $MIGRATION_FILE"
        print_info "To apply migration manually, run:"
        print_info "  sqlcmd -S localhost -U sa -P your_password -i $MIGRATION_FILE"
        
    else
        print_warning "SQL Server tools (sqlcmd) not found"
        print_info "Please run the migration script manually from SQL Server Management Studio"
    fi
    
    echo ""
}

# =============================================================================
# Environment Setup
# =============================================================================

setup_environment() {
    print_header "Environment Setup"
    
    print_step "Checking .env file..."
    
    if [ -f ".env" ]; then
        # Check if advanced charting config already exists
        if grep -q "CHART_MAX_CANDLES" .env; then
            print_info "Advanced charting configuration already exists in .env"
        else
            print_step "Adding advanced charting configuration to .env..."
            
            cat >> .env << 'EOF'

# ==========================================
# Advanced Charting Configuration
# ==========================================
CHART_MAX_CANDLES=5000
CHART_DEFAULT_LIMIT=500
CHART_CACHE_TTL=300
INDICATOR_MAX_PERIOD=200
INDICATOR_CACHE_ENABLED=true
ALERTS_ENABLED=true
ALERTS_CHECK_INTERVAL=30
DEFAULT_THEME=dark
REDIS_ENABLED=false
EOF
            print_success "Configuration added to .env"
        fi
    else
        print_warning ".env file not found"
        print_info "Creating template .env file..."
        
        cat > .env.template << 'EOF'
# ==========================================
# Database Configuration
# ==========================================
DB_SERVER=localhost
DB_USER=sa
DB_PASS=your_password
DB_NAME=ForexBrainDB
DB_PORT=1433

# ==========================================
# OANDA API Configuration
# ==========================================
OANDA_API_KEY=your_api_key_here
OANDA_ACCOUNT_ID=your_account_id_here
OANDA_ENV=practice
OANDA_URL=https://api-fxpractice.oanda.com

# ==========================================
# Advanced Charting Configuration
# ==========================================
CHART_MAX_CANDLES=5000
CHART_DEFAULT_LIMIT=500
CHART_CACHE_TTL=300
INDICATOR_MAX_PERIOD=200
INDICATOR_CACHE_ENABLED=true
ALERTS_ENABLED=true
ALERTS_CHECK_INTERVAL=30
DEFAULT_THEME=dark
REDIS_ENABLED=false
EOF
        print_success ".env.template created. Please copy to .env and configure."
    fi
    
    echo ""
}

# =============================================================================
# Directory Setup
# =============================================================================

setup_directories() {
    print_header "Creating Directories"
    
    local dirs=(
        "src/layer5/api/routes"
        "src/layer5/services"
        "src/layer5/frontend/src/components/charts"
        "src/layer5/frontend/src/workers"
        "logs"
        "migrations"
    )
    
    for dir in "${dirs[@]}"; do
        if [ ! -d "$dir" ]; then
            mkdir -p "$dir"
            print_success "Created: $dir"
        fi
    done
    
    echo ""
}

# =============================================================================
# Verification
# =============================================================================

verify_installation() {
    if [ "$SKIP_VERIFY" = true ]; then
        print_warning "Verification skipped (--skip-verify flag set)"
        return
    fi
    
    print_header "Verification"
    
    local has_errors=false
    
    # Verify backend files
    print_step "Verifying backend files..."
    
    BACKEND_FILES=(
        "src/layer5/api/routes/charts.py"
        "src/layer5/api/routes/indicators.py"
        "src/layer5/api/routes/alerts.py"
        "src/layer5/services/chart_data_client.py"
        "src/layer5/services/indicators_client.py"
        "src/layer5/services/alerts_client.py"
    )
    
    for file in "${BACKEND_FILES[@]}"; do
        if [ -f "$file" ]; then
            print_success "$file"
        else
            print_error "$file (missing)"
            has_errors=true
        fi
    done
    
    # Verify frontend files
    print_step "Verifying frontend files..."
    
    FRONTEND_FILES=(
        "src/layer5/frontend/src/components/charts/TradingChart.tsx"
        "src/layer5/frontend/src/components/charts/IndicatorPanel.tsx"
        "src/layer5/frontend/src/hooks/useTheme.tsx"
    )
    
    for file in "${FRONTEND_FILES[@]}"; do
        if [ -f "$file" ]; then
            print_success "$file"
        else
            print_error "$file (missing)"
            has_errors=true
        fi
    done
    
    # Verify Python imports
    print_step "Verifying Python imports..."
    
    if python3 -c "
import sys
sys.path.insert(0, 'src')
try:
    from layer5.services.indicators_client import calculate_indicator
    from layer5.services.chart_data_client import get_ohlc_data
    print('Imports successful')
except Exception as e:
    print(f'Import error: {e}')
    sys.exit(1)
" 2>/dev/null; then
        print_success "Python imports working"
    else
        print_warning "Python import verification failed (may need PYTHONPATH setup)"
    fi
    
    # Verify npm packages
    print_step "Verifying npm packages..."
    
    cd "$FRONTEND_DIR"
    
    if npm list lightweight-charts > /dev/null 2>&1; then
        print_success "lightweight-charts package installed"
    else
        print_warning "lightweight-charts package not found"
    fi
    
    cd "$PROJECT_ROOT"
    
    # Summary
    echo ""
    if [ "$has_errors" = true ]; then
        print_warning "Some files are missing. Check the errors above."
    else
        print_success "Installation verification completed!"
    fi
    
    echo ""
}

# =============================================================================
# Print Summary
# =============================================================================

print_summary() {
    print_header "Installation Complete!"
    
    echo -e "${GREEN}The Advanced Charting System has been installed successfully!${NC}"
    echo ""
    echo -e "${BOLD}Next Steps:${NC}"
    echo ""
    echo "1. Start the backend server:"
    echo -e "   ${CYAN}python src/layer5/run.py${NC}"
    echo ""
    echo "2. Start the frontend development server:"
    echo -e "   ${CYAN}cd src/layer5/frontend && npm run dev${NC}"
    echo ""
    echo "3. Open your browser and navigate to:"
    echo -e "   ${CYAN}http://localhost:5173${NC}"
    echo ""
    echo -e "${BOLD}New Features Available:${NC}"
    echo "  • Charts view with 13 timeframes"
    echo "  • 30+ technical indicators (SMA, EMA, RSI, MACD, etc.)"
    echo "  • Volume profile analysis"
    echo "  • Support/resistance auto-detection"
    echo "  • Alert system for price and indicator notifications"
    echo "  • Dark/Light theme system"
    echo ""
    echo -e "${BOLD}Backup Location:${NC}"
    echo "  All original files backed up to: $BACKUP_DIR"
    echo ""
    echo -e "${BOLD}Documentation:${NC}"
    echo "  • INSTALL_ADVANCED_CHARTS.md - Full installation guide"
    echo "  • UPGRADE_SUMMARY.md - Feature overview"
    echo "  • API docs: http://localhost:8001/docs (when server is running)"
    echo ""
    echo -e "${YELLOW}Note:${NC} If you encounter any issues, check the backup directory"
    echo "      to restore original files."
    echo ""
}

# =============================================================================
# Main Script
# =============================================================================

main() {
    # Print banner
    echo ""
    echo -e "${CYAN}╔════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║${NC}                                                                ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}  ${BOLD}Advanced Charting System Installation${NC}                         ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}  Scalable Brain Trading Platform                                ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}                                                                ${CYAN}║${NC}"
    echo -e "${CYAN}╚════════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    
    # Parse arguments
    parse_args "$@"
    
    # Change to project root
    cd "$PROJECT_ROOT"
    
    # Run installation steps
    check_prerequisites
    setup_directories
    
    if [ "$SKIP_BACKEND" = false ]; then
        install_python_deps
        install_backend
    else
        print_warning "Backend installation skipped (--skip-backend flag set)"
    fi
    
    if [ "$SKIP_FRONTEND" = false ]; then
        install_frontend
    else
        print_warning "Frontend installation skipped (--skip-frontend flag set)"
    fi
    
    setup_database
    setup_environment
    verify_installation
    print_summary
}

# Run main function
main "$@"
