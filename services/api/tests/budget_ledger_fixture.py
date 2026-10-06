"""Offline SQLite reservation contract oracle; never used by the application.

Limits/holds are injected symbolic units, not currency, pricing or authorization.
This generated-store fixture tests a proposed transaction/state contract only.
"""

import json
import sqlite3
from contextlib import contextmanager


class ContractConflict(ValueError):
    pass


class LedgerFixture:
    def __init__(self, path, limit=10):
        if type(limit) is not int or limit <= 0:
            raise ValueError("Positive symbolic limit required")
        self.path = str(path)
        with self.transaction() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS policy(
                    id INTEGER PRIMARY KEY CHECK(id=1), ceiling INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS attempts(
                    id TEXT PRIMARY KEY NOT NULL, hold INTEGER NOT NULL CHECK(hold>0),
                    state TEXT NOT NULL CHECK(state IN
                        ('reserved','in_flight','uncertain','reconciled','released')),
                    settled INTEGER CHECK(settled>=0), evidence TEXT UNIQUE);
                CREATE TABLE IF NOT EXISTS history(
                    seq INTEGER PRIMARY KEY, attempt TEXT NOT NULL,
                    action TEXT NOT NULL, evidence TEXT);
            """)
            db.execute("INSERT OR IGNORE INTO policy VALUES(1,?)", (limit,))
            if db.execute("SELECT ceiling FROM policy").fetchone()[0] != limit:
                raise ContractConflict("Fixture policy is immutable")

    @contextmanager
    def transaction(self):
        db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def available_in(db):
        ceiling = db.execute("SELECT ceiling FROM policy").fetchone()[0]
        used = db.execute("""SELECT COALESCE(SUM(CASE
            WHEN state='reconciled' THEN settled
            WHEN state IN ('reserved','in_flight','uncertain') THEN hold ELSE 0 END),0)
            FROM attempts""").fetchone()[0]
        return ceiling - used

    def reserve(self, attempt, hold):
        if not isinstance(attempt, str) or not attempt.strip() or len(attempt) > 128:
            raise ValueError("Nonempty bounded attempt ID required")
        if type(hold) is not int or hold <= 0:
            raise ValueError("Positive symbolic integer units required")
        with self.transaction() as db:
            old = db.execute("SELECT hold,state FROM attempts WHERE id=?", (attempt,)).fetchone()
            if old:
                if old[0] != hold:
                    raise ContractConflict("Attempt parameters changed")
                return old[1]
            if self.available_in(db) < hold:
                return None
            db.execute("INSERT INTO attempts VALUES(?,?,?,NULL,NULL)", (attempt, hold, "reserved"))
            db.execute("INSERT INTO history(attempt,action) VALUES(?,?)", (attempt, "reserved"))
            return "reserved"

    def transition(
        self,
        attempt,
        target,
        *,
        amount=None,
        evidence=None,
        evidence_source=None,
        unsent_proof=None,
    ):
        if target not in {"in_flight", "uncertain", "released", "reconciled"}:
            raise ContractConflict("Unknown transition")
        if target == "reconciled" and (
            type(amount) is not int
            or amount < 0
            or not isinstance(evidence, str)
            or not evidence.strip()
            or not isinstance(evidence_source, str)
            or not evidence_source.strip()
        ):
            raise ContractConflict("Settlement needs units and evidence; unknown is not zero")
        if target == "released" and not unsent_proof:
            raise ContractConflict("Disposable unsent-proof precondition required")
        evidence_key = json.dumps([evidence_source, evidence]) if target == "reconciled" else None
        with self.transaction() as db:
            row = db.execute(
                "SELECT state,settled,evidence FROM attempts WHERE id=?", (attempt,)
            ).fetchone()
            if row is None:
                raise ContractConflict("Unknown attempt")
            state, settled, old_evidence = row
            if state == target:
                if target == "reconciled" and (settled, old_evidence) != (amount, evidence_key):
                    raise ContractConflict("Settlement replay differs")
                return state
            permitted = {
                "reserved": {"in_flight", "released"},
                "in_flight": {"uncertain", "reconciled"},
                "uncertain": {"reconciled"},
                "reconciled": set(),
                "released": set(),
            }
            if target not in permitted[state]:
                raise ContractConflict("No automatic release after possible dispatch")
            try:
                db.execute(
                    "UPDATE attempts SET state=?,settled=?,evidence=? WHERE id=?",
                    (target, amount, evidence_key, attempt),
                )
                db.execute(
                    "INSERT INTO history(attempt,action,evidence) VALUES(?,?,?)",
                    (attempt, target, evidence_key or unsent_proof),
                )
            except sqlite3.IntegrityError as exc:
                raise ContractConflict("Billing evidence already used") from exc
            return target

    def recover(self, *, fenced_sender_proof):
        # A supplied fixture token states a precondition, not real authorization/fencing.
        if not fenced_sender_proof:
            raise ContractConflict("Disposable sender-fencing precondition required")
        with self.transaction() as db:
            rows = db.execute("SELECT id FROM attempts WHERE state='in_flight'").fetchall()
            for (attempt,) in rows:
                db.execute("UPDATE attempts SET state='uncertain' WHERE id=?", (attempt,))
                db.execute(
                    "INSERT INTO history(attempt,action) VALUES(?,?)", (attempt, "uncertain")
                )

    def snapshot(self):
        with self.transaction() as db:
            return {
                "available": self.available_in(db),
                "states": dict(db.execute("SELECT id,state FROM attempts")),
                "transitions": db.execute("SELECT COUNT(*) FROM history").fetchone()[0],
            }


def reserve_from_process(path, attempt):
    return LedgerFixture(path).reserve(str(attempt), 3)
