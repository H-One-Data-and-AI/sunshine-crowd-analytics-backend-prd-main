# Use official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Install system dependencies (geopandas & pycryptodome may require build tools)
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file first for better cache on rebuild
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Expose port (default FastAPI/uvicorn runs on 8000)
EXPOSE 8000

# Start Uvicorn server pointing to app.main:app
# Ensure python knows the base dir is /app so it can import from app/
ENV PYTHONPATH=/app/app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
