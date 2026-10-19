#!/usr/bin/env python3
"""Forward the legacy CD entry point to the maintained playlist implementation."""
import os
from pathlib import Path
import sys

target = Path(__file__).resolve().parents[2] / 'road-music-showreel-playlist' / 'scripts' / 'playlist_presets.py'
os.execv(sys.executable, [sys.executable, str(target), *sys.argv[1:]])
