"""Konfiguracja wyłącznie ze zmiennych środowiskowych (bez sekretów w kodzie)."""
import os
from pathlib import Path

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
SAMPLE_DIR = Path(__file__).resolve().parents[2] / "tests" / "sample"
PORT = int(os.getenv("PORT", "8000"))
DANE_API_URL = os.getenv("DANE_API_URL", "https://api.dane.gov.pl/1.4")
DANE_API_KEY = os.getenv("DANE_API_KEY", "")
