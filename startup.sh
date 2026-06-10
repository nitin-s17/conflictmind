#!/bin/bash

python -m google.adk.cli web --host 0.0.0.0 --port 8000 &
ADK_PID=$!

python -m reconciler.background_worker &

echo "Waiting for ADK to be ready..."
for i in $(seq 1 60); do
    if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
        echo "ADK ready after ${i} seconds"
        break
    fi
    if ! kill -0 $ADK_PID 2>/dev/null; then
        echo "ADK process died! Exiting."
        exit 1
    fi
    sleep 1
done

echo "Starting Flask..."
exec python app.py