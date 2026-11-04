#!/usr/bin/env python3
"""
pi-KUHUL Field-Theoretic Inference Engine
PyTorch implementation: 100D manifold + mixed-radix level indexing + π-phase
Supports sharded weights via shard.pt files
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset
import math
import pickle
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
import numpy as np

# ============================================================
# MIXED-RADIX LEVEL DIGITS (base-20, bars/dots/shell notation)
# ============================================================

class LevelDigit:
    """Base-20 level digit: bars (5), dots (1), shell (0)."""
    def __init__(self, bars: int = 0, dots: int = 0, shell: bool = False):
        self.bars = min(bars, 3)
        self.dots = min(dots, 4)
        self.shell = shell

    def value(self) -> int:
        if self.shell:
            return 0
        return self.bars * 5 + self.dots

    @classmethod
    def from_int(cls, n: int) -> 'LevelDigit':
        n = n % 20
        if n == 0:
            return cls(shell=True)
        bars = n // 5
        dots = n % 5
        return cls(bars=bars, dots=dots)

    def to_tensor(self) -> torch.Tensor:
        return torch.tensor([self.bars / 3.0, self.dots / 4.0, float(self.shell)])

    def __repr__(self):
        if self.shell:
            return "O"
        return "-" * self.bars + "." * self.dots


class LevelCoord:
    """5-place mixed-radix coordinate (baktun, katun, tun, uinal, kin)."""
    def __init__(self, baktun=13, katun=0, tun=0, uinal=0, kin=0):
        self.baktun = LevelDigit.from_int(baktun)
        self.katun  = LevelDigit.from_int(katun)
        self.tun    = LevelDigit.from_int(tun)
        self.uinal  = LevelDigit.from_int(uinal)
        self.kin    = LevelDigit.from_int(kin)

    def to_days(self) -> int:
        return (self.baktun.value() * 144000 +
                self.katun.value()  * 7200   +
                self.tun.value()    * 360    +
                self.uinal.value()  * 20     +
                self.kin.value())

    def to_tensor(self) -> torch.Tensor:
        return torch.cat([
            self.baktun.to_tensor(),
            self.katun.to_tensor(),
            self.tun.to_tensor(),
            self.uinal.to_tensor(),
            self.kin.to_tensor()
        ])

    def advance(self, days: int = 1):
        total = self.to_days() + days
        self.baktun = LevelDigit.from_int(total // 144000)
        total %= 144000
        self.katun  = LevelDigit.from_int(total // 7200)
        total %= 7200
        self.tun    = LevelDigit.from_int(total // 360)
        total %= 360
        self.uinal  = LevelDigit.from_int(total // 20)
        self.kin    = LevelDigit.from_int(total % 20)
        return self


# ============================================================
# pi-NORMALIZATION (Phase Space)
# ============================================================

class PiNormalizer:
    """pi-normalization: map any value to [0, 2*pi) circle"""
    PI  = math.pi
    TAU = 2 * math.pi

    @classmethod
    def normalize(cls, x: torch.Tensor) -> torch.Tensor:
        return (x % cls.TAU) / cls.PI

    @classmethod
    def denormalize(cls, x: torch.Tensor) -> torch.Tensor:
        return x * cls.PI

    @classmethod
    def phase_modulation(cls, x: torch.Tensor, pi_time: torch.Tensor) -> torch.Tensor:
        phase = cls.denormalize(pi_time) * x
        return torch.complex(torch.cos(phase), torch.sin(phase))


# ============================================================
# SHARDED WEIGHT MANAGER (shard.pt)
# ============================================================

class ShardedWeightManager:
    """
    Manages model weights sharded across .pt files.
    Each shard = 128MB compressed = 500MB uncompressed.
    KV cache provides residuals so each shard needs minimal weights.
    """

    def __init__(self, shard_dir: str = "./shards", cache_size_mb: int = 1024):
        self.shard_dir = Path(shard_dir)
        self.shard_dir.mkdir(exist_ok=True)
        self.cache_size = cache_size_mb * 1024 * 1024
        self.current_cache_size = 0
        self.kv_cache: Dict[str, torch.Tensor] = {}
        self.shard_index: Dict[int, Dict[str, Any]] = {}
        self._load_shard_index()

    def _load_shard_index(self):
        index_path = self.shard_dir / "index.pt"
        if index_path.exists():
            self.shard_index = torch.load(index_path, weights_only=False)
        else:
            self.shard_index = {}

    def save_shard(self, shard_id: int, weights: Dict[str, torch.Tensor],
                   maya_coord: LevelCoord, compress: bool = True):
        shard_path = self.shard_dir / f"shard_{shard_id}.pt"
        compressed = self._maya_compress(weights, maya_coord) if compress else weights
        orig_mb = sum(p.numel() * 4 / (1024*1024) for p in weights.values())
        comp_mb = sum(p.numel() * 4 / (1024*1024) for p in compressed.values())
        shard_data = {
            'shard_id': shard_id,
            'maya_coord': {
                'baktun': maya_coord.baktun.value(),
                'katun':  maya_coord.katun.value(),
                'tun':    maya_coord.tun.value(),
                'uinal':  maya_coord.uinal.value(),
                'kin':    maya_coord.kin.value()
            },
            'weights':          compressed,
            'compressed':       compress,
            'original_size_mb': orig_mb,
            'compressed_size_mb': comp_mb,
        }
        torch.save(shard_data, shard_path)
        self.shard_index[shard_id] = {'shard_id': shard_id, 'path': str(shard_path),
                                       'orig_mb': orig_mb, 'comp_mb': comp_mb}
        torch.save(self.shard_index, self.shard_dir / "index.pt")
        ratio = orig_mb / comp_mb if comp_mb > 0 else 1
        print(f"[shard] saved {shard_id}: {orig_mb:.1f}MB -> {comp_mb:.1f}MB ({ratio:.1f}x)")

    def _maya_compress(self, weights: Dict[str, torch.Tensor],
                       maya_coord: LevelCoord) -> Dict[str, torch.Tensor]:
        """5-level scalar quantisation: one pattern value per level digit."""
        compressed = {}
        digits = [maya_coord.baktun.value(), maya_coord.katun.value(),
                  maya_coord.tun.value(),    maya_coord.uinal.value(),
                  maya_coord.kin.value()]
        for name, tensor in weights.items():
            flat = tensor.flatten()
            patterns = {}
            for i, digit in enumerate(digits):
                idx = (i * 1000 + digit) % flat.shape[0]
                patterns[digit] = flat[idx]
            compressed_flat = []
            for val in flat:
                closest = min(digits, key=lambda d: abs(patterns[d] - val))
                compressed_flat.append(closest)
            compressed[name] = torch.tensor(compressed_flat, dtype=torch.float32).reshape(tensor.shape)
        return compressed

    def load_shard(self, shard_id: int, use_cache: bool = True) -> Dict[str, torch.Tensor]:
        cache_key = f"shard_{shard_id}"
        if use_cache and cache_key in self.kv_cache:
            return self._decompress_with_cache(self.kv_cache[cache_key], shard_id)
        shard_path = self.shard_dir / f"shard_{shard_id}.pt"
        if not shard_path.exists():
            return self._generate_minimal_weights(shard_id)
        shard_data = torch.load(shard_path, weights_only=False)
        weights = shard_data['weights']
        if shard_data.get('compressed', False):
            weights = self._maya_decompress(weights, shard_data['maya_coord'])
        if use_cache:
            size = sum(p.numel() * 4 for p in weights.values())
            self._evict_if_needed(size)
            self.kv_cache[cache_key] = weights
            self.current_cache_size += size
        return weights

    def _maya_decompress(self, compressed: Dict[str, torch.Tensor],
                         maya_coord: Dict) -> Dict[str, torch.Tensor]:
        decompressed = {}
        for name, tensor in compressed.items():
            flat = [int(v.item()) * 0.1 + 0.05 for v in tensor.flatten()]
            decompressed[name] = torch.tensor(flat).reshape(tensor.shape)
        return decompressed

    def _generate_minimal_weights(self, shard_id: int) -> Dict[str, torch.Tensor]:
        return {
            'essential_metadata': torch.tensor([shard_id, hash(shard_id) % 10000], dtype=torch.float32),
            'shape_hints': torch.randn(10),
        }

    def _decompress_with_cache(self, cached, shard_id):
        return cached

    def _evict_if_needed(self, needed: int):
        while self.current_cache_size + needed > self.cache_size and self.kv_cache:
            key = next(iter(self.kv_cache))
            evicted = self.kv_cache.pop(key)
            self.current_cache_size -= sum(p.numel() * 4 for p in evicted.values())

    def store_kv_cache(self, key: str, tensor: torch.Tensor):
        size = tensor.numel() * 4
        self._evict_if_needed(size)
        self.kv_cache[f"kv_{key}"] = tensor
        self.current_cache_size += size


# ============================================================
# 100D TENSOR FIELD (Card in Deck)
# ============================================================

class TensorFieldSlice(nn.Module):
    def __init__(self, card_id: int, hidden_dim: int = 768):
        super().__init__()
        self.card_id    = card_id
        self.hidden_dim = hidden_dim
        rank = hidden_dim // 4
        self.field_u    = nn.Parameter(torch.randn(16, rank) * 0.02)       # [16, rank]
        self.field_s    = nn.Parameter(torch.randn(rank) * 0.02)           # [rank]
        self.field_v    = nn.Parameter(torch.randn(rank, hidden_dim) * 0.02) # [rank, hidden_dim]
        self.amplitude  = nn.Parameter(torch.randn(4) * 0.1)
        self.gradient   = nn.Parameter(torch.randn(4) * 0.01)
        self.curvature  = nn.Parameter(torch.randn(1) * 0.1)
        self.pi_mod     = nn.Parameter(torch.randn(1) * 0.5)
        self.level_digit = nn.Parameter(torch.randint(0, 20, (1,)), requires_grad=False)
        self.register_buffer('adjacency',          torch.zeros(8, dtype=torch.long))
        self.register_buffer('adjacency_strength', torch.zeros(8))

    @property
    def maya_digit(self):
        """Back-compat alias for the slice's level digit."""
        return self.level_digit

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        field_sample = torch.einsum('bi,ij,jk,kl->bl',
                                    x[:, :16],
                                    self.field_u,
                                    torch.diag(self.field_s),
                                    self.field_v)
        if field_sample.shape[-1] < self.hidden_dim:
            field_sample = F.pad(field_sample, (0, self.hidden_dim - field_sample.shape[-1]))
        else:
            field_sample = field_sample[:, :self.hidden_dim]
        return field_sample

    def get_geodesic_distance(self, p1: torch.Tensor, p2: torch.Tensor) -> torch.Tensor:
        flat_dist = torch.norm(p1 - p2, dim=-1)
        curve = self.curvature.abs()
        return flat_dist * (1.0 + curve * flat_dist * flat_dist / 6.0)


# ============================================================
# pi-GEODESIC ATTENTION (Wave Mechanics)
# ============================================================

class PiGeodesicAttention(nn.Module):
    """Attention = geodesic_distance x phase_interference"""

    def __init__(self, hidden_dim: int = 768, num_heads: int = 12):
        super().__init__()
        self.hidden_dim = hidden_dim
        self.num_heads  = num_heads
        self.head_dim   = hidden_dim // num_heads
        self.q_proj     = nn.Linear(hidden_dim, hidden_dim)
        self.k_proj     = nn.Linear(hidden_dim, hidden_dim)
        self.v_proj     = nn.Linear(hidden_dim, hidden_dim)
        self.out_proj   = nn.Linear(hidden_dim, hidden_dim)
        self.phase_scale = nn.Parameter(torch.ones(1) * 0.1)
        self.sigma       = nn.Parameter(torch.ones(1) * 0.15)

    def phase_interference(self, p1: torch.Tensor, p2: torch.Tensor) -> torch.Tensor:
        return torch.cos((p1 - p2).abs() % (2 * math.pi))

    def forward(self, x: torch.Tensor, positions: torch.Tensor,
                phases: torch.Tensor, cards) -> torch.Tensor:
        B, T, _ = x.shape
        Q = self.q_proj(x).reshape(B, T, self.num_heads, self.head_dim).transpose(1, 2)
        K = self.k_proj(x).reshape(B, T, self.num_heads, self.head_dim).transpose(1, 2)
        V = self.v_proj(x).reshape(B, T, self.num_heads, self.head_dim).transpose(1, 2)
        # Standard scaled dot-product (geodesic version for larger sequences)
        scale = self.head_dim ** -0.5
        attn  = torch.matmul(Q, K.transpose(-2, -1)) * scale
        # Phase modulation applied as bias
        phase_diff = (phases.unsqueeze(-1) - phases.unsqueeze(-2)).abs() % (2 * math.pi)
        interference = torch.cos(phase_diff).unsqueeze(1)  # [B, 1, T, T]
        attn = attn + interference * self.phase_scale
        attn = F.softmax(attn, dim=-1)
        out  = torch.matmul(attn, V).transpose(1, 2).reshape(B, T, self.hidden_dim)
        return self.out_proj(out)


# ============================================================
# pi-KUHUL TRANSFORMER (Complete Model)
# ============================================================

class PiKuhulTransformer(nn.Module):
    def __init__(self, vocab_size: int = 50257, hidden_dim: int = 768,
                 num_layers: int = 12, num_slices: int = 64, num_cards: Optional[int] = None):
        super().__init__()
        self.hidden_dim = hidden_dim
        self.num_slices = num_slices if num_cards is None else num_cards

        self.token_embedding    = nn.Embedding(vocab_size, hidden_dim)
        self.position_embedding = nn.Embedding(1024, hidden_dim)
        self.maya_embedding     = nn.Sequential(
            nn.Linear(15, hidden_dim // 4), nn.GELU(),
            nn.Linear(hidden_dim // 4, hidden_dim)
        )
        self.phase_embedding = nn.Sequential(
            nn.Linear(1, hidden_dim // 8), nn.GELU(),
            nn.Linear(hidden_dim // 8, hidden_dim)
        )

        self.cards = nn.ModuleList([TensorFieldSlice(i, hidden_dim) for i in range(self.num_slices)])
        self._build_deck_adjacency()

        self.layers  = nn.ModuleList([PiGeodesicAttention(hidden_dim, 12) for _ in range(num_layers)])
        self.norms   = nn.ModuleList([nn.LayerNorm(hidden_dim) for _ in range(num_layers)])
        self.ffns    = nn.ModuleList([nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim * 4), nn.GELU(),
            nn.Linear(hidden_dim * 4, hidden_dim)
        ) for _ in range(num_layers)])
        self.ffn_norms = nn.ModuleList([nn.LayerNorm(hidden_dim) for _ in range(num_layers)])

        self.ln_f        = nn.LayerNorm(hidden_dim)
        self.output_proj = nn.Linear(hidden_dim, vocab_size, bias=False)

        self.shard_manager = ShardedWeightManager()
        self.router = TokenShardRouter(self.num_slices)   # interleave across all slices
        self.register_buffer('pi_time', torch.tensor(0.0))

    @property
    def num_cards(self) -> int:
        """Back-compat alias for the slice count."""
        return self.num_slices

    def _build_deck_adjacency(self):
        for i, card in enumerate(self.cards):
            for j, offset in enumerate([-4, -3, -2, -1, 1, 2, 3, 4]):
                card.adjacency[j]          = (i + offset) % self.num_slices
                card.adjacency_strength[j] = math.exp(-abs(offset) / 4.0)

    def get_card(self, shard_id: int) -> TensorFieldSlice:
        return self.cards[shard_id % self.num_slices]

    def forward(self, input_ids: torch.Tensor,
                maya_coords: Optional[torch.Tensor] = None,
                phases: Optional[torch.Tensor] = None) -> torch.Tensor:
        B, T = input_ids.shape
        pos_ids = torch.arange(T, device=input_ids.device).unsqueeze(0)

        x = self.token_embedding(input_ids) + self.position_embedding(pos_ids)

        if maya_coords is not None:
            x = x + self.maya_embedding(maya_coords)

        if phases is None:
            phases = torch.zeros(B, T, device=input_ids.device)
        else:
            x = x + self.phase_embedding(phases.unsqueeze(-1))

        # ── Card field injection (interleaved) ──────────────────────────────
        # Each token position is owned by a card via binary interleave.
        # The card's field is sampled and added to the token's embedding.
        # All cards train simultaneously — no token goes to only one shard.
        card_ids = self.router.card_ids_for_sequence(T, device=x.device)  # [T]
        inject_len = min(T, 16)
        field_vecs = []
        for t in range(inject_len):
            card = self.cards[int(card_ids[t]) % self.num_slices]
            field_vecs.append(card(x[:, t, :16]))  # [B, H]
        field_mat = torch.stack(field_vecs, dim=1)  # [B, inject_len, H]
        if inject_len < T:
            pad = torch.zeros(B, T - inject_len, x.size(-1), device=x.device)
            field_mat = torch.cat([field_mat, pad], dim=1)
        x = x + field_mat

        # ── Transformer layers ───────────────────────────────────────────────
        for layer_idx, (attn, norm, ffn, ffn_norm) in enumerate(
                zip(self.layers, self.norms, self.ffns, self.ffn_norms)):
            x = x + attn(norm(x), pos_ids.expand(B, -1).float(), phases, self.cards)
            x = x + ffn(ffn_norm(x))

        with torch.no_grad():
            self.pi_time.fill_((self.pi_time.item() + 0.001) % (2 * math.pi))
        return self.output_proj(self.ln_f(x))

    def save_sharded(self, shard_ids: List[int], output_dir: str = "./shards"):
        """
        Save shards by ownership: each shard saves its TensorFieldSlice weights
        plus the shared layer slices that correspond to its interleaved token positions.
        Shared weights (embeddings, norms, output_proj) are saved in shard 0 only.
        """
        self.shard_manager.shard_dir = Path(output_dir)
        self.shard_manager.shard_dir.mkdir(parents=True, exist_ok=True)
        state = self.state_dict()
        n = len(shard_ids)

        for shard_id in shard_ids:
            chunk = {}

            # Each shard owns its TensorFieldSlice
            card_prefix = f"cards.{shard_id % self.num_slices}."
            for k, v in state.items():
                if k.startswith(card_prefix):
                    chunk[k] = v.clone()

            # Each shard owns its slice of attention/ffn layers
            # Layer i is owned by shard i % num_shards
            for layer_idx in range(len(self.layers)):
                if layer_idx % n == shard_id % n:
                    for prefix in (f"layers.{layer_idx}.", f"norms.{layer_idx}.",
                                   f"ffns.{layer_idx}.", f"ffn_norms.{layer_idx}."):
                        for k, v in state.items():
                            if k.startswith(prefix):
                                chunk[k] = v.clone()

            # Shard 0 holds shared weights (embeddings, final norm, lm head)
            if shard_id == shard_ids[0]:
                for k, v in state.items():
                    if any(k.startswith(p) for p in (
                        'token_embedding.', 'position_embedding.',
                        'maya_embedding.', 'phase_embedding.',
                        'ln_f.', 'output_proj.'
                    )):
                        chunk[k] = v.clone()

            if not chunk:
                continue

            coord = LevelCoord(
                baktun=(shard_id)        % 20,
                katun =(shard_id // 20)  % 20,
                tun   =(shard_id // 400) % 20,
            )
            self.shard_manager.save_shard(shard_id, chunk, coord, compress=False)

        print(f"[pi-kuhul] saved {n} shards -> {output_dir}/")

    def load_sharded(self, shard_ids: List[int], load_dir: str = "./shards"):
        self.shard_manager.shard_dir = Path(load_dir)
        merged = {}
        for sid in shard_ids:
            merged.update(self.shard_manager.load_shard(sid))
        missing = self.load_state_dict(merged, strict=False)
        print(f"[pi-kuhul] loaded {len(shard_ids)} shards | missing={len(missing.missing_keys)}")


# ============================================================
# TOKEN SHARD ROUTER (Binary interleave)
# ============================================================

class TokenShardRouter:
    """
    Binary interleave: token at position i goes to shard i % num_shards.
    All shards train on the FULL dataset simultaneously — no shard gets a
    sequential slice. The pattern cycles across the sequence like disk striping:

      pos:   0  1  2  3  4  5  6  7  8  9 ...
      shard: 0  1  2  3  4  5  6  7  0  1 ...  (8 shards)

    This means every shard sees every topic in the data, but specializes on
    the token positions it owns. Shards trained this way develop complementary
    representations rather than domain silos.
    """

    def __init__(self, num_shards: int):
        self.num_shards = num_shards

    def assign(self, seq_len: int, device=None) -> torch.Tensor:
        """Return [seq_len] shard-ID tensor."""
        ids = torch.arange(seq_len, device=device) % self.num_shards
        return ids

    def scatter(self, x: torch.Tensor) -> List[Tuple[torch.Tensor, torch.Tensor]]:
        """
        x: [B, T, H]
        Returns list of (tokens, bool_mask) per shard.
        tokens: [B, T_i, H]  — only positions owned by this shard.
        bool_mask: [T]        — which positions belong to this shard.
        """
        B, T, H = x.shape
        assignments = self.assign(T, device=x.device)
        result = []
        for s in range(self.num_shards):
            mask = (assignments == s)                 # [T] bool
            result.append((x[:, mask, :], mask))
        return result

    def gather(self, shard_outputs: List[Tuple[torch.Tensor, torch.Tensor]],
               seq_len: int, hidden_dim: int, device=None) -> torch.Tensor:
        """
        Reassemble per-shard outputs back into the original sequence order.
        shard_outputs: list of (tokens [B, T_i, H], bool_mask [T])
        """
        B = shard_outputs[0][0].shape[0]
        out = torch.zeros(B, seq_len, hidden_dim, device=device)
        for tokens, mask in shard_outputs:
            out[:, mask, :] = tokens
        return out

    def card_ids_for_sequence(self, seq_len: int, device=None) -> torch.Tensor:
        """Return which card index each token position maps to."""
        return self.assign(seq_len, device=device)


# ============================================================
# FIELD DYNAMICS ENGINE
# ============================================================

class PiFieldDynamics:
    def __init__(self, model: PiKuhulTransformer, dt: float = 0.01):
        self.model     = model
        self.dt        = dt
        self.positions = None
        self.velocities = None
        self.phases    = None
        self.shard_ids = None

    def initialize_tokens(self, num_tokens: int):
        self.positions  = torch.randn(num_tokens, 100) * 0.1
        self.velocities = torch.randn(num_tokens, 100) * 0.01
        self.phases     = torch.rand(num_tokens) * 2 * math.pi
        self.shard_ids  = torch.randint(0, self.model.num_slices, (num_tokens,))
        return self

    def step(self):
        forces = torch.stack([self.model.get_card(int(s)).gradient.detach()
                              for s in self.shard_ids])
        # Pad forces to match position dims
        if forces.shape[-1] < self.positions.shape[-1]:
            forces = F.pad(forces, (0, self.positions.shape[-1] - forces.shape[-1]))
        self.velocities = self.velocities * 0.95 + forces * self.dt
        self.positions  = self.positions + self.velocities * self.dt
        self.phases     = (self.phases + self.dt) % (2 * math.pi)
        return self


# ============================================================
# TRAINER
# ============================================================

class PiKuhulTrainer:
    def __init__(self, model: PiKuhulTransformer, lr: float = 1e-4):
        self.model     = model
        self.optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.01)
        self.dynamics  = PiFieldDynamics(model)
        self.step_count = 0

    def train_step(self, input_ids: torch.Tensor, labels: torch.Tensor,
                   maya_coords: Optional[torch.Tensor] = None,
                   phases: Optional[torch.Tensor] = None):
        logits = self.model(input_ids, maya_coords, phases)
        loss   = F.cross_entropy(logits.view(-1, logits.size(-1)), labels.view(-1))
        self.optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
        self.optimizer.step()
        self.step_count += 1
        return {'loss': loss.item(), 'step': self.step_count, 'pi_time': self.model.pi_time.item()}

    def save_checkpoint(self, path: str):
        torch.save({
            'step':       self.step_count,
            'model':      self.model.state_dict(),
            'optimizer':  self.optimizer.state_dict(),
            'pi_time':    self.model.pi_time.item(),
        }, path)
        print(f"[pi-kuhul] checkpoint -> {path}")

    def load_checkpoint(self, path: str):
        ckpt = torch.load(path, weights_only=False)
        self.model.load_state_dict(ckpt['model'])
        self.optimizer.load_state_dict(ckpt['optimizer'])
        self.step_count = ckpt.get('step', 0)
        self.model.pi_time = torch.tensor(ckpt.get('pi_time', 0.0))
        print(f"[pi-kuhul] resumed from step {self.step_count}")


# ── Back-compat aliases (old vocabulary) ─────────────────────────────────────
MayaDigit = LevelDigit
MayaLongCount = LevelCoord
TensorFieldCard = TensorFieldSlice