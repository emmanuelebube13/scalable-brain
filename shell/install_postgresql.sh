#!/bin/bash
# PostgreSQL Installation Script for Ubuntu/Debian
# Run: chmod +x install_postgresql.sh && ./install_postgresql.sh

echo "======================================================"
echo "Installing PostgreSQL 16 + TimescaleDB Extension"
echo "======================================================"

# Update package list
echo "Updating package list..."
sudo apt update

# Install PostgreSQL
echo -e "\nInstalling PostgreSQL..."
sudo apt install -y postgresql postgresql-contrib

# Install PostgreSQL dev tools
echo -e "\nInstalling PostgreSQL development tools..."
sudo apt install -y postgresql-server-dev-16 build-essential

# Add TimescaleDB repository
echo -e "\nAdding TimescaleDB repository..."
echo "deb https://packagecloud.io/timescale/timescaledb/ubuntu/ $(lsb_release -c -s) main" | sudo tee /etc/apt/sources.list.d/timescaledb.list > /dev/null
wget --quiet https://packagecloud.io/timescale/timescaledb/gpgkey -O - | sudo apt-key add -

# Update and install TimescaleDB
echo -e "\nInstalling TimescaleDB..."
sudo apt update
sudo apt install -y timescaledb-2-postgresql-16

# Configure TimescaleDB (optional but recommended)
echo -e "\nConfiguring TimescaleDB..."
sudo timescaledb-tune --quiet --accept

# Start PostgreSQL service
echo -e "\nStarting PostgreSQL service..."
sudo systemctl start postgresql
sudo systemctl enable postgresql

# Verify installation
echo -e "\n======================================================"
echo "Verification"
echo "======================================================"
psql --version
sudo -u postgres psql -c "SELECT version();" 2>/dev/null || echo "Could not verify"
sudo -u postgres psql -c "CREATE EXTENSION IF NOT EXISTS timescaledb; SELECT version();" 2>/dev/null || echo "Could not verify TimescaleDB"

echo -e "\n======================================================"
echo "✅ Installation Complete!"
echo "======================================================"
echo ""
echo "Next steps:"
echo "  1. Create user and database:"
echo "     python /home/emmanuel/Documents/Scalable_Brain/scalable-brain/shell/setup_postgresql_native.py"
echo ""
echo "  2. Verify connection:"
echo "     psql -U postgres -c 'SELECT 1'"
echo ""
echo "PostgreSQL Details:"
echo "  - Service: postgres (use 'sudo systemctl status postgresql')"
echo "  - Port: 5432"
echo "  - Admin user: postgres"
echo ""
echo "Default location: /var/lib/postgresql"
echo "Configuration: /etc/postgresql"
echo "Logs: /var/log/postgresql"
