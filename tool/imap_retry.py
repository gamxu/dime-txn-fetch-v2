"""Retry helper for transient Gmail IMAP errors (e.g. SEARCH => System Error)."""

import imaplib
import time


def with_imap_retry(session_fn, attempts: int = 3, delay: float = 5.0):
    """Run session_fn() (which opens its own IMAP connection) up to `attempts`
    times, retrying on imaplib.IMAP4.abort / OSError since the connection
    state is unusable after those errors."""
    last_err = None
    for i in range(1, attempts + 1):
        try:
            return session_fn()
        except (imaplib.IMAP4.abort, OSError) as e:
            last_err = e
            if i < attempts:
                print(f"  IMAP error ({e}) — retry {i}/{attempts - 1} in {delay:.0f}s")
                time.sleep(delay)
    raise last_err
