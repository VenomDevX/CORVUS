"""Minimal CLIP BPE tokenizer (vocab.json + merges.txt), no transformers.

Implements the byte-level BPE CLIP uses: lowercase, GPT-2 byte→unicode
mapping, end-of-word `</w>` marker, merge ranks from merges.txt. Covers the
ASCII prompt path exactly; non-Latin words fall through as byte sequences
(still valid tokens, slightly less optimal splits).
"""

from __future__ import annotations

import functools
import json
import re
from pathlib import Path

_PAT = re.compile(
    r"""<\|startoftext\|>|<\|endoftext\|>|'s|'t|'re|'ve|'m|'ll|'d|[a-z]+|[0-9]|[^\sa-z0-9]+""",
    re.IGNORECASE,
)

BOS = 49406
EOS = 49407
CONTEXT = 77


@functools.lru_cache(maxsize=1)
def _bytes_to_unicode() -> dict[int, str]:
    bs = list(range(33, 127)) + list(range(161, 173)) + list(range(174, 256))
    cs = bs[:]
    n = 0
    for b in range(256):
        if b not in bs:
            bs.append(b)
            cs.append(256 + n)
            n += 1
    return dict(zip(bs, (chr(c) for c in cs)))


class ClipTokenizer:
    def __init__(self, tokenizer_dir: Path):
        self.encoder: dict[str, int] = json.loads(
            (tokenizer_dir / "vocab.json").read_text(encoding="utf-8")
        )
        merges = (tokenizer_dir / "merges.txt").read_text(encoding="utf-8").splitlines()
        merges = [m for m in merges if m and not m.startswith("#")]
        self.ranks = {tuple(m.split()): i for i, m in enumerate(merges)}
        self.byte_encoder = _bytes_to_unicode()
        self.cache: dict[str, list[str]] = {}

    def _bpe(self, token: str) -> list[str]:
        if token in self.cache:
            return self.cache[token]
        word = [*token[:-1], token[-1] + "</w>"]
        while len(word) > 1:
            pairs = {(word[i], word[i + 1]) for i in range(len(word) - 1)}
            best = min(pairs, key=lambda p: self.ranks.get(p, 1 << 30))
            if best not in self.ranks:
                break
            first, second = best
            merged: list[str] = []
            i = 0
            while i < len(word):
                if i < len(word) - 1 and word[i] == first and word[i + 1] == second:
                    merged.append(first + second)
                    i += 2
                else:
                    merged.append(word[i])
                    i += 1
            word = merged
        self.cache[token] = word
        return word

    def encode(self, text: str) -> list[int]:
        """Token ids padded/truncated to the CLIP context length of 77."""
        ids: list[int] = []
        for tok in _PAT.findall(text.lower().strip()):
            mapped = "".join(self.byte_encoder[b] for b in tok.encode("utf-8"))
            for piece in self._bpe(mapped):
                piece_id = self.encoder.get(piece)
                if piece_id is not None:
                    ids.append(piece_id)
        ids = ids[: CONTEXT - 2]
        full = [BOS, *ids, EOS]
        full += [EOS] * (CONTEXT - len(full))
        return full
