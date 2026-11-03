"""Local registry with transactional updates, unique card IDs and change history."""
import sqlite3
import json
import re
from datetime import datetime, timezone
from pathlib import Path

def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

class Registry:
    def __init__(self,path):
        self.path=Path(path)
        self.db=sqlite3.connect(self.path)
        self.db.row_factory=sqlite3.Row
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS cards (
          uid TEXT PRIMARY KEY, name TEXT NOT NULL, initials TEXT NOT NULL,
          active INTEGER NOT NULL CHECK(active IN (0,1)),
          created_utc TEXT NOT NULL, updated_utc TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS history (
          id INTEGER PRIMARY KEY, timestamp_utc TEXT NOT NULL,
          uid TEXT NOT NULL, action TEXT NOT NULL, before_json TEXT, after_json TEXT NOT NULL);
        ''')

    def get(self,uid):
        row=self.db.execute('SELECT * FROM cards WHERE uid=?',(uid,)).fetchone()
        return dict(row) if row else None

    def rows(self):
        return [dict(r) for r in self.db.execute('SELECT * FROM cards ORDER BY name COLLATE NOCASE,uid')]

    def save(self,uid,name,initials,active,existing=False):
        """Require explicit edit mode to prevent silent reassignment of a card."""
        uid=uid.strip().upper();name=name.strip();initials=initials.strip().upper()
        if not re.fullmatch(r'(?:[0-9A-F]{2}){1,256}',uid):raise ValueError('Scan a card first.')
        if not name or len(name)>100:raise ValueError('Enter an operator name (1–100 characters).')
        if not re.fullmatch(r'[A-Z]{1,10}',initials):raise ValueError('Enter initials using 1–10 letters.')
        with self.db:
            # Lock before reading so another registry cannot interleave a write.
            self.db.execute('BEGIN IMMEDIATE')
            old=self.get(uid)
            if old and not existing:raise ValueError('Card is already registered. Select its row to edit it.')
            if existing and not old:raise ValueError('This record no longer exists. Refresh the list.')
            stamp=now();created=old['created_utc'] if old else stamp
            self.db.execute('INSERT OR REPLACE INTO cards VALUES (?,?,?,?,?,?)',
                (uid,name,initials,int(bool(active)),created,stamp))
            self.db.execute('INSERT INTO history(timestamp_utc,uid,action,before_json,after_json) VALUES(?,?,?,?,?)',
                (stamp,uid,'updated' if old else 'enrolled',json.dumps(old) if old else None,json.dumps(self.get(uid))))
        return self.get(uid)

    def backup(self,path):
        """SQLite backup creates a consistent database including change history."""
        if Path(path).resolve()==self.path.resolve():raise ValueError('Choose a different backup filename.')
        target = sqlite3.connect(path)
        try:
            self.db.backup(target)
        finally:
            # SQLite's context manager commits transactions but does not close
            # the connection. Explicit closure releases Windows file locks.
            target.close()

    def close(self):
        self.db.close()
