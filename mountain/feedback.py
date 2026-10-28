"""Anonymous, unverified observations kept separate from model predictions."""
import argparse
import hashlib
import hmac
import json
import secrets
import sqlite3
import time
from pathlib import Path
from contextlib import contextmanager
from urllib.parse import urlsplit

CHOICES = {'out': 'Out', 'partial': 'Partly out', 'not_out': 'Not out', 'unsure': 'Can’t tell'}
CONTEXT_TTL = 2 * 3600
RETENTION = 90 * 86400


def public_origin(value):
    value = value.rstrip('/')
    parsed = urlsplit(value)
    if (parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in ('localhost', '127.0.0.1'))
            or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path):
        raise ValueError('Public URL must be an HTTPS origin (HTTP permitted for loopback development).')
    return value


class FeedbackStore:
    def __init__(self, directory, clock=time.time):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path, self.clock = directory / 'feedback.sqlite3', clock
        with self.connect() as db:
            db.executescript('''
              CREATE TABLE IF NOT EXISTS settings (name TEXT PRIMARY KEY, value TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS contexts (token TEXT PRIMARY KEY, created REAL NOT NULL, snapshot TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY, received REAL NOT NULL, mountain TEXT NOT NULL,
                viewpoint TEXT NOT NULL, answer TEXT NOT NULL, browser_hash TEXT NOT NULL,
                bucket INTEGER NOT NULL, snapshot TEXT NOT NULL,
                UNIQUE(viewpoint, browser_hash, bucket));
            ''')
            db.execute('INSERT OR IGNORE INTO settings VALUES (?,?)', ('key', secrets.token_hex(32)))
            self.key = bytes.fromhex(db.execute('SELECT value FROM settings WHERE name=?', ('key',)).fetchone()[0])
        self.prune()

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def digest(self, value):
        return hmac.new(self.key, value.encode(), hashlib.sha256).hexdigest()

    def context(self, token):
        if not token or len(token) != 24:
            raise ValueError('This feedback link is invalid. Scan a fresh display QR code.')
        with self.connect() as db:
            row = db.execute('SELECT * FROM contexts WHERE token=?', (token,)).fetchone()
        if not row or not 0 <= self.clock() - row['created'] <= CONTEXT_TTL:
            raise ValueError('This feedback link has expired. Scan the code after the display refreshes.')
        return json.loads(row['snapshot'])

    def issue(self, snapshot):
        token = secrets.token_urlsafe(18)
        with self.connect() as db:
            db.execute('DELETE FROM contexts WHERE created < ?', (self.clock() - CONTEXT_TTL,))
            db.execute('DELETE FROM reports WHERE received < ?', (self.clock() - RETENTION,))
            # A bounded context table prevents polling from filling the database forever.
            db.execute('DELETE FROM contexts WHERE token IN (SELECT token FROM contexts ORDER BY created DESC LIMIT -1 OFFSET 4999)')
            db.execute('INSERT INTO contexts VALUES (?,?,?)', (token, self.clock(), json.dumps(snapshot)))
        return token

    def csrf(self, token, browser):
        return self.digest('csrf:' + token + ':' + browser)

    def submit(self, token, browser, csrf, answer, present):
        snapshot = self.context(token)
        if (not browser or len(browser) != 32 or len(csrf) != 64 or
                any(c not in '0123456789abcdef' for c in csrf) or
                not hmac.compare_digest(self.csrf(token, browser), csrf)):
            raise ValueError('The form session is invalid. Open the feedback link again.')
        if answer not in CHOICES or present != 'yes':
            raise ValueError('Choose an answer and confirm you are looking from this viewpoint now.')
        now = self.clock()
        with self.connect() as db:
            try:
                db.execute('INSERT INTO reports(received,mountain,viewpoint,answer,browser_hash,bucket,snapshot) VALUES (?,?,?,?,?,?,?)',
                           (now, snapshot['mountain'], snapshot['viewpoint'], answer,
                            self.digest('browser:' + browser), int(now // 600), json.dumps(snapshot)))
            except sqlite3.IntegrityError:
                return False
        return True

    def export(self):
        with self.connect() as db:
            rows = db.execute('SELECT id,received,mountain,viewpoint,answer,snapshot FROM reports ORDER BY id').fetchall()
        for row in rows:
            report = dict(row)
            report['snapshot'] = json.loads(report['snapshot'])
            report['verified'] = False
            yield report

    def recent(self, mountain, viewpoint):
        """A short-lived shared view; no identities, raw reports, or consensus claim."""
        with self.connect() as db:
            rows = db.execute('SELECT answer,COUNT(*) AS n FROM reports WHERE mountain=? AND viewpoint=? AND received>=? GROUP BY answer',
                              (mountain, viewpoint, self.clock() - 1200)).fetchall()
        return {row['answer']: row['n'] for row in rows}

    def review(self):
        """Private operator queue of recent disagreements; never alters the model."""
        for report in self.export():
            if self.clock() - report['received'] <= 86400 and comparison(report['snapshot']['status'], report['answer']) == 'different':
                yield report

    def prune(self):
        with self.connect() as db:
            db.execute('DELETE FROM contexts WHERE created < ?', (self.clock() - CONTEXT_TTL,))
            db.execute('DELETE FROM reports WHERE received < ?', (self.clock() - RETENTION,))


def qr_svg(url):
    import io
    import qrcode
    from qrcode.image.svg import SvgPathImage
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=4, box_size=4)
    qr.add_data(url)
    qr.make(fit=True)
    output = io.BytesIO()
    qr.make_image(image_factory=SvgPathImage).save(output)
    return output.getvalue()


def comparison(status, answer):
    expected = {'mountain_out': 'out', 'mostly_out': 'out',
                'halfway_out': 'partial', 'kinda_out': 'partial', 'not_out': 'not_out'}
    if status not in expected or answer == 'unsure':
        return 'uncompared'
    return 'same' if expected[status] == answer else 'different'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['export', 'prune', 'review'])
    parser.add_argument('--data-dir', default='.local/mountain')
    args = parser.parse_args()
    store = FeedbackStore(args.data_dir)
    if args.action == 'prune':
        store.prune()
    else:
        for report in (store.review() if args.action == 'review' else store.export()):
            print(json.dumps(report))


if __name__ == '__main__':
    main()
