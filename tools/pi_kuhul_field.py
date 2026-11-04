"""
pi_kuhul_field.py
π-KUHUL: field geometry in Python.

The notation is positional, not calendrical. Every named construct is a
coordinate device:

  - level digit    base-20 place, written as bars (5) + dots (1) + shell (0)
  - LongCount      5-place mixed-radix coordinate, radices (20, 18, 20, 20)
  - Tzolkin        residue index pair (mod 13, mod 20), period 260
  - Haab           residue index mod 365 (18 x 20 + 5)
  - CalendarRound  joint residue pair, period lcm(260, 365) = 18,980
  - slices         64 field slices, one Chebyshev weight per slice

Complete implementation:
  - base-20 digit symbols ↔ level values
  - PiGeometry: phase arithmetic (normalize, interference, rotation)
  - field tensors: vigesimal-scaled numpy arrays
  - PiKuhulFieldEngine: 100D manifold field dynamics engine

Connects to the neural side via:
  - pi_kuhul.py  (PiKuhulTransformer — trains shard.pt weights)
  - LevelCoord.to_tensor() mirrors the neural-side LevelCoord.to_tensor() [15 floats]
  - make_maya_coords() / make_phases() produce level coordinates and phases
"""

import math
import numpy as np
from typing import List, Dict, Tuple, Optional, Union
from dataclasses import dataclass, field
from datetime import datetime

# ============================================================
# BASE-20 DIGIT SYMBOLS ↔ LEVEL VALUES
# ============================================================

MAYAN_DIGITS: Dict[str, int] = {
    '•': 1, '••': 2, '•••': 3, '••••': 4,
    '⎯': 5, '⎯⎯': 10, '⎯⎯⎯': 15,
    '•⎯': 6,  '••⎯': 7,  '•••⎯': 8,  '••••⎯': 9,
    '•⎯⎯': 11, '••⎯⎯': 12, '•••⎯⎯': 13, '••••⎯⎯': 14,
    '•⎯⎯⎯': 16, '••⎯⎯⎯': 17, '•••⎯⎯⎯': 18, '••••⎯⎯⎯': 19,
    '\u1090': 0, '🐚': 0, '○': 0, '·': 0,   # shell variants
}

REVERSE_MAYAN: Dict[int, str] = {
    0: '○',   1: '•',    2: '••',   3: '•••',  4: '••••',
    5: '⎯',   6: '•⎯',   7: '••⎯',  8: '•••⎯', 9: '••••⎯',
    10: '⎯⎯',  11: '•⎯⎯',  12: '••⎯⎯', 13: '•••⎯⎯', 14: '••••⎯⎯',
    15: '⎯⎯⎯', 16: '•⎯⎯⎯', 17: '••⎯⎯⎯', 18: '•••⎯⎯⎯', 19: '••••⎯⎯⎯',
}

# ── Core glyph ↔ int helpers ─────────────────────────────────────────────────

def mayan_to_number(glyph: str) -> int:
    """Single Maya glyph (0-19) → int."""
    if glyph in MAYAN_DIGITS:
        return MAYAN_DIGITS[glyph]
    raise ValueError(f"Unknown Maya glyph: {repr(glyph)}")

def number_to_mayan(n: int) -> str:
    """int (0-19) → Maya glyph."""
    n = int(n) % 20
    return REVERSE_MAYAN[n]

def int_to_vigesimal(n: int) -> str:
    """int → base-20 string (matches JS Number.prototype.toString(20))."""
    if n == 0:
        return '0'
    digits, remaining = [], n
    while remaining:
        digits.insert(0, remaining % 20)
        remaining //= 20
    return ''.join(str(d) for d in digits)

def vigesimal_to_int(s: str) -> int:
    """base-20 string → int (matches JS Number.parseInt(s, 20))."""
    return int(s, 20)

# ============================================================
# MIXED-RADIX LEVEL COORDINATE
# ============================================================

TICKS = dict(kin=1, uinal=20, tun=360, katun=7200, baktun=144000)
LONG_COUNT_MAX = 13 * TICKS['baktun']   # 1,872,000 days


@dataclass
class LevelCoord:
    """5-place mixed-radix coordinate (radices 20, 18, 20, 20)."""
    baktun: int = 13
    katun:  int = 0
    tun:    int = 0
    uinal:  int = 0     # 0-17 (18 uinals per tun)
    kin:    int = 0

    def __post_init__(self):
        if not (0 <= self.baktun < 20): raise ValueError(f'baktun {self.baktun}')
        if not (0 <= self.katun  < 20): raise ValueError(f'katun {self.katun}')
        if not (0 <= self.tun    < 20): raise ValueError(f'tun {self.tun}')
        if not (0 <= self.uinal  < 18): raise ValueError(f'uinal {self.uinal}')
        if not (0 <= self.kin    < 20): raise ValueError(f'kin {self.kin}')

    def to_days(self) -> int:
        return (self.baktun * TICKS['baktun'] + self.katun * TICKS['katun'] +
                self.tun * TICKS['tun'] + self.uinal * TICKS['uinal'] + self.kin)

    @classmethod
    def from_days(cls, days: int) -> 'LevelCoord':
        days = max(0, int(days)) % LONG_COUNT_MAX
        baktun, days = divmod(days, TICKS['baktun'])
        katun,  days = divmod(days, TICKS['katun'])
        tun,    days = divmod(days, TICKS['tun'])
        uinal,  kin  = divmod(days, TICKS['uinal'])
        return cls(baktun, katun, tun, uinal, kin)

    def advance(self, days: int = 1) -> 'LevelCoord':
        return LevelCoord.from_days(self.to_days() + days)

    # ── Tensor output (matches pi_kuhul.py LevelCoord.to_tensor) ─────────
    # 5 digits × 3 features [bars/3, dots/4, shell] → float32[15]
    def to_tensor(self) -> np.ndarray:
        out = np.zeros(15, dtype=np.float32)
        for i, v in enumerate([self.baktun, self.katun, self.tun, self.uinal, self.kin]):
            v = v % 20
            if v == 0:
                out[i*3 + 2] = 1.0          # shell
            else:
                out[i*3]     = (v // 5) / 3.0
                out[i*3 + 1] = (v  % 5) / 4.0
        return out

    def to_mayan_glyph(self) -> str:
        return ''.join(number_to_mayan(v)
                       for v in [self.baktun, self.katun, self.tun, self.uinal, self.kin])

    @classmethod
    def parse(cls, s: str) -> 'LevelCoord':
        parts = [int(p) for p in s.split('.')]
        if len(parts) != 5:
            raise ValueError(f'Expected b.k.t.u.k got: {s}')
        return cls(*parts)

    def __str__(self) -> str:
        return f'{self.baktun}.{self.katun}.{self.tun}.{self.uinal}.{self.kin}'


# ── Secondary calendars ───────────────────────────────────────────────────────

_TZOLKIN_DAYS = [
    'Imix', 'Ik', 'Akbal', 'Kan', 'Chicchan', 'Cimi', 'Manik', 'Lamat',
    'Muluc', 'Oc', 'Chuen', 'Eb', 'Ben', 'Ix', 'Men', 'Cib', 'Caban',
    'Eznab', 'Cauac', 'Ahau',
]
_HAAB_MONTHS = [
    'Pop', 'Wo', 'Sip', 'Sotz', 'Sek', 'Xul', "Yaxk'in", 'Mol',
    "Ch'en", 'Yax', 'Sak', 'Keh', 'Mak', "K'ank'in", 'Muwan',
    'Pax', "K'ayab", "Kumk'u", 'Wayeb',
]

@dataclass
class Tzolkin:
    """Residue index pair (mod 13, mod 20); period 260."""
    number: int     # 1-13
    day_sign: str   # 20 day names

    @classmethod
    def from_days(cls, days: int) -> 'Tzolkin':
        d = days % 260
        return cls(number=(d % 13) + 1, day_sign=_TZOLKIN_DAYS[d % 20])

    def __str__(self) -> str:
        return f'{self.number} {self.day_sign}'


@dataclass
class Haab:
    """Residue index mod 365 (18 x 20 + 5)."""
    day: int    # 0-19
    month: str

    @classmethod
    def from_days(cls, days: int) -> 'Haab':
        d = days % 365
        return cls(day=d % 20, month=_HAAB_MONTHS[d // 20])

    def __str__(self) -> str:
        return f'{self.day} {self.month}'


@dataclass
class CalendarRound:
    """Joint residue pair (mod 260, mod 365); period lcm = 18,980 = 52 x 365."""
    tzolkin: Tzolkin
    haab: Haab

    PERIOD = 18980

    @classmethod
    def from_days(cls, days: int) -> 'CalendarRound':
        return cls(Tzolkin.from_days(days), Haab.from_days(days))


# ============================================================
# π-GEOMETRY
# ============================================================

class PiGeometry:
    """Phase arithmetic using math.pi — no external deps."""

    TAU = 2 * math.pi

    @staticmethod
    def normalize(phase: float) -> float:
        """Wrap to [0, 2π)."""
        p = phase % PiGeometry.TAU
        return p if p >= 0 else p + PiGeometry.TAU

    @staticmethod
    def difference(p1: float, p2: float) -> float:
        """Shortest angular distance."""
        d = abs(p1 - p2) % PiGeometry.TAU
        return min(d, PiGeometry.TAU - d)

    @staticmethod
    def interference(p1: float, p2: float, a1: float = 1.0, a2: float = 1.0) -> float:
        """Cosine interference: constructive (+) or destructive (-)."""
        return math.cos(PiGeometry.difference(p1, p2)) * a1 * a2

    @staticmethod
    def rotate(phase: float, angle: float) -> float:
        return PiGeometry.normalize(phase + angle)

    @staticmethod
    def from_long_count(lc: LevelCoord) -> float:
        """Map Long Count to π-phase ∈ [0, 2π)."""
        return PiGeometry.normalize(lc.to_days() * math.pi / LONG_COUNT_MAX)


# ============================================================
# MAYAN TENSOR (vigesimal-scaled numpy)
# ============================================================

class MayanTensor:
    """numpy array with vigesimal normalization."""

    VIGESIMAL = 20

    def __init__(self, data: np.ndarray, scale: bool = True):
        self.data = np.asarray(data, dtype=np.float32)
        if scale:
            self.data = self.data / self.VIGESIMAL

    @staticmethod
    def normalize(x: np.ndarray, eps: float = 1e-10) -> np.ndarray:
        n = np.linalg.norm(x)
        return x if n < eps else x / n

    @staticmethod
    def coherence(phases: np.ndarray, amps: Optional[np.ndarray] = None) -> float:
        """Mean pairwise cosine interference."""
        n = len(phases)
        if n < 2:
            return 0.0
        if amps is None:
            amps = np.ones(n)
        total = 0.0
        for i in range(n):
            for j in range(i + 1, n):
                total += 2 * amps[i] * amps[j] * math.cos(PiGeometry.difference(phases[i], phases[j]))
        return total / (n * (n - 1))

    def to_glyphs(self) -> List[str]:
        return [number_to_mayan(int(abs(v) * self.VIGESIMAL) % 20)
                for v in self.data.flatten()]

    @classmethod
    def from_glyphs(cls, glyphs: List[str]) -> 'MayanTensor':
        return cls(np.array([mayan_to_number(g) for g in glyphs], dtype=np.float32))


# ============================================================
# BATCH TENSOR FACTORIES
# (match Python training helpers in pi_kuhul_train.py)
# ============================================================

def make_maya_coords(batch_size: int, seq_len: int, step: int) -> np.ndarray:
    """
    [B, T, 15] float32 — matches pi_kuhul_train.py make_maya_coords().
    Each slot is the LevelCoord tensor for the given training step.
    """
    lc   = LevelCoord.from_days(0).advance(step)
    base = lc.to_tensor()                          # [15]
    return np.tile(base, (batch_size, seq_len, 1))

def make_phases(batch_size: int, seq_len: int, pi_time: float) -> np.ndarray:
    """[B, T] float32 — matches pi_kuhul_train.py make_phases()."""
    pos   = np.arange(seq_len, dtype=np.float32)
    phase = (pos * math.pi / seq_len + pi_time) % (2 * math.pi)
    return np.tile(phase, (batch_size, 1))


# ============================================================
# π-KUHUL FIELD ENGINE
# ============================================================

@dataclass
class Token:
    """Particle on 100D manifold."""
    position:       np.ndarray
    velocity:       np.ndarray
    phase:          float
    phase_velocity: float
    long_count:     LevelCoord
    shard_id:       int
    coherence:      float = 0.0

    @classmethod
    def random(cls, dims: int = 100) -> 'Token':
        return cls(
            position       = np.random.randn(dims) * 2,
            velocity       = np.random.randn(dims) * 0.1,
            phase          = np.random.random() * 2 * math.pi,
            phase_velocity = np.random.random() * 0.5,
            long_count     = LevelCoord.from_days(np.random.randint(0, LONG_COUNT_MAX)),
            shard_id       = 0,
        )


@dataclass
class SliceField:
    """One slice in the 64-slice layer stack — owns a slice of the 100D field."""
    amplitude:          np.ndarray
    gradient:           np.ndarray
    curvature:          np.ndarray
    pi_mod:             float
    level_digit:        int
    adjacency:          List[int]
    adjacency_strength: List[float]

    @property
    def maya_digit(self) -> int:
        """Back-compat alias for the slice's level digit."""
        return self.level_digit


class PiKuhulFieldEngine:
    """
    100D manifold field-theoretic engine.
    Drives coherence-based shard routing identical to the neural
    TokenShardRouter in pi_kuhul.py, but as a physics simulation.
    """

    def __init__(self, num_tokens: int = 1024, num_slices: int = 64, num_cards: Optional[int] = None,
                 dimensions: int = 100, dt: float = 0.01,
                 sigma: float = 0.15, temperature: float = 0.2):
        self.num_tokens  = num_tokens
        self.num_slices  = num_slices if num_cards is None else num_cards
        self.dimensions  = dimensions
        self.dt          = dt
        self.sigma       = sigma
        self.temperature = temperature

        self.tokens:     List[Token]     = []
        self.cards:      List[SliceField] = []
        self.pi_time     = 0.0
        self.global_lc   = LevelCoord(13, 0, 0, 0, 0)
        self.shard_transitions = 0
        self.coherence_history: List[float] = []
        self.phase_history:     List[float] = []

        self._init()

    @property
    def num_cards(self) -> int:
        """Back-compat alias for the slice count."""
        return self.num_slices

    def _init(self):
        for _ in range(self.num_tokens):
            t = Token.random(self.dimensions)
            t.shard_id = np.random.randint(0, self.num_slices)
            self.tokens.append(t)

        for i in range(self.num_slices):
            adj  = [(i + j) % self.num_slices for j in range(1, 9)]
            astr = [1.0 / j for j in range(1, 9)]
            self.cards.append(SliceField(
                amplitude          = np.random.randn(4) * 2,
                gradient           = np.random.randn(4) * 0.5,
                curvature          = np.random.randn(4) * 0.2,
                pi_mod             = np.random.random() * 2,
                level_digit        = i % 20,
                adjacency          = adj,
                adjacency_strength = astr,
            ))

    # ── Geodesic distance on curved submanifold ───────────────────────────────
    def geodesic_dist(self, p1: np.ndarray, p2: np.ndarray,
                      curvature: np.ndarray) -> float:
        d = np.linalg.norm(p1[:16] - p2[:16])
        return d * (1 + curvature[0] * d * d / 6.0)

    # ── Single timestep ───────────────────────────────────────────────────────
    def step(self) -> float:
        self.pi_time = PiGeometry.normalize(self.pi_time + self.dt * 0.1)
        total_coh = 0.0

        for i, tok in enumerate(self.tokens):
            card = self.cards[tok.shard_id % self.num_slices]

            # Phase evolution
            tok.phase = PiGeometry.rotate(tok.phase,
                                          self.dt * (card.pi_mod + self.pi_time * 0.1))
            if tok.long_count.uinal == 0 and tok.long_count.kin == 0:
                tok.phase = self.pi_time     # sync at uinal boundary

            amp_local = float(np.sum(card.amplitude))
            net_force = np.zeros(4)
            total_int = 0.0
            trans_pot = 0.0

            for j, other in enumerate(self.tokens):
                if i == j:
                    continue
                other_card = self.cards[other.shard_id % self.num_slices]
                same_shard = (other.shard_id == tok.shard_id)
                adjacent   = same_shard or (other.shard_id in card.adjacency)
                if not adjacent:
                    continue

                dist   = self.geodesic_dist(tok.position[:16],
                                            other.position[:16], card.curvature)
                intf   = PiGeometry.interference(tok.phase, other.phase,
                                                 amp_local,
                                                 float(np.sum(other_card.amplitude)))
                weight = math.exp(-dist * dist / (2 * self.sigma ** 2)) * abs(intf)

                diff   = other.position[:4] - tok.position[:4]
                norm   = np.linalg.norm(diff)
                if norm > 1e-6:
                    net_force += (diff / norm) * weight * (1.0 if intf > 0 else -1.0)
                total_int += abs(intf)
                if intf > 0.5 and other.shard_id != tok.shard_id:
                    trans_pot += intf

            if total_int > 0:
                net_force /= total_int
            net_force += card.gradient[:4]

            tok.velocity[:4] = tok.velocity[:4] * 0.95 + net_force * self.dt
            tok.position[:4] += tok.velocity[:4] * self.dt
            for d in range(4, self.dimensions):
                tok.position[d] += math.sin(tok.position[d % 4]) * 0.01 * self.dt

            # Level coordinate advance
            mag = max(1, int(abs(np.linalg.norm(tok.position[:4])) * 10))
            tok.long_count = tok.long_count.advance(mag)

            # Shard transition
            phase_wrap = tok.phase < self.dt * card.pi_mod
            if phase_wrap or trans_pot > 1.0:
                target_digit = int(abs(tok.position[0]) * 20) % 20
                new_shard    = tok.shard_id
                for adj in card.adjacency:
                    if adj < self.num_slices and self.cards[adj].level_digit == target_digit:
                        new_shard = adj
                        break
                if np.random.random() < self.temperature:
                    new_shard = card.adjacency[np.random.randint(0, min(8, len(card.adjacency)))]
                if new_shard != tok.shard_id:
                    self.shard_transitions += 1
                    tok.shard_id = new_shard

            tok.coherence = tok.coherence * 0.99 + (total_int / 100.0 if total_int else 0.0)
            total_coh += tok.coherence

        self.global_lc = self.global_lc.advance(1)
        avg_coh = total_coh / self.num_tokens
        self.coherence_history.append(avg_coh)
        self.phase_history.append(
            float(np.mean([t.phase for t in self.tokens])) / (2 * math.pi) * 100
        )
        return avg_coh

    def run(self, steps: int = 1000, callback=None) -> Dict:
        t0 = datetime.now()
        for s in range(steps):
            coh = self.step()
            if callback and s % 10 == 0:
                callback(s, coh, self.metrics())
            elif s % 100 == 0:
                print(f'step {s:5d} | coherence {coh*100:.1f}% | '
                      f'LC {self.global_lc} | pi {self.pi_time:.3f}')
        elapsed = (datetime.now() - t0).total_seconds()
        return {
            'final_coherence': self.coherence_history[-1] if self.coherence_history else 0.0,
            'avg_coherence':   float(np.mean(self.coherence_history)) if self.coherence_history else 0.0,
            'shard_transitions': self.shard_transitions,
            'time_seconds': elapsed,
            'steps_per_second': steps / max(elapsed, 1e-9),
        }

    def metrics(self) -> Dict:
        avg_coh   = float(np.mean([t.coherence for t in self.tokens]))
        avg_phase = float(np.mean([t.phase for t in self.tokens]))
        days      = self.global_lc.to_days()
        return {
            'coherence':         avg_coh,
            'avg_phase':         avg_phase,
            'pi_time':           self.pi_time,
            'global_long_count': str(self.global_lc),
            'shard_transitions': self.shard_transitions,
            'active_tokens':     sum(1 for t in self.tokens if t.coherence > 0.1),
            'tzolkin':           str(Tzolkin.from_days(days)),
            'haab':              str(Haab.from_days(days)),
            'calendar_round':    f'{Tzolkin.from_days(days)} / {Haab.from_days(days)}',
        }


# ============================================================
# CLI
# ============================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(description='pi-KUHUL Field Inference Engine')
    parser.add_argument('--tokens',      type=int,   default=256)
    parser.add_argument('--steps',       type=int,   default=500)
    parser.add_argument('--temperature', type=float, default=0.2)
    parser.add_argument('--dt',          type=float, default=0.01)
    parser.add_argument('--seed',        type=int,   default=None)
    args = parser.parse_args()

    if args.seed is not None:
        np.random.seed(args.seed)

    print(f'\npi-KUHUL Field Engine | tokens={args.tokens} steps={args.steps}')
    print(f'100D manifold | Maya base-20 | pi-phase geodesic flow\n')

    engine = PiKuhulFieldEngine(
        num_tokens=args.tokens,
        dt=args.dt,
        temperature=args.temperature,
    )

    results = engine.run(args.steps)
    m = engine.metrics()

    print(f'\nFinal coherence:   {results["final_coherence"]*100:.2f}%')
    print(f'Average coherence: {results["avg_coherence"]*100:.2f}%')
    print(f'Shard transitions: {results["shard_transitions"]}')
    print(f'Speed: {results["steps_per_second"]:.1f} steps/s')
    print(f'Long Count: {m["global_long_count"]}')
    print(f'Tzolk\'in:   {m["tzolkin"]}')
    print(f'Haab:       {m["haab"]}')
    print(f'pi-time:    {m["pi_time"]/math.pi:.4f}pi')


if __name__ == '__main__':
    main()


# ── Back-compat aliases (old vocabulary) ─────────────────────────────────────
LongCount = LevelCoord
CardField = SliceField