# Backend - Gemini Website Authority Evaluator

## Prerequisites

- Python 3.10 or higher
- pip
- MongoDB connection (for database)

## Installation

1. Navigate to the backend directory:
   ```bash
   cd backend
   ```

2. Create a virtual environment:
   ```bash
   python -m venv venv
   ```

3. Activate the virtual environment:
   - **macOS/Linux:**
     ```bash
     source venv/bin/activate
     ```
   - **Windows:**
     ```bash
     venv\Scripts\activate
     ```

4. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

5. Install Playwright browsers:
   ```bash
   playwright install chromium
   ```

## Environment Setup

1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```

2. Update `.env` with your configuration:
   - Add your API keys
   - Add MongoDB connection string

## Running the Application

Start the development server:
```bash
uvicorn main:app --reload
```

The API will be available at `http://localhost:8000`

## Project Structure

```
backend/
├── controllers/      # Business logic
├── models/           # Database models
├── routes/           # API routes
├── main.py           # Application entry point
├── database.py       # Database configuration
└── requirements.txt  # Python dependencies
```
