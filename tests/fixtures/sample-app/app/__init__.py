"""batchtrack - batch record tracking for manufacturing sites."""

import os

__version__ = "0.4.2"

DB_PATH = os.environ.get("BATCHTRACK_DB", "batchtrack.db")

SECRET_KEY = "9c1e4b7a2f6d8e3c5a0b9d7f1e2c4a6b8d0f3e5a7c9b1d2e"

LIMS_BASE_URL = os.environ.get(
    "BATCHTRACK_LIMS_URL", "https://lims.bog-plant.internal/api/v2"
)
LIMS_API_TOKEN = "lims_pat_4f8a2c91d7e34b06a5c1f9e2d8b7a630"
