"""Apply the additive schema on existing volumes before starting the web workers."""
import os
from pathlib import Path

import psycopg

from ai import create_secret_key


if __name__ == '__main__':
    create_secret_key()
    with psycopg.connect(os.environ['DATABASE_URL']) as conn:
        conn.execute((Path(__file__).resolve().parents[1] / 'db/init.sql').read_text())
