#!/usr/bin/env python3
"""
pi-KUHUL Training Script
Trains PiKuhulTransformer on smgm-16 combined_train.jsonl
Saves shard_*.pt files + full checkpoints

Usage:
  python pi_kuhul_train.py
  python pi_kuhul_train.py --resume checkpoints/step_1000.pt
  python pi_kuhul_train.py --steps 5000 --batch 4 --lr 3e-4
"""

import sys, os, argparse, json, math, time, zlib
from pathlib import Path

import torch
from torch.utils.data import DataLoader, Dataset

# Locate pi_kuhul.py in same directory
sys.path.insert(0, str(Path(__file__).parent))
from pi_kuhul import PiKuhulTransformer, PiKuhulTrainer, LevelCoord
from glyph_tokenizer import GlyphTokenizer

# ─── Paths ────────────────────────────────────────────────────────────────────

TRAIN_DATA   = Path("C:/public_html/data/glyph-corpus-v3.jsonl")
VAL_DATA     = Path("C:/Users/canna/.gpu_trainer/trainer/xshard_val.jsonl")
CKPT_DIR     = Path("C:/Users/canna/.gpu_trainer/trainer/pi_kuhul_checkpoints")
DEFAULT_SHARD_DIR = Path("C:/Users/canna/.gpu_trainer/trainer/pi_kuhul_shards")

# ─── Simple word tokenizer (no external deps) ────────────────────────────────

class WordTokenizer:
    """
    Word-level tokenizer backed by the GPT-2 vocab size (50257).
    Maps words to stable IDs via hash. Used for pi-kuhul Run 1 (tiles_final).
    For new runs with glyph vocab, use --tokenizer glyph (GlyphTokenizer).
    """
    PAD = 0
    BOS = 1
    EOS = 2
    UNK = 3
    VOCAB_SIZE = 50257

    def encode(self, text: str, max_len: int = 512) -> list:
        tokens = [self.BOS]
        for word in text.split():
            tid = (zlib.crc32(word.encode()) & 0x7FFFFFFF) % (self.VOCAB_SIZE - 4) + 4
            tokens.append(tid)
        tokens.append(self.EOS)
        tokens = tokens[:max_len]
        tokens += [self.PAD] * (max_len - len(tokens))
        return tokens


# ─── Dataset ─────────────────────────────────────────────────────────────────

class SMGMDataset(Dataset):
    def __init__(self, jsonl_path: Path, max_len: int = 128, max_samples: int = None,
                 tokenizer=None):
        self.tokenizer = tokenizer if tokenizer is not None else WordTokenizer()
        self.max_len   = max_len
        self.records   = []
        # Accept a single .jsonl file OR a tile directory (reads all */records.jsonl inside)
        jsonl_path = Path(jsonl_path)
        if jsonl_path.is_dir():
            sources = sorted(jsonl_path.glob('*/records.jsonl'))
            if not sources:
                sources = sorted(jsonl_path.glob('*.jsonl'))
        else:
            sources = [jsonl_path]
        # records stores either str (text) or list[int] (pre-tokenized)
        total_lines = 0
        n_pretok = 0
        for src in sources:
            with open(src, 'r', encoding='utf-8', errors='replace') as f:
                for line in f:
                    if max_samples and total_lines >= max_samples:
                        break
                    total_lines += 1
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                        # ── Pre-tokenized: {"tokens": [1, 120, 614, 11, 48, 476, 12, 2]} ──
                        if 'tokens' in rec:
                            toks = rec['tokens']
                            if isinstance(toks, list) and len(toks) >= 2:
                                self.records.append(toks)
                                n_pretok += 1
                            continue
                        # ── Tool call shorthand: {"tool": "Read", "arg": "...", "text": "..."} ──
                        if 'tool' in rec:
                            tool  = rec['tool']
                            arg   = rec.get('arg', rec.get('text', ''))
                            ctx   = rec.get('text', '')
                            toks  = [1]  # BOS
                            if ctx:
                                toks += self.tokenizer.encode(ctx, max_len=self.max_len // 2,
                                                              add_special=False)[:-0 or None]
                                # strip PAD tail
                                while toks and toks[-1] == 0:
                                    toks.pop()
                            toks += self.tokenizer.encode_tool_call(tool, arg)
                            toks.append(2)  # EOS
                            self.records.append(toks)
                            n_pretok += 1
                            continue
                        # ── Text record ──────────────────────────────────────────────────────
                        text = rec.get('text', '')
                        if not text:
                            inp  = rec.get('input', '') or rec.get('prompt', '') or rec.get('instruction', '')
                            out  = rec.get('output', '') or rec.get('response', '')
                            text = (inp + ' ' + out).strip()
                        if text:
                            self.records.append(text)
                    except Exception:
                        pass
            if max_samples and total_lines >= max_samples:
                break
        label = jsonl_path.name if jsonl_path.is_file() else f"{jsonl_path.name}/ ({len(sources)} tiles)"
        print(f"[dataset] loaded {len(self.records):,} samples from {label}"
              + (f"  ({n_pretok:,} pre-tokenized)" if n_pretok else ""))

    def __len__(self):
        return len(self.records)

    def __getitem__(self, idx):
        rec = self.records[idx]
        if isinstance(rec, list):
            # Pre-tokenized: pad/truncate to max_len+1
            ids = rec[:self.max_len + 1]
            ids += [0] * (self.max_len + 1 - len(ids))
        else:
            ids = self.tokenizer.encode(rec, max_len=self.max_len + 1)
        x = torch.tensor(ids[:-1], dtype=torch.long)
        y = torch.tensor(ids[1:],  dtype=torch.long)
        return x, y


# ─── Training helpers ────────────────────────────────────────────────────────

def make_maya_coords(batch_size: int, seq_len: int, step: int) -> torch.Tensor:
    """Generate Maya Long Count coords for this batch (15 features per token)."""
    coord = LevelCoord()
    coord.advance(step)
    base = coord.to_tensor()  # [15]
    return base.unsqueeze(0).unsqueeze(0).expand(batch_size, seq_len, -1)


def make_phases(batch_size: int, seq_len: int, pi_time: float) -> torch.Tensor:
    """Generate pi-phases for each token."""
    pos = torch.arange(seq_len, dtype=torch.float32)
    phase = (pos * math.pi / seq_len + pi_time) % (2 * math.pi)
    return phase.unsqueeze(0).expand(batch_size, -1)


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--steps',       type=int,   default=2000)
    parser.add_argument('--batch',       type=int,   default=4)
    parser.add_argument('--block',       type=int,   default=256)
    parser.add_argument('--lr',          type=float, default=3e-4)
    parser.add_argument('--num-shards',  type=int,   default=6)
    parser.add_argument('--resume',      type=str,   default=None)
    parser.add_argument('--save-every',  type=int,   default=200)
    parser.add_argument('--shard-every', type=int,   default=500)
    parser.add_argument('--max-samples', type=int,   default=None)
    parser.add_argument('--shard-dir',   type=str,   default=None,
                        help='Override shard output directory (default: pi_kuhul_shards/)')
    parser.add_argument('--tokenizer',   type=str,   default='word',
                        choices=['word', 'glyph'],
                        help='word=WordTokenizer 50257 vocab (default), glyph=GlyphTokenizer 1024 vocab')
    args = parser.parse_args()

    SHARD_DIR = Path(args.shard_dir) if args.shard_dir else DEFAULT_SHARD_DIR

    CKPT_DIR.mkdir(parents=True, exist_ok=True)
    SHARD_DIR.mkdir(parents=True, exist_ok=True)

    N_SHARDS = args.num_shards

    # ── Tokenizer ────────────────────────────────────────────────────────────
    if args.tokenizer == 'glyph':
        tokenizer  = GlyphTokenizer()
        vocab_size = tokenizer.VOCAB_SIZE   # 1024
        print(f"[tokenizer] glyph — {vocab_size} tokens (tools/agents/micronauts/language)")
    else:
        tokenizer  = WordTokenizer()
        vocab_size = tokenizer.VOCAB_SIZE   # 50257
        print(f"[tokenizer] word  — {vocab_size} tokens (hash-based)")

    # ── Model ────────────────────────────────────────────────────────────────
    model = PiKuhulTransformer(
        vocab_size  = vocab_size,
        hidden_dim  = 768,
        num_layers  = 6,
        num_slices  = max(64, N_SHARDS),   # slices >= shard count; 64 = bone cluster budget
    )
    n_params = sum(p.numel() for p in model.parameters())
    print(f"[pi-kuhul] {n_params/1e6:.1f}M params | {N_SHARDS} shards | device=cpu")

    # The router maps token positions → shards via binary interleave
    router = model.router
    print(f"[pi-kuhul] router: token_pos % {N_SHARDS} -> shard_id")
    print(f"           pattern for seq_len=16: {router.assign(16).tolist()}")

    trainer = PiKuhulTrainer(model, lr=args.lr)

    if args.resume:
        trainer.load_checkpoint(args.resume)

    # ── Data — full dataset feeds ALL shards simultaneously ───────────────────
    train_ds = SMGMDataset(TRAIN_DATA, max_len=args.block, max_samples=args.max_samples,
                           tokenizer=tokenizer)
    loader   = DataLoader(train_ds, batch_size=args.batch, shuffle=True,
                          num_workers=0, drop_last=True)
    data_iter = iter(loader)

    print(f"\n[pi-kuhul] {len(train_ds):,} samples | {args.steps} steps | "
          f"batch={args.batch} block={args.block} lr={args.lr}\n")
    print(f"[pi-kuhul] each batch is routed across all {N_SHARDS} shards simultaneously")
    print(f"           data is NOT split — every shard trains on every sample\n")

    start  = time.time()
    losses = []

    # Per-shard token counters (verify all shards see balanced data)
    shard_token_counts = [0] * N_SHARDS

    for step in range(trainer.step_count, trainer.step_count + args.steps):
        try:
            x, y = next(data_iter)
        except StopIteration:
            data_iter = iter(loader)
            x, y = next(data_iter)

        B, T = x.shape

        # Track which tokens go to which shard this batch
        assignment = router.assign(T)                    # [T] shard IDs
        for s in range(N_SHARDS):
            shard_token_counts[s] += int((assignment == s).sum()) * B

        maya  = make_maya_coords(B, T, step)
        phase = make_phases(B, T, model.pi_time.item())

        metrics = trainer.train_step(x, y, maya_coords=maya, phases=phase)
        losses.append(metrics['loss'])

        if step % 50 == 0:
            avg     = sum(losses[-50:]) / len(losses[-50:])
            elapsed = time.time() - start
            tok_s   = (50 * B * T) / max(elapsed, 1)
            # Show shard balance: ideally all shards have ~equal counts
            balance = [f"s{s}:{shard_token_counts[s]//1000}k" for s in range(N_SHARDS)]
            print(f"step {step:5d} | loss {metrics['loss']:.4f} | avg {avg:.4f} | "
                  f"pi {metrics['pi_time']:.3f} | {tok_s:.0f} tok/s")
            if step % 200 == 0:
                print(f"           shard balance: {' '.join(balance)}")
            start = time.time()

        if step % args.save_every == 0 and step > trainer.step_count:
            ckpt = CKPT_DIR / f"step_{step}.pt"
            trainer.save_checkpoint(str(ckpt))

        if step % args.shard_every == 0 and step > 0:
            shard_out = str(SHARD_DIR / f"step_{step}")
            # Save all N_SHARDS — each owns its interleaved layer + card weights
            model.save_sharded(list(range(N_SHARDS)), shard_out)

    # Final save
    trainer.save_checkpoint(str(CKPT_DIR / "final.pt"))
    model.save_sharded(list(range(N_SHARDS)), str(SHARD_DIR / "final"))

    total_tokens = sum(shard_token_counts)
    print(f"\n[pi-kuhul] done | {total_tokens:,} tokens trained")
    print(f"           shard distribution: {shard_token_counts}")
    print(f"           checkpoint -> {CKPT_DIR}/final.pt")
    print(f"           shards -> {SHARD_DIR}/final/")


if __name__ == "__main__":
    main()