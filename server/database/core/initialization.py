"""Database initialization functions for Phlox.

This module handles initialization tasks that run after migrations,
such as creating the initial user-settings row. The simplified app keeps
no clinical templates, letters, or patient records.
"""

import logging


def ensure_user_settings_row(cursor, _db):
    """Create the initial user-settings row when the table is empty.

    Args:
        cursor: Database cursor
        _db: Database connection (unused; commit owned by caller's transaction)
    """
    try:
        cursor.execute("SELECT COUNT(*) FROM user_settings")
        count = cursor.fetchone()[0]
        if count == 0:
            cursor.execute(
                "INSERT INTO user_settings (has_completed_splash_screen) VALUES (?)",
                (True,),
            )
            logging.info("Created initial user settings row")
    except Exception as e:
        logging.error(f"Error ensuring user settings row: {e}")
        raise
