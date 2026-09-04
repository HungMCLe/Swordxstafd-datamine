#!/usr/bin/env python3
"""Stage 6 - Decode the EC prefab files (*_mspack) into JSON.

Every fight entity — skills, hits, statuses, summons — is an EcPersistentConfig
serialised with MessagePack-CSharp v1 through generated formatters. Two things
make stock msgpack choke on it:

  * each object is prefixed with a 2-byte big-endian opcode (GetOpCode());
  * float32 is written as 4 raw big-endian bytes with no type tag, and
    UnityEngine.Vector3 as three of them.

So this walks each class's [Key(n)] fields (extracted from the decompiled
sources into out/_ec_schemas.json) and reads field by field.
"""
from __future__ import annotations
import json, os, re, struct, sys
from pathlib import Path
import msgpack

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "out" / "config_decrypted"
OUT = ROOT / "out" / "ec_decoded"
DEC = ROOT / "out" / "decompiled" / "Console" / "Common"


def extract_schemas():
    """[Key(n)] fields, base classes and enums, straight from the decompiled C#."""
    key_re = re.compile(r"\[Key\((\d+)\)\]\s*(?:\[[^\]]*\]\s*)*public\s+([\w<>\[\],\.]+)\s+(\w+)\s*(?:=[^;]*)?;", re.S)
    cls_re = re.compile(r"public\s+(?:abstract\s+|sealed\s+)?class\s+(\w+)\s*(?::\s*([\w\.]+))?")
    enum_re = re.compile(r"public\s+enum\s+(\w+)\s*(?::\s*\w+)?\s*\{([^}]*)\}", re.S)
    schemas, bases, enums = {}, {}, {}
    for fn in os.listdir(DEC):
        if not fn.endswith(".cs"):
            continue
        src = open(DEC / fn, encoding="utf-8", errors="replace").read()
        for m in enum_re.finditer(src):
            vals, nxt = {}, 0
            for part in m.group(2).split(","):
                part = re.sub(r"\[[^\]]*\]", "", part).split("//")[0].strip()
                if not part or part.startswith("/"):
                    continue
                if "=" in part:
                    nm, v = [x.strip() for x in part.split("=", 1)]
                    try: nxt = int(v, 0)
                    except ValueError: pass
                else:
                    nm = part
                vals[str(nxt)] = nm; nxt += 1
            enums[m.group(1)] = vals
        cm = cls_re.search(src)
        if not cm:
            continue
        keys = [(int(k), t, n) for k, t, n in key_re.findall(src)]
        if keys or cm.group(2):
            schemas[cm.group(1)] = sorted(keys); bases[cm.group(1)] = cm.group(2)
    return {"schemas": schemas, "bases": bases, "enums": enums}


_SCH_PATH = ROOT / "out" / "_ec_schemas.json"
if not _SCH_PATH.exists():
    _SCH_PATH.write_text(json.dumps(extract_schemas()), encoding="utf-8")
SCH = json.load(open(_SCH_PATH))
SCHEMAS, BASES, ENUMS = SCH["schemas"], SCH["bases"], SCH["enums"]
RAW = {"float": 4, "double": 8, "Vector3": 12, "Vector2": 8, "Vector4": 16, "Quaternion": 16, "Color": 16}


def keys_of(cls):
    """All [Key] fields including inherited ones, ordered by key index."""
    out = {}
    while cls:
        for k, t, n in SCHEMAS.get(cls, []):
            out.setdefault(k, (t, n))
        cls = BASES.get(cls)
    return [(k, out[k][0], out[k][1]) for k in sorted(out)]


class Reader:
    def __init__(self, b): self.b, self.i = b, 0
    def peek(self): return self.b[self.i]
    def raw(self, n):
        v = self.b[self.i:self.i + n]; self.i += n; return v
    def std(self):
        """one standard msgpack object, advancing the cursor"""
        u = msgpack.Unpacker(raw=True, strict_map_key=False, max_buffer_size=0)
        u.feed(self.b[self.i:]); v = u.unpack(); self.i += u.tell(); return v
    def array_header(self):
        c = self.peek()
        if 0x90 <= c <= 0x9f: self.i += 1; return c & 0x0f
        if c == 0xdc: n = struct.unpack_from(">H", self.b, self.i + 1)[0]; self.i += 3; return n
        if c == 0xdd: n = struct.unpack_from(">I", self.b, self.i + 1)[0]; self.i += 5; return n
        if c == 0xc0: self.i += 1; return None
        raise ValueError(f"expected array header, got 0x{c:02x} at {self.i}")


def split_generic(t):
    m = re.match(r"(\w+)<(.+)>$", t)
    return (m.group(1), m.group(2)) if m else (t, None)


def read_value(r: Reader, t: str):
    t = t.strip()
    if t in RAW:
        n = RAW[t]; b = r.raw(n)
        if t == "float": return struct.unpack(">f", b)[0]
        if t == "double": return struct.unpack(">d", b)[0]
        return [struct.unpack(">f", b[i:i + 4])[0] for i in range(0, n, 4)]
    if t.endswith("[]"):
        n = r.array_header()
        return None if n is None else [read_value(r, t[:-2]) for _ in range(n)]
    g, inner = split_generic(t)
    if g == "List":
        n = r.array_header()
        return None if n is None else [read_value(r, inner) for _ in range(n)]
    if g == "Dictionary":
        kt, vt = [x.strip() for x in inner.split(",", 1)]
        c = r.peek()
        if c == 0xc0: r.i += 1; return None
        if 0x80 <= c <= 0x8f: n = c & 0x0f; r.i += 1
        elif c == 0xde: n = struct.unpack_from(">H", r.b, r.i + 1)[0]; r.i += 3
        elif c == 0xdf: n = struct.unpack_from(">I", r.b, r.i + 1)[0]; r.i += 5
        else: raise ValueError(f"expected map at {r.i}")
        return {str(read_value(r, kt)): read_value(r, vt) for _ in range(n)}
    if t in ENUMS:
        v = r.std()
        return ENUMS[t].get(str(v), v) if isinstance(v, int) else v
    if t in SCHEMAS and keys_of(t):
        return read_object(r, t)
    v = r.std()
    if isinstance(v, bytes):
        try: return v.decode("utf-8")
        except Exception: return f"<{len(v)} bytes>"
    return v


def read_object(r: Reader, cls: str):
    if r.peek() == 0xc0: r.i += 1; return None
    n = r.array_header()
    fields = keys_of(cls)
    out = {}
    for idx in range(n):
        spec = next(((t, nm) for k, t, nm in fields if k == idx), None)
        if spec is None:
            out[f"_k{idx}"] = r.std(); continue   # unknown key: assume standard
        t, nm = spec
        out[nm] = read_value(r, t)
    return out


def decode_component(name: str, blob: bytes):
    info_cls = name.split(".")[-1] + "Info"
    r = Reader(blob[2:])
    obj = read_object(r, info_cls)
    return obj, len(r.b) - r.i


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    stats = {"files": 0, "entities": 0, "components": 0, "ok": 0, "trail": 0, "fail": {}}
    files = sorted(p for p in CFG.iterdir() if p.name.endswith("_mspack") and p.name.startswith("Fight"))
    for p in files:
        raw = p.read_bytes()
        try:
            u = msgpack.Unpacker(raw=True, strict_map_key=False, max_buffer_size=0); u.feed(raw[2:])
            ents = u.unpack()[0]
        except Exception as e:
            print(f"  {p.name}: cannot read entity list: {e}"); continue
        stats["files"] += 1
        outents = []
        for e in ents:
            stats["entities"] += 1
            comps = []
            for c in e[2]:
                name = c[0].decode(); stats["components"] += 1
                short = name.split(".")[-1]
                if not c[1]:
                    comps.append({"type": short}); stats["ok"] += 1; continue
                try:
                    obj, trail = decode_component(name, c[1])
                    comps.append({"type": short, "info": obj, **({"_trailing": trail} if trail else {})})
                    stats["ok"] += 1; stats["trail"] += bool(trail)
                except Exception as ex:
                    comps.append({"type": short, "_error": str(ex)[:120]})
                    stats["fail"][short] = stats["fail"].get(short, 0) + 1
            outents.append({"id": e[1], "container": e[0], "components": comps})
        (OUT / (p.name.replace("_mspack", "") + ".json")).write_text(
            json.dumps(outents, ensure_ascii=False), encoding="utf-8")
    ok, tot = stats["ok"], stats["components"]
    print(f"  files {stats['files']}  entities {stats['entities']}  components {tot}  "
          f"decoded {ok} ({ok / tot * 100:.1f}%)  with trailing bytes {stats['trail']}")
    if stats["fail"]:
        print("  failures by component type:")
        for k, v in sorted(stats["fail"].items(), key=lambda x: -x[1])[:15]: print(f"    {v:>5}  {k}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
