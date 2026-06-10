#!/bin/bash
# Export env vars explicitly for ADK
export GOOGLE_CLOUD_PROJECT="${maximal-kingdom-499004-r9}"
export GOOGLE_CLOUD_LOCATION="${us-central1}"
export GOOGLE_GENAI_USE_VERTEXAI="${true}"
export MONGODB_URI="${mongodb+srv://conflictmind_user:conflictmind_user@conflictmind.emdezmg.mongodb.net/?appName=ConflictMind}"
export MONGODB_DB_NAME="${ConflictMind}"

# Start ADK in background
python -m google.adk.cli web --host 0.0.0.0 --port 8000 &

# Wait until ADK health endpoint responds
echo "Waiting for ADK to be ready..."
for i in $(seq 1 60); do
    if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
        echo "ADK ready after ${i} seconds"
        break
    fi
    sleep 1
done

echo "Starting Flask..."
exec python app.py