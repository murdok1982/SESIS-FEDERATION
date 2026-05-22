"""Satellite database operations."""
import sqlite3
import os
from app.services.satellite.config import satellite_settings


def get_db():
    os.makedirs(os.path.dirname(satellite_settings.DB_PATH), exist_ok=True)
    conn = sqlite3.connect(os.path.join(satellite_settings.DB_PATH, "satellite.db"))
    conn.row_factory = sqlite3.Row
    return conn
