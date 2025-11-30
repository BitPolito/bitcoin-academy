#!/bin/bash

# BitPolito Academy - Development Server Startup Script
# This script starts both frontend and backend servers

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "BitPolito Academy - Development Server"
echo "=========================================="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running on macOS or Linux
if [[ "$OSTYPE" == "darwin"* ]]; then
    OPEN_CMD="open"
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    OPEN_CMD="xdg-open"
else
    OPEN_CMD=""
fi

# Function to print section
print_section() {
    echo ""
    echo -e "${GREEN}>>> $1${NC}"
    echo ""
}

# Function to print warning
print_warning() {
    echo -e "${YELLOW} $1${NC}"
}

# Function to print error
print_error() {
    echo -e "${RED} $1${NC}"
}

# Check prerequisites
print_section "Checking Prerequisites"

if ! command -v node &> /dev/null; then
    print_error "Node.js is not installed. Please install Node.js 18+"
    exit 1
fi

if ! command -v npm &> /dev/null; then
    print_error "npm is not installed"
    exit 1
fi

if ! command -v python3 &> /dev/null; then
    print_error "Python 3 is not installed"
    exit 1
fi

echo "Node.js: $(node --version)"
echo "npm: $(npm --version)"
echo "Python: $(python3 --version)"

# Setup Backend
print_section "Setting up Backend"

cd "$PROJECT_DIR/services/ai"

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv venv
    echo "Virtual environment created"
fi

# Activate virtual environment
echo "Activating virtual environment..."
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
elif [ -f "venv/Scripts/activate" ]; then
    source venv/Scripts/activate
else
    print_error "Could not find virtual environment activation script"
    exit 1
fi

# Check if requirements.txt exists
if [ ! -f "requirements.txt" ]; then
    print_error "requirements.txt not found"
    exit 1
fi

# Upgrade pip first
echo "Upgrading pip..."
pip install -q --upgrade pip

# Install dependencies
echo "Installing Python dependencies..."
pip install -r requirements.txt

if [ ! -f ".env" ]; then
    print_warning ".env file not found. Copying from .env.example..."
    if [ -f ".env.example" ]; then
        cp .env.example .env
    fi
fi

echo "✅ Backend setup complete"

# Setup Frontend
print_section "Setting up Frontend"

cd "$PROJECT_DIR/apps/web"

if [ ! -d "node_modules" ]; then
    echo "Installing npm dependencies..."
    npm install --silent
fi

if [ ! -f ".env.local" ]; then
    print_warning ".env.local file not found. Copying from .env.example..."
    if [ -f ".env.example" ]; then
        cp .env.example .env.local
    fi
fi

echo "Frontend setup complete"

# Start servers
print_section "Starting Development Servers"

echo ""
echo "Backend will start on:   http://localhost:8000"
echo "API Documentation:       http://localhost:8000/docs"
echo "Frontend will start on:  http://localhost:3000"
echo ""
print_warning "Keep this terminal open to run both servers"
echo ""

# Start backend in background
echo "Starting FastAPI backend..."
cd "$PROJECT_DIR/services/ai"
source venv/bin/activate 2>/dev/null || source venv/Scripts/activate 2>/dev/null || true
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 > backend.log 2>&1 &
BACKEND_PID=$!
echo "Backend PID: $BACKEND_PID"

# Wait a bit for backend to start
sleep 3

# Start frontend
echo "Starting Next.js frontend..."
cd "$PROJECT_DIR/apps/web"
npm run dev

# Cleanup on exit
trap "kill $BACKEND_PID 2>/dev/null" EXIT

echo ""
print_section "Development Servers Stopped"
