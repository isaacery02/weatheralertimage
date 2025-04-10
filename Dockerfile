# Dockerfile

# Use a standard Python slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install cron
# Install cron, procps (for ps), and vim (for vi)
RUN apt-get update && apt-get install -y --no-install-recommends cron vim && rm -rf /var/lib/apt/lists/*

# Copy requirements first, install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY weather_notifier.py .

# Copy the crontab file into the cron directory
COPY weather_cron /etc/cron.d/weather_cron

# Give correct permissions to the crontab file
RUN chmod 0644 /etc/cron.d/weather_cron

# Create the log file and grant permissions for writing
RUN touch /var/log/cron.log && chmod 0666 /var/log/cron.log

# --- Changes Start Here ---

# Copy the entrypoint script
COPY entrypoint.sh /entrypoint.sh
# Make it executable
RUN chmod +x /entrypoint.sh

# REMOVE the old CMD line:
# CMD printenv | sed 's/=\(.*\)/="\1"/' >> /etc/environment && cron -f

# Set the entrypoint script to run when the container starts
ENTRYPOINT ["/entrypoint.sh"]