#!/usr/bin/env python3
"""
myzip.py - a personal compressor with its own file format (.myz).

Compression is written from scratch:
  1. LZ77     - replaces repeated chunks with (length, distance) back-references
  2. Huffman  - gives common symbols short bit codes, rare symbols long ones

Optional password protection uses proven cryptography (never homemade):
  key   = scrypt(password, random salt)
  data  = AES-256-GCM encrypted (also detects tampering / wrong password)

Usage:
  python myzip.py compress   photo.bmp  photo.myz
  python myzip.py compress   notes.txt  notes.myz  --password
  python myzip.py decompress notes.myz  notes_restored.txt

Folders (all files, subfolders and empty folders are included):
  python myzip.py compress   MyProject  project.myz
  python myzip.py decompress project.myz restored_folder
  python myzip.py list       project.myz

Encryption needs:  pip install cryptography
"""

import argparse
import binascii
import getpass
import hashlib
import heapq
import os
import struct
import sys

MAGIC = b"MYZ1"          # signature so the program recognises its own files
FLAG_ENCRYPTED = 1
FLAG_FOLDER = 2          # payload holds many files/folders, not one file

# ---------------------------------------------------------------- LZ77 settings
WINDOW = 32768           # how far back we look for repeats
MIN_MATCH = 3            # shorter repeats aren't worth a reference
MAX_MATCH = 258
MAX_CHAIN = 64           # candidates checked per position (speed vs. ratio)

# ---------------------------------------------------------------- symbol layout
# Literal/length alphabet:  0-255 = literal byte
#                           256-511 = match length (3..258)
#                           512 = end of data
# Distance: (distance-1) split into a high part (0-127, Huffman coded)
#           and a low byte (8 raw bits).
END_SYMBOL = 512
NUM_LITLEN = 513
NUM_DIST = 128


# =============================================================== bit-level I/O
class BitWriter:
    def __init__(self):
        self.buf = bytearray()
        self.acc = 0
        self.nbits = 0

    def write(self, value, nbits):
        self.acc = (self.acc << nbits) | value
        self.nbits += nbits
        while self.nbits >= 8:
            self.nbits -= 8
            self.buf.append((self.acc >> self.nbits) & 0xFF)
        self.acc &= (1 << self.nbits) - 1

    def finish(self):
        if self.nbits:
            self.buf.append((self.acc << (8 - self.nbits)) & 0xFF)
        self.acc = self.nbits = 0
        return bytes(self.buf)


class BitReader:
    def __init__(self, data, pos=0):
        self.data = data
        self.pos = pos
        self.acc = 0
        self.nbits = 0

    def read_bit(self):
        if self.nbits == 0:
            if self.pos >= len(self.data):
                raise ValueError("Unexpected end of data (file corrupt?)")
            self.acc = self.data[self.pos]
            self.pos += 1
            self.nbits = 8
        self.nbits -= 1
        return (self.acc >> self.nbits) & 1

    def read(self, nbits):
        value = 0
        for _ in range(nbits):
            value = (value << 1) | self.read_bit()
        return value


# ===================================================================== LZ77
def lz77_tokens(data):
    """Turn bytes into a list of literals (int) and matches (length, distance)."""
    tokens = []
    table = {}                        # 3-byte sequence -> positions where seen
    i, n = 0, len(data)

    while i < n:
        best_len = best_dist = 0
        if i + MIN_MATCH <= n:
            candidates = table.get(data[i:i + 3])
            if candidates:
                max_len = min(MAX_MATCH, n - i)
                for j in reversed(candidates[-MAX_CHAIN:]):   # newest first
                    dist = i - j
                    if dist > WINDOW:
                        break
                    length = 3        # first 3 bytes are known to match
                    while length < max_len and data[j + length] == data[i + length]:
                        length += 1
                    if length > best_len:
                        best_len, best_dist = length, dist
                        if length == max_len:
                            break

        if best_len >= MIN_MATCH:
            tokens.append((best_len, best_dist))
            step = best_len
        else:
            tokens.append(data[i])
            step = 1

        # remember every position we just passed so later data can refer to it
        for k in range(i, min(i + step, n - 2)):
            lst = table.setdefault(data[k:k + 3], [])
            lst.append(k)
            if len(lst) > 256:
                del lst[:128]
        i += step

    return tokens


# ================================================================== Huffman
def huffman_code_lengths(freqs):
    """Build a Huffman tree from frequencies; return the code length per symbol."""
    lengths = [0] * len(freqs)
    heap = [(f, s, s) for s, f in enumerate(freqs) if f > 0]
    if not heap:
        return lengths
    if len(heap) == 1:                # one symbol still needs a 1-bit code
        lengths[heap[0][1]] = 1
        return lengths

    heapq.heapify(heap)
    tiebreak = len(freqs)
    while len(heap) > 1:              # repeatedly join the two rarest nodes
        f1, _, a = heapq.heappop(heap)
        f2, _, b = heapq.heappop(heap)
        heapq.heappush(heap, (f1 + f2, tiebreak, (a, b)))
        tiebreak += 1

    stack = [(heap[0][2], 0)]         # walk tree: depth = code length
    while stack:
        node, depth = stack.pop()
        if isinstance(node, tuple):
            stack.append((node[0], depth + 1))
            stack.append((node[1], depth + 1))
        else:
            lengths[node] = depth
    return lengths


def canonical_codes(lengths):
    """Assign actual bit codes from lengths alone (so only lengths are stored)."""
    max_len = max(lengths, default=0)
    count = [0] * (max_len + 1)
    for l in lengths:
        if l:
            count[l] += 1
    next_code = [0] * (max_len + 2)
    code = 0
    for bits in range(1, max_len + 1):
        code = (code + count[bits - 1]) << 1
        next_code[bits] = code
    codes = {}
    for sym, l in enumerate(lengths):
        if l:
            codes[sym] = (next_code[l], l)
            next_code[l] += 1
    return codes


def decode_table(lengths):
    return {(l, c): s for s, (c, l) in canonical_codes(lengths).items()}


def read_symbol(reader, table):
    code = length = 0
    while True:
        code = (code << 1) | reader.read_bit()
        length += 1
        sym = table.get((length, code))
        if sym is not None:
            return sym
        if length > 64:
            raise ValueError("Invalid code in data (file corrupt?)")


# ============================================================ compress / expand
def compress_bytes(data):
    tokens = lz77_tokens(data)

    litlen_freq = [0] * NUM_LITLEN
    dist_freq = [0] * NUM_DIST
    for t in tokens:
        if isinstance(t, int):
            litlen_freq[t] += 1
        else:
            length, dist = t
            litlen_freq[256 + length - 3] += 1
            dist_freq[(dist - 1) >> 8] += 1
    litlen_freq[END_SYMBOL] += 1

    litlen_len = huffman_code_lengths(litlen_freq)
    dist_len = huffman_code_lengths(dist_freq)
    litlen_codes = canonical_codes(litlen_len)
    dist_codes = canonical_codes(dist_len)

    w = BitWriter()
    for t in tokens:
        if isinstance(t, int):
            w.write(*litlen_codes[t])
        else:
            length, dist = t
            w.write(*litlen_codes[256 + length - 3])
            d = dist - 1
            w.write(*dist_codes[d >> 8])
            w.write(d & 0xFF, 8)
    w.write(*litlen_codes[END_SYMBOL])

    header = struct.pack(">QI", len(data), binascii.crc32(data))
    return header + bytes(litlen_len) + bytes(dist_len) + w.finish()


def decompress_bytes(payload):
    size, crc = struct.unpack(">QI", payload[:12])
    pos = 12
    litlen_len = list(payload[pos:pos + NUM_LITLEN]); pos += NUM_LITLEN
    dist_len = list(payload[pos:pos + NUM_DIST]); pos += NUM_DIST

    litlen_table = decode_table(litlen_len)
    dist_table = decode_table(dist_len)
    r = BitReader(payload, pos)
    out = bytearray()

    while True:
        sym = read_symbol(r, litlen_table)
        if sym < 256:
            out.append(sym)
        elif sym == END_SYMBOL:
            break
        else:
            length = sym - 256 + 3
            dist = ((read_symbol(r, dist_table) << 8) | r.read(8)) + 1
            if dist > len(out):
                raise ValueError("Bad back-reference (file corrupt?)")
            start = len(out) - dist
            for k in range(length):       # byte-by-byte: copies may overlap
                out.append(out[start + k])

    if len(out) != size or binascii.crc32(out) != crc:
        raise ValueError("Checksum mismatch: data is corrupt")
    return bytes(out)


# =============================================================== encryption
def _derive_key(password, salt):
    return hashlib.scrypt(password.encode(), salt=salt, n=2**15, r=8, p=1,
                          maxmem=64 * 1024 * 1024, dklen=32)


def _aesgcm():
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        return AESGCM
    except ImportError:
        sys.exit("Password mode needs:  pip install cryptography")


# ========================================================= folder bundling
# Like tar: many files are glued into ONE byte stream, which is then compressed
# as a whole ("solid"), so repeats across different files are found too.
# Each entry:  type(1) | mtime(8) | path_len(2) | path | [data_len(8) | data]
ENTRY_DIR, ENTRY_FILE = 0, 1


def bundle_folder(root):
    out = bytearray()
    count = 0
    root = os.path.abspath(root)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        rel_dir = os.path.relpath(dirpath, root)
        entries = []
        if rel_dir != ".":
            entries.append((ENTRY_DIR, dirpath, rel_dir))
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            if os.path.islink(full) or not os.path.isfile(full):
                continue                      # skip symlinks, devices, etc.
            entries.append((ENTRY_FILE, full, os.path.relpath(full, root)))

        for kind, full, rel in entries:
            path = rel.replace(os.sep, "/").encode("utf-8")
            out += struct.pack(">Bd", kind, os.path.getmtime(full))
            out += struct.pack(">H", len(path)) + path
            if kind == ENTRY_FILE:
                with open(full, "rb") as f:
                    data = f.read()
                out += struct.pack(">Q", len(data)) + data
                count += 1
                print(f"  + {rel}")
    return bytes(out), count


def iter_bundle(blob):
    """Yield (kind, mtime, relative_path, data) from a bundled byte stream."""
    pos = 0
    while pos < len(blob):
        kind, mtime = struct.unpack_from(">Bd", blob, pos); pos += 9
        (plen,) = struct.unpack_from(">H", blob, pos); pos += 2
        path = blob[pos:pos + plen].decode("utf-8"); pos += plen
        data = None
        if kind == ENTRY_FILE:
            (dlen,) = struct.unpack_from(">Q", blob, pos); pos += 8
            data = blob[pos:pos + dlen]; pos += dlen
        yield kind, mtime, path, data


def unbundle_folder(blob, dest):
    dest = os.path.abspath(dest)
    os.makedirs(dest, exist_ok=True)
    dir_times = []
    count = 0
    for kind, mtime, rel, data in iter_bundle(blob):
        target = os.path.abspath(os.path.join(dest, *rel.split("/")))
        # safety: never write outside the destination folder
        if os.path.commonpath([dest, target]) != dest:
            raise ValueError(f"Unsafe path in archive: {rel}")
        if kind == ENTRY_DIR:
            os.makedirs(target, exist_ok=True)
            dir_times.append((target, mtime))
        else:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "wb") as f:
                f.write(data)
            os.utime(target, (mtime, mtime))
            count += 1
            print(f"  - {rel}")
    for target, mtime in reversed(dir_times):   # set folder times last
        os.utime(target, (mtime, mtime))
    return count


# ============================================================= file format
def pack_file(data, password=None, extra_flags=0):
    payload = compress_bytes(data)
    if password is None:
        return MAGIC + bytes([extra_flags]) + payload
    header = MAGIC + bytes([FLAG_ENCRYPTED | extra_flags])
    salt, nonce = os.urandom(16), os.urandom(12)
    cipher = _aesgcm()(_derive_key(password, salt))
    return header + salt + nonce + cipher.encrypt(nonce, payload, header)


def unpack_file(blob, ask_password):
    """Return (flags, original_bytes)."""
    if blob[:4] != MAGIC:
        raise ValueError("Not a .myz file")
    flags = blob[4]
    if flags & FLAG_ENCRYPTED:
        header = blob[:5]
        salt, nonce, ciphertext = blob[5:21], blob[21:33], blob[33:]
        cipher = _aesgcm()(_derive_key(ask_password(), salt))
        try:
            payload = cipher.decrypt(nonce, ciphertext, header)
        except Exception:
            raise ValueError("Wrong password, or the file was modified")
    else:
        payload = blob[5:]
    return flags, decompress_bytes(payload)


# ===================================================================== CLI
def main():
    p = argparse.ArgumentParser(description="Personal compressor (.myz format)")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("compress", help="compress a file or a whole folder")
    c.add_argument("input"); c.add_argument("output")
    c.add_argument("--password", action="store_true", help="encrypt with a password")
    d = sub.add_parser("decompress", help="restore a file or folder")
    d.add_argument("input"); d.add_argument("output")
    l = sub.add_parser("list", help="show what is inside a .myz")
    l.add_argument("input")
    args = p.parse_args()

    ask = lambda: getpass.getpass("Password: ")
    try:
        if args.cmd == "compress":
            pw = None
            if args.password:
                pw = getpass.getpass("Password: ")
                if pw != getpass.getpass("Repeat password: "):
                    sys.exit("Passwords do not match")
            if os.path.isdir(args.input):
                print(f"Bundling folder '{args.input}':")
                data, count = bundle_folder(args.input)
                result = pack_file(data, pw, FLAG_FOLDER)
                print(f"{count} files")
            else:
                with open(args.input, "rb") as f:
                    data = f.read()
                result = pack_file(data, pw)
            with open(args.output, "wb") as f:
                f.write(result)
            ratio = 100 * len(result) / max(len(data), 1)
            print(f"{len(data):,} bytes -> {len(result):,} bytes ({ratio:.1f}%)")

        else:
            with open(args.input, "rb") as f:
                blob = f.read()
            flags, data = unpack_file(blob, ask)

            if args.cmd == "list":
                if flags & FLAG_FOLDER:
                    for kind, _, rel, content in iter_bundle(data):
                        print(f"{rel}/" if kind == ENTRY_DIR
                              else f"{rel}  ({len(content):,} bytes)")
                else:
                    print(f"Single file, {len(data):,} bytes")
            elif flags & FLAG_FOLDER:
                print(f"Restoring into folder '{args.output}':")
                count = unbundle_folder(data, args.output)
                print(f"Restored {count} files")
            else:
                with open(args.output, "wb") as f:
                    f.write(data)
                print(f"Restored {len(data):,} bytes")
    except ValueError as e:
        sys.exit(f"Error: {e}")


if __name__ == "__main__":
    main()
