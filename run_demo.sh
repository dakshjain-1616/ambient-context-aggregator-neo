#!/bin/bash
set -e
cd /root/projects/ambient-context-aggregator

echo "=== Step 1: Installing huggingface_hub==0.20.3 ==="
/usr/bin/python3 -m pip install huggingface_hub==0.20.3 --force-reinstall -q

echo "=== Step 2: Installing requirements.txt ==="
/usr/bin/python3 -m pip install -r requirements.txt -q

echo "=== Step 3: Running demo.py ==="
/usr/bin/python3 demo.py
