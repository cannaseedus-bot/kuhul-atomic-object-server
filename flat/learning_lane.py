"""KGF-fed learning lane. Python stdlib only; proposal-only student boundary."""
from __future__ import annotations
import hashlib
import json
import math
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path


class ContractError(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


@dataclass(frozen=True)
class KGFContract:
    name: str
    source: str
    score: str
    commit_phase: str
    update: str
    bias_key: str
    phases: tuple[str, ...]

    @classmethod
    def load(cls, path):
        src = Path(path).read_text(encoding='utf-8')
        src = re.sub(r'\(\*.*?\*\)', '', src, flags=re.S)
        def one(pattern, label):
            matches = re.findall(pattern, src, flags=re.I | re.S)
            if len(matches) != 1:
                raise ContractError(f'Expected exactly one {label}, found {len(matches)}')
            return matches[0]
        name = one(r'keygraph\s+"([^"]+)"\s+version\s+"[^"]+"\s*;', 'keygraph')
        source = one(r'key\s+learning:PROPOSAL\s+kind\s+field\s+value\s+"([^"]+)"\s*;', 'proposal source')
        score = one(r'policy\s+xcfe:LEARNING_POLICY\s*\{[^}]*?score\s+(\w+)\s*;', 'score policy')
        phase = one(r'policy\s+xcfe:LEARNING_POLICY\s*\{[^}]*?commit_phase\s+(\w+)\s*;', 'commit phase')
        bias, update = one(r'bias\s+(tensor:\w+)\s+target\s+learning:PROPOSE\s+corpus\s+[\d.]+\s+learned\s+[\d.]+\s+update\s+(\w+)\s*;', 'bias')
        phases = tuple(re.findall(r'program\s+learning:\w+\s+track\s+track:LEARNING\s+entry\s+fold:\w+\s+phase\s+([\w\']+)\s*;', src))
        if name != 'LearningLane' or source != 'student.solve.learning' or score != 'wcr' or phase != 'Xul' or update != 'xul_commit' or bias != 'tensor:learning_bias' or phases != ('Yax', 'Sek', "Ch'en", 'Xul'):
            raise ContractError('Unsupported KGF learning contract or phase sequence')
        return cls(name, source, score, phase, update, bias, phases)


class WCRFoldAccumulator:
    """Stages deltas only. Does not write storage or authorize execution."""
    def fold(self, learning):
        if not isinstance(learning, list) or not learning:
            raise ContractError('learning must be a nonempty list')
        out = []
        for c in learning:
            if not isinstance(c, dict):
                raise ContractError('candidate must be an object')
            if not all(k in c for k in ('pattern', 'W', 'C', 'R', 'G', 'S')):
                raise ContractError('candidate requires pattern and W/C/R/G/S')
            vals = {k: float(c[k]) for k in ('W', 'C', 'R', 'G', 'S')}
            if not all(math.isfinite(v) for v in vals.values()):
                raise ContractError('non-finite candidate value')
            if not 0 <= vals['C'] <= 1 or not 0 <= vals['R'] <= 1:
                raise ContractError('C and R must be in [0,1]')
            if not isinstance(c['pattern'], str) or not c['pattern']:
                raise ContractError('pattern must be a nonempty string')
            # S is supplied by ScoredCandidate; do not silently recompute it.
            out.append({'pattern': c['pattern'], 'delta': vals['G'], 'score': vals['S'], 'wcr': vals})
        return out


class SQLiteLearningStore:
    def __init__(self, path):
        self.path = str(path)
        with self._db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS commits (key TEXT PRIMARY KEY, payload_hash TEXT NOT NULL, payload TEXT NOT NULL)')

    def _db(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.execute('PRAGMA busy_timeout=30000')
        return db

    def has(self, key):
        with self._db() as db:
            return db.execute('SELECT 1 FROM commits WHERE key=?', (key,)).fetchone() is not None

    def commit(self, key, payload):
        body = canonical(payload)
        h = hashlib.sha256(body.encode()).hexdigest()
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            existing = db.execute('SELECT payload_hash FROM commits WHERE key=?', (key,)).fetchone()
            if existing:
                if existing[0] != h:
                    raise ContractError('idempotency key reused with different payload')
                return False
            db.execute('INSERT INTO commits VALUES (?, ?, ?)', (key, h, body))
            return True

    def get(self, key):
        with self._db() as db:
            row = db.execute('SELECT payload FROM commits WHERE key=?', (key,)).fetchone()
            return json.loads(row[0]) if row else None

    def projection(self):
        """Deterministically reconstruct tensor bias from committed events."""
        result = {}
        with self._db() as db:
            rows = db.execute('SELECT payload FROM commits ORDER BY key').fetchall()
        for (body,) in rows:
            for item in json.loads(body)['deltas']:
                pattern = item['pattern']
                result[pattern] = result.get(pattern, 0.0) + item['delta']
        return result


class LearningLane:
    def __init__(self, kgf_path, store):
        self.contract = KGFContract.load(kgf_path)
        self.store = store
        self.accumulator = WCRFoldAccumulator()

    def propose(self, student_result, *, proposal_id, principal, workspace):
        if not all(isinstance(x, str) and x for x in (proposal_id, principal, workspace)):
            raise ContractError('proposal_id, principal, workspace required')
        deltas = self.accumulator.fold(student_result['learning'])
        return {'proposal_id': proposal_id, 'principal': principal, 'workspace': workspace,
                'deltas': deltas, 'contract': self.contract.name}

    def commit(self, proposal, *, admission, sek_authorized, chen_verified, xul_closed):
        # Host must supply independently verified authority evidence. This method
        # does NOT itself authenticate the host; never expose it to untrusted callers.
        if not (admission == 'ADMITTED' and sek_authorized is True and
                chen_verified is True and xul_closed is True):
            raise PermissionError('Learning commit requires admission, Sek, Ch\'en, Xul')
        if proposal.get('contract') != self.contract.name:
            raise ContractError('wrong learning contract')
        for field in ('proposal_id', 'principal', 'workspace'):
            if not isinstance(proposal.get(field), str) or not proposal[field]:
                raise ContractError('missing provenance: ' + field)
        # Derive identity from the logical proposal, not the delivery attempt.
        key = digest([proposal['principal'], proposal['workspace'], proposal['proposal_id']])
        return {'key': key, 'inserted': self.store.commit(key, proposal), 'bias': self.store.projection()}
