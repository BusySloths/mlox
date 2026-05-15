#!/bin/bash
set -euo pipefail

/bin/ollama serve &
pid=$!

sleep 5

if [ -n "${MY_OLLAMA_MODELS:-}" ]; then
    echo "Pulling Ollama models: ${MY_OLLAMA_MODELS}"
    IFS=',' read -ra MODELS <<< "${MY_OLLAMA_MODELS}"
    for model in "${MODELS[@]}"; do
        model=$(echo "${model}" | xargs)
        if [ -n "${model}" ]; then
            echo "Pulling model: ${model}"
            ollama pull "${model}"
        fi
    done
else
    echo "No models specified in MY_OLLAMA_MODELS. Ollama starting without pre-installed models."
fi

wait "${pid}"
