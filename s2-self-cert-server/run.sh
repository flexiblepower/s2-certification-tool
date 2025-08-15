#!/bin/bash

SERVER_KEY_PATH="./server_key.pem" KEYS_STORAGE_PATH="./data/keys.json" uv run fastapi dev ./src/main.py  --port 8000 --host 0.0.0.0