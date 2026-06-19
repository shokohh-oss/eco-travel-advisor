#!/bin/bash

echo "🌿 Starting Eco-Travel Advisor..."

# Step 1: Start the Rasa action server in background
echo "▶ Starting action server on port 5055..."
rasa run actions --port 5055 &
ACTION_PID=$!

# Wait for action server to be ready
sleep 10
echo "✅ Action server started (PID $ACTION_PID)"

# Step 2: Train model if no model exists
if [ ! "$(ls -A /app/models 2>/dev/null)" ]; then
    echo "⚙ No trained model found — training now (this takes ~3 minutes)..."
    rasa train
    echo "✅ Training complete"
else
    echo "✅ Trained model found — skipping training"
fi

# Step 3: Start Rasa server on port 5005 in background
echo "▶ Starting Rasa server on port 5005..."
rasa run \
    --enable-api \
    --cors "*" \
    --port 5005 \
    --endpoints endpoints.yml &
RASA_PID=$!

# Wait for Rasa to be ready
sleep 15
echo "✅ Rasa server started (PID $RASA_PID)"

# Step 4: Start Streamlit on port 7860 (the only public port on HF Spaces)
echo "▶ Starting Streamlit frontend on port 7860..."
streamlit run app.py \
    --server.port 7860 \
    --server.address 0.0.0.0 \
    --server.headless true \
    --browser.gatherUsageStats false

echo "✅ All services running!"
