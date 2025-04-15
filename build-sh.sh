#!/usr/bin/env bash
# Install system dependencies
apt-get update
apt-get install -y --no-install-recommends poppler-utils libcairo2

# Install Python dependencies
pip install -r requirements.txt
