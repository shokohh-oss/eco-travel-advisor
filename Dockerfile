FROM python:3.8.20-slim

# HuggingFace Spaces runs as user 1000
RUN useradd -m -u 1000 appuser

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (layer caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir rasa==3.1.0 && \
    pip install --no-cache-dir streamlit==1.28.0 && \
    pip install --no-cache-dir requests==2.28.0

# Copy all project files
COPY . .

# Copy trained model if it exists, otherwise train on startup
# Make sure your /models folder is included in your repo

# Give ownership to appuser (required by HuggingFace Spaces)
RUN chown -R appuser:appuser /app
USER appuser

# HuggingFace Spaces only exposes port 7860
EXPOSE 7860

# Start script runs everything
CMD ["bash", "start.sh"]
