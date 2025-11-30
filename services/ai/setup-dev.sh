#!/bin/bash

# Setup script for AI service development environment
set -e

echo "🚀 Setting up AI service for development..."

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed"
    exit 1
fi

# Install dependencies
echo "📦 Installing dependencies..."
pip install -q -r requirements.txt 2>/dev/null || true

# Initialize database with test users
echo "🗄️  Initializing database with test users..."
python app/db/init_db.py

echo ""
echo "✅ Setup complete!"
echo ""
echo "🔑 Test Users:"
echo "   Admin:   admin@bitpolito.it / admin123"
echo "   Student: student@bitpolito.it / student123"
echo ""
echo "🚀 To start the development server, run:"
echo "   python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
