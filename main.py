"""
FastAPI application entry point.

To run the application:
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

Or directly:
    python -m uvicorn app.main:app --reload
"""


def main():
    """Entry point for the application."""
    import uvicorn
    uvicorn.run("app.main:app",  port=8000, reload=True)


if __name__ == "__main__":
    main()
