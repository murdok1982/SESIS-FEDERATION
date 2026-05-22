#!/bin/bash
echo "Pulling fsociety model for SESIS-FEDERATION..."
ollama pull fsociety || echo "Model not found. Run: ollama create fsociety -f Modelfile"
ollama list
