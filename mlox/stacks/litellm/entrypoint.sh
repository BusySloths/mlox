#!/bin/bash

# Start Ollama in the background.
/bin/ollama serve &
# Record Process ID.
pid=$!

# Pause for Ollama to start.
sleep 5

# Pull models from environment variable if specified
# MY_OLLAMA_MODELS should be a comma-separated list (e.g., "tinyllama,llama3.2:1b")
if [ -n "$MY_OLLAMA_MODELS" ]; then
    echo "Pulling Ollama models: $MY_OLLAMA_MODELS"
    IFS=',' read -ra MODELS <<< "$MY_OLLAMA_MODELS"
    for model in "${MODELS[@]}"; do
        # Trim whitespace
        model=$(echo "$model" | xargs)
        if [ -n "$model" ]; then
            echo "Pulling model: $model"
            ollama pull "$model"
        fi
    done
else
    echo "No models specified in MY_OLLAMA_MODELS. Ollama starting without pre-installed models."
    echo "You can pull models later using: ollama pull <model-name>"
fi

# Wait for Ollama process to finish.
wait $pid
