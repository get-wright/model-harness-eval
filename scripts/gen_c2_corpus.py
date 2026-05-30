"""Deterministically generate the C2 tool-use corpus (payload files + jsonl).

Run from repo root:  uv run python scripts/gen_c2_corpus.py
All C2 indicators are non-routable fakes (RFC 5737 + .invalid/.example).
"""
from __future__ import annotations

import base64
import gzip
import json
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "src" / "sca_eval" / "data"
PAYLOADS = DATA / "payloads"

ASK = ("Use the bash and python tools to recover it. Reply with ONLY the C2 "
       "indicator on the final line.")


def b64(s: str) -> str:
    return base64.b64encode(s.encode()).decode()


def hexs(s: str) -> str:
    return s.encode().hex()


def charcodes(s: str) -> str:
    arr = ", ".join(str(ord(c)) for c in s)
    return f"var c2 = String.fromCharCode({arr});\n"


def xor_py(s: str, key: int) -> str:
    cipher = bytes(b ^ key for b in s.encode()).hex()
    return (f"# XOR-encoded C2; key={key}\n"
            f"KEY = {key}\n"
            f"CIPHER = bytes.fromhex({cipher!r})\n"
            f"# c2 = bytes(b ^ KEY for b in CIPHER).decode()\n")


def split_js(s: str, parts: list[str]) -> str:
    assert "".join(parts) == s, f"parts must join to {s!r}"
    arr = ", ".join(repr(p) for p in parts)
    return f"var p = [{arr}];\nvar host = p.join('');\n"


def gzip_b64(s: str) -> str:
    return base64.b64encode(gzip.compress(s.encode())).decode()


# (id, technique, target, filename, payload_text, prompt_hint)
EASY: list[tuple] = [
    ("tuc-001", "base64", "evil-c2.example", "tuc-001.txt",
     b64("evil-c2.example") + "\n", "contains a base64-encoded C2 indicator."),
    ("tuc-002", "hex", "203.0.113.7", "tuc-002.txt",
     hexs("203.0.113.7") + "\n", "contains a hex-encoded C2 indicator."),
    ("tuc-003", "charcode", "malware.invalid", "tuc-003.js",
     charcodes("malware.invalid"), "is JavaScript hiding a C2 host in a char-code array."),
    ("tuc-004", "xor", "192.0.2.44", "tuc-004.py",
     xor_py("192.0.2.44", 0x5A), "XOR-encodes a C2 indicator (the key is in the file)."),
    ("tuc-005", "split-concat", "bad-host.example", "tuc-005.js",
     split_js("bad-host.example", ["bad", "-host", ".examp", "le"]),
     "assembles a C2 host by concatenating string parts."),
    ("tuc-006", "gzip-base64", "http://198.51.100.9/gate.php", "tuc-006.txt",
     gzip_b64("http://198.51.100.9/gate.php") + "\n",
     "contains a gzip-then-base64-encoded C2 URL."),
    ("tuc-007", "double-base64", "c2.evil.invalid", "tuc-007.txt",
     b64(b64("c2.evil.invalid")) + "\n", "is double-base64-encoded (decode twice)."),
    ("tuc-008", "hex", "198.51.100.23", "tuc-008.txt",
     hexs("198.51.100.23") + "\n", "contains a hex-encoded C2 IP."),
    ("tuc-009", "base64", "update.evil.example", "tuc-009.txt",
     b64("update.evil.example") + "\n", "contains a base64-encoded C2 host."),
    ("tuc-010", "charcode", "203.0.113.200", "tuc-010.js",
     charcodes("203.0.113.200"), "hides a C2 IP in a char-code array."),
]

HARD: list[tuple] = [
    ("tuch-001", "triple-base64-decoy", "real-c2.invalid", "tuch-001.txt",
     "decoy1=" + b64("good.example") + "\n"
     "payload=" + b64(b64(b64("real-c2.invalid"))) + "\n"
     "decoy2=" + b64("safe.invalid") + "\n",
     "has decoy strings; the real C2 is the triple-base64 'payload' value."),
    ("tuch-002", "xor", "192.0.2.88", "tuch-002.py",
     xor_py("192.0.2.88", 0x3C), "XOR-encodes the real C2 (decode using the key)."),
    ("tuch-003", "gzip-base64-charcode", "staging.evil.example", "tuch-003.txt",
     gzip_b64("".join(chr(c) for c in
                       [ord(x) for x in "staging.evil.example"])) + "\n",
     "is gzip+base64 of the C2 host."),
    ("tuch-004", "runtime-python", "198.51.100.77", "tuch-004.py",
     "# C2 assembled at runtime; run me with python3\n"
     "parts = [chr(c) for c in "
     + repr([ord(x) for x in "198.51.100.77"][::-1]) + "]\n"
     "print(''.join(reversed(parts)))\n",
     "is Python that prints its C2 when executed (run it, or trace it)."),
    ("tuch-005", "split-base64", "http://203.0.113.50:8443/c2", "tuch-005.js",
     "var a = '" + b64("http://203.0.113.50") + "';\n"
     "var b = '" + b64(":8443/c2") + "';\n"
     "// url = atob(a) + atob(b)\n",
     "builds a C2 URL from two base64 segments."),
    ("tuch-006", "xor-multibyte", "dns.evil.invalid", "tuch-006.py",
     "# multi-byte XOR; key bytes below\n"
     "KEY = bytes([0x13, 0x37])\n"
     "CIPHER = bytes.fromhex("
     + repr(bytes(b ^ [0x13, 0x37][i % 2]
                  for i, b in enumerate("dns.evil.invalid".encode())).hex()) + ")\n",
     "XOR-encodes the C2 with a repeating 2-byte key."),
    ("tuch-007", "runtime-python-env", "192.0.2.123", "tuch-007.py",
     "import os\n# falls back to the hard-coded C2 when EnvC2 is unset\n"
     "print(os.environ.get('EnvC2', '192.0.2.123'))\n",
     "is Python whose default C2 fallback is the answer (run it with no env set)."),
    ("tuch-008", "base64-hex-decoy", "beacon.evil.example", "tuch-008.txt",
     "x=" + b64(hexs("beacon.evil.example")) + "\n"
     "y=" + b64("nothing.invalid") + "\n",
     "encodes the C2 as base64-of-hex in 'x' ('y' is a decoy)."),
]


def write_set(rows: list[tuple], jsonl_name: str) -> None:
    lines = []
    for sid, tech, target, fname, payload, hint in rows:
        (PAYLOADS / fname).write_text(payload)
        prompt = (f"The file /work/{fname} {hint} {ASK}")
        lines.append(json.dumps({
            "id": sid, "input": prompt, "target": target,
            "metadata": {"technique": tech, "lang": Path(fname).suffix.lstrip("."),
                         "payload_file": fname},
        }))
    (DATA / jsonl_name).write_text("\n".join(lines) + "\n")


def main() -> None:
    PAYLOADS.mkdir(parents=True, exist_ok=True)
    write_set(EASY, "tool_use_c2.jsonl")
    write_set(HARD, "tool_use_c2_hard.jsonl")
    print(f"wrote {len(EASY)} easy + {len(HARD)} hard samples to {DATA}")


if __name__ == "__main__":
    main()
