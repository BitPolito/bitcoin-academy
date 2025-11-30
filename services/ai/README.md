# FastAPI Backend Setup

## Prerequisites

- Python 3.10+
- pip or poetry

## Installation

```bash
cd services/ai
pip install -r requirements.txt
```

## Environment Variables

Create a `.env` file in `services/ai`:

```bash
DATABASE_URL=postgresql://user:password@localhost:5432/bitcoin_academy
SECRET_KEY=your-secret-key
API_PORT=8000
```

## Development

### Initial Setup

Run the setup script to initialize the database with test users:

```bash
./setup-dev.sh
```

This will:

- Install dependencies
- Create the SQLite database with schema
- Seed test users for development (no registration needed)

**Test Users:**

- **Admin**: `admin@bitpolito.it` / `admin123`
- **Student**: `student@bitpolito.it` / `student123`

### Start the Server

```bash
python -m uvicorn app.main:app --reload
```

The API will be available at `http://localhost:8000`

## Project Structure

See the main README.md for the FastAPI architecture overview.

## Running Tests

```bash
pytest
```
