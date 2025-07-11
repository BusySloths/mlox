#!/bin/bash

# Start Ollama in the background.
/bin/ollama serve &
# Record Process ID.
pid=$!

# Pause for Ollama to start.
sleep 5

ollama pull tinyllama
ollama pull llama3.2
ollama pull llama3.2:1b
ollama pull phi3.5
ollama pull gemma2
ollama pull gemma2:27b

# Wait for Ollama process to finish.
wait $pid
