FROM python:3.12-slim

# Set working directory inside the container
WORKDIR /app

# Copy your exporter script
COPY exporter.py .

# Copy requirements.txt first
COPY requirements.txt .

# Install required Python packages
RUN pip install -r requirements.txt

# Set environment variable (optional, good practice)
ENV PYTHONUNBUFFERED=1

# Set default port (optional, for documentation)
EXPOSE 8000

# Run the Python script

CMD ["gunicorn", "-w", "1", "--threads", "4", "-b", "0.0.0.0:8000", "exporter:app"]
