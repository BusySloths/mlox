#!/bin/bash

# Start Ollama in the background.
/bin/ollama serve &
# Record Process ID.
pid=$!

# Pause for Ollama to start.
sleep 5

ollama pull tinyllama
ollama pull llama3.2:1b
ollama pull deepseek-r1:1.5b

# Wait for Ollama process to finish.
wait $pid
