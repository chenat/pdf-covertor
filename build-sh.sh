#!/usr/bin/env bash
apt-get update
apt-get install -y --no-install-recommends poppler-utils libcairo2
pip install -r requirements.txt
