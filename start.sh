#!/bin/bash
set -e
cd /opt/doc-system

echo === Pulling base images ===
docker pull pgvector/pgvector:pg17
docker pull elasticsearch:8.17.4
docker pull ollama/ollama:latest

echo === Building services ===
docker compose build --parallel

echo === Starting services ===
docker compose up -d --remove-orphans

echo === Waiting for health checks ===
sleep 15
docker compose ps

echo === Done ===
echo Frontend: http://192.168.99.210
echo Backend: http://192.168.99.210:8000
