#!/bin/bash

# Setup script for AI service development environment
set -e

echo "Setting up AI service for development..."

# Check for uv
if ! command -v uv &> /dev/null; then
    echo "uv is not installed. Install it from https://docs.astral.sh/uv/getting-started/installation/"
    exit 1
fi

# Install dependencies
echo "Installing dependencies..."
uv sync

# Copy .env if missing
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        cp .env.example .env
        echo ".env created from .env.example — fill in the required values before starting."
    else
        echo "Warning: no .env or .env.example found. Create .env manually."
    fi
fi

# Initialize database with test users
echo "Initializing database..."
uv run python -m app.db.init_db

echo ""
echo "Setup complete!"
echo ""
echo "Test accounts (development only):"
echo "  Admin:   admin@bitpolito.it  / DevAdmin@2024!Secure"
echo "  Student: student@bitpolito.it / DevStudent@2024!Learn"
echo ""
echo "Start the development server:"
echo "  uv run uvicorn app.main:app --reload --port 8000"
