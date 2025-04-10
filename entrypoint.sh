#!/bin/sh
# entrypoint.sh

echo "[Entrypoint] Setting up environment for cron..."
# Clear potentially stale environment file if container restarts
# then capture current environment variables passed via 'docker run -e'
rm -f /etc/environment
printenv | sed 's/=\(.*\)/="\1"/' >> /etc/environment

echo "[Entrypoint] Executing Python script on startup..."
# Execute the python script - its output/logs will go to Docker's stdout/stderr
/usr/local/bin/python /app/weather_notifier.py

# Check the exit code of the startup script (optional)
startup_exit_code=$?
if [ $startup_exit_code -ne 0 ]; then
    echo "[Entrypoint] Warning: Startup script exited with code $startup_exit_code"
    # Decide if you want to exit the container or continue to cron
    # exit $startup_exit_code # Uncomment to exit container if startup fails
fi

echo "[Entrypoint] Startup run finished. Starting cron daemon..."
# Start cron in the foreground.
# 'exec' replaces the shell process with cron, ensuring signals are handled correctly.
exec cron -f
