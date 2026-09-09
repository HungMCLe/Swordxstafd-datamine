"""Schema-driven decoder for Sword x Staff's live game protocol (client <-> planes server).

The client talks KCP over UDP (TCP fallback) on ports 8033/9033 and sends MessagePack. Nothing on the
wire is encrypted. This module turns raw frames into named objects using the decompiled client
(`out/decompiled/Console`) as the schema source. Everything below was verified against a real capture:
every frame in both directions decodes with zero trailing bytes.

Wire format
  frame  = magic 0xF0F0 (u16 LE) + bodyLen (u16 LE) + header rest (12 bytes client->server, 8 bytes
           server->client; the u16 at header offset 8 (c2s) / 0 (s2c) is the RPC seq) + body[bodyLen]
  body   = opcode (u16 LE, `Common.SerializeType` const of the message class) + MessagePack array of the
           class's [Key(n)] fields, in the order the generated `<Class>Formatter.Serialize` writes them
  fields whose declared type is one of the ~356 `BaseSerializable<T>` types listed in
           `AutoMPG/RootSerializer.GetFormatters` (abstract bases, `MySerializable`, interfaces) are written
           as opcode (raw u16 LE, 0 = null) followed by the concrete class's array; every other class is a
           plain array. Enums are ints. DateTime is the msgpack timestamp ext (-1).
  float32 is written as 4 raw big-endian bytes (no 0xCA marker) by this build of the library.

Usage
  python tools/liveproto/gproto.py schema                 # build tools/liveproto/schema.json (from out/decompiled)
  python tools/liveproto/gproto.py decode streams.json out.json   # decode a parse.py output
"""
import sys, os, re, json, struct, glob

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DECOMP = os.path.join(ROOT, 'out', 'decompiled')
SCHEMA = os.path.join(HERE, 'schema.json')

# ----------------------------------------------------------------------------- schema

def split_generic(s):
    """'Dictionary<long, List<int>>' -> ('Dictionary', ['long', 'List<int>'])"""
    s = s.strip()
    if s.endswith('[]'):
        return 'Array', [s[:-2]]
    if s.endswith('?'):
        return 'Nullable', [s[:-1]]
    if s.startswith('(') and s.endswith(')'):
        return 'ValueTuple', split_args(s[1:-1])
    i = s.find('<')
    if i < 0:
        return s, []
    return s[:i], split_args(s[i + 1:-1])

def split_args(s):
    out, depth, cur = [], 0, ''
    for ch in s:
        if ch in '<(':
            depth += 1
        elif ch in '>)':
            depth -= 1
        if ch == ',' and depth == 0:
            out.append(cur.strip()); cur = ''
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return [re.sub(r'\s+\w+$', '', a) if ' ' in a and not a.endswith('>') else a for a in out]

def fieldname(expr):
    m = re.search(r'value\)?\.(\w+)', expr)
    return m.group(1) if m else expr[-30:]

def enum_values(text):
    """Parse every `enum Name { A, B = 3, ... }` in a C# source into {Name: {int: member}}."""
    out = {}
    for m in re.finditer(r'\benum (\w+)\b[^{]*\{(.*?)\n\}', text, re.S):
        vals, v = {}, 0
        for item in re.split(r',\s*\n', m.group(2)):
            item = item.strip().split('//')[0].strip().rstrip(',')
            if not item or item.startswith('['):
                continue
            if '=' in item:
                k, val = [x.strip() for x in item.split('=', 1)]
                try:
                    v = int(val, 0)
                except ValueError:
                    pass
            else:
                k = item
            vals[v] = k; v += 1
        out[m.group(1)] = vals
    return out

def build_schema():
    con = os.path.join(DECOMP, 'Console')
    files = []
    for d in ('MessagePack.Formatters.Common', 'MessagePack.Formatters.EntityComponent', 'MessagePack.Formatters'):
        files += glob.glob(os.path.join(con, d, '*.cs'))
    classes = {}
    sig = re.compile(r'public int Serialize\(ref byte\[\] bytes, int offset, (.+?) value, IFormatterResolver formatterResolver\)\s*\{(.*?)\n\t\}\n', re.S)
    for f in files:
        t = open(f, encoding='utf-8', errors='replace').read()
        m = sig.search(t)
        if not m:
            continue
        typ, body = m.group(1).strip(), m.group(2)
        if re.search(r'return MessagePackBinary\.Write\w+\(ref bytes, offset, \((\w+)\)value\);', body) and 'ArrayHeader' not in body:
            continue  # enum formatter
        fields, count = [], None
        for l in (l.strip() for l in body.splitlines()):
            if not l or l.startswith('//'):
                continue
            mm = re.search(r'Write(?:FixedArrayHeaderUnsafe|ArrayHeader)\(ref bytes, offset, (\d+)\)', l)
            if mm:
                count = int(mm.group(1)); continue
            if l == 'offset += MessagePackBinary.WriteNil(ref bytes, offset);':
                fields.append(['nil', None]); continue
            mm = re.search(r'MessagePackBinary\.Write(Int32|Int64|Boolean|Single|Double|UInt64|UInt32|Byte|UInt16|Int16|SByte|String|Char)\(ref bytes, offset, (.+)\);$', l)
            if mm:
                fields.append([mm.group(1).lower(), fieldname(mm.group(2))]); continue
            mm = re.search(r'GetFormatterWithVerify<(.+)>\(formatterResolver\)\.Serialize\(ref bytes, offset, (.+), formatterResolver\);$', l)
            if mm:
                fields.append([mm.group(1), fieldname(mm.group(2))]); continue
            mm = re.search(r'\(\(IMessagePackFormatter<(.+?)>\)[^)]*\)\.Serialize\(ref bytes, offset, (.+), formatterResolver\);$', l)
            if mm:
                fields.append([mm.group(1), fieldname(mm.group(2))]); continue
        if count is None and not fields:
            continue
        classes[typ] = dict(count=count, fields=fields)
    # opcode table
    ops = {}
    st = open(os.path.join(con, 'Common', 'SerializeType.cs'), encoding='utf-8', errors='replace').read()
    for name, val in re.findall(r'public const ushort (\w+) = (\d+);', st):
        ops[int(val)] = name
    # declared types that go through RootSerializer (opcode prefix)
    rs = open(os.path.join(con, 'AutoMPG', 'RootSerializer.cs'), encoding='utf-8', errors='replace').read()
    prefixed = sorted(set(re.findall(r'new BaseSerializable<(.+?)>\(\)', rs)))
    # enums with their member names
    enums = {}
    for f in glob.glob(os.path.join(DECOMP, '**', '*.cs'), recursive=True):
        try:
            t = open(f, encoding='utf-8', errors='replace').read()
        except OSError:
            continue
        if 'enum ' in t:
            enums.update(enum_values(t))
    schema = dict(classes=classes, enums=enums, opcodes=ops, prefixed=prefixed)
    json.dump(schema, open(SCHEMA, 'w'), indent=0)
    print(f'classes {len(classes)}, enums {len(enums)}, opcodes {len(ops)}, prefixed types {len(prefixed)} -> {SCHEMA}')
    return schema

# ----------------------------------------------------------------------------- msgpack reader

class Reader:
    def __init__(self, b, pos=0):
        self.b, self.pos = b, pos

    def peek(self):
        return self.b[self.pos]

    def u16(self):
        v = struct.unpack_from('<H', self.b, self.pos)[0]; self.pos += 2; return v

    def take(self, n):
        v = self.b[self.pos:self.pos + n]; self.pos += n; return v

    def be(self, fmt):
        v = struct.unpack_from(fmt, self.b, self.pos)[0]; self.pos += struct.calcsize(fmt); return v

    def array_header(self):
        c = self.take(1)[0]
        if 0x90 <= c <= 0x9f: return c & 15
        if c == 0xdc: return self.be('>H')
        if c == 0xdd: return self.be('>I')
        if c == 0xc0: return None
        raise ValueError(f'expected array at {self.pos - 1}, got {c:02x}')

    def map_header(self):
        c = self.take(1)[0]
        if 0x80 <= c <= 0x8f: return c & 15
        if c == 0xde: return self.be('>H')
        if c == 0xdf: return self.be('>I')
        if c == 0xc0: return None
        raise ValueError(f'expected map at {self.pos - 1}, got {c:02x}')

    def value(self):
        """Generic MessagePack value (scalars, and structures without a schema)."""
        c = self.take(1)[0]
        if c <= 0x7f: return c
        if c >= 0xe0: return c - 256
        if 0x80 <= c <= 0x8f: return {self.value(): self.value() for _ in range(c & 15)}
        if 0x90 <= c <= 0x9f: return [self.value() for _ in range(c & 15)]
        if 0xa0 <= c <= 0xbf: return self.str(c & 31)
        if c == 0xc0: return None
        if c == 0xc2: return False
        if c == 0xc3: return True
        if c == 0xc4: return self.take(self.be('>B'))
        if c == 0xc5: return self.take(self.be('>H'))
        if c == 0xc6: return self.take(self.be('>I'))
        if c == 0xc7: return self.ext(self.be('>B'))
        if c == 0xc8: return self.ext(self.be('>H'))
        if c == 0xc9: return self.ext(self.be('>I'))
        if c == 0xca: return self.be('>f')
        if c == 0xcb: return self.be('>d')
        if c == 0xcc: return self.be('>B')
        if c == 0xcd: return self.be('>H')
        if c == 0xce: return self.be('>I')
        if c == 0xcf: return self.be('>Q')
        if c == 0xd0: return self.be('>b')
        if c == 0xd1: return self.be('>h')
        if c == 0xd2: return self.be('>i')
        if c == 0xd3: return self.be('>q')
        if c == 0xd4: return self.ext(1)
        if c == 0xd5: return self.ext(2)
        if c == 0xd6: return self.ext(4)
        if c == 0xd7: return self.ext(8)
        if c == 0xd8: return self.ext(16)
        if c == 0xd9: return self.str(self.be('>B'))
        if c == 0xda: return self.str(self.be('>H'))
        if c == 0xdb: return self.str(self.be('>I'))
        if c == 0xdc: return [self.value() for _ in range(self.be('>H'))]
        if c == 0xdd: return [self.value() for _ in range(self.be('>I'))]
        if c == 0xde: return {self.value(): self.value() for _ in range(self.be('>H'))}
        if c == 0xdf: return {self.value(): self.value() for _ in range(self.be('>I'))}
        raise ValueError(f'bad msgpack byte {c:02x} at {self.pos - 1}')

    def str(self, n):
        raw = self.take(n)
        try:
            return raw.decode('utf-8')
        except UnicodeDecodeError:
            return raw

    def ext(self, n):
        code = self.be('>b'); data = self.take(n)
        if code == -1:  # timestamp
            if n == 4: return dict(ts=struct.unpack('>I', data)[0])
            if n == 8:
                v = struct.unpack('>Q', data)[0]; return dict(ts=v & 0x3ffffffff, ns=v >> 34)
            if n == 12:
                ns, s = struct.unpack('>Iq', data); return dict(ts=s, ns=ns)
        return dict(ext=code, data=data.hex())

# ----------------------------------------------------------------------------- decoder

SCALARS = {'int', 'long', 'short', 'byte', 'sbyte', 'ushort', 'uint', 'ulong', 'double', 'bool', 'string',
           'char', 'decimal', 'DateTime', 'TimeSpan', 'DateTimeOffset', 'Guid', 'BigInteger',
           'int32', 'int64', 'boolean', 'uint64', 'uint32', 'int16', 'uint16'}
LISTS = {'List', 'Array', 'IList', 'IReadOnlyList', 'ICollection', 'IReadOnlyCollection', 'IEnumerable', 'HashSet',
         'ISet', 'Queue', 'Stack', 'LinkedList', 'ReadOnlyCollection', 'ObservableCollection', 'ArraySegment'}
MAPS = {'Dictionary', 'IDictionary', 'IReadOnlyDictionary', 'ReadOnlyDictionary', 'SortedDictionary',
        'ConcurrentDictionary', 'SortedList'}

class Decoder:
    def __init__(self, schema, names=True):
        self.classes = schema['classes']
        # JSON turned the int member values into string keys; put them back
        self.enums = {name: {int(k): m for k, m in vals.items()} for name, vals in schema['enums'].items()}
        self.opcodes = {int(k): v for k, v in schema['opcodes'].items()}
        self.prefixed = set(schema['prefixed'])
        self.names = names
        self.problems = []

    def message(self, body):
        r = Reader(body)
        op = r.u16()
        name = self.opcodes.get(op, f'op{op}')
        try:
            obj = self.cls(r, name) if name in self.classes else r.value()
            rest = len(body) - r.pos
        except Exception as e:
            self.problems.append(f'{name}: {e!r} at {r.pos}')
            obj, rest = dict(error=repr(e), at=r.pos), -1
        return name, obj, rest

    def cls(self, r, name):
        if r.peek() == 0xc0:
            r.pos += 1; return None
        n = r.array_header()
        sch = self.classes[name]
        out = {'$type': name}
        for i in range(n):
            if i < len(sch['fields']):
                typ, fname = sch['fields'][i]
                if typ == 'nil':
                    r.value(); continue
                out[fname] = self.typed(r, typ)
            else:
                out[f'_{i}'] = r.value()
        return out

    def typed(self, r, typ):
        head, args = split_generic(typ)
        if head in ('single', 'float'):  # float32 = 4 raw big-endian bytes in this build
            return struct.unpack('>f', r.take(4))[0]
        if head in SCALARS or typ == 'byte[]':
            return r.value()
        if head == 'Nullable':
            if r.peek() == 0xc0:
                r.pos += 1; return None
            return self.typed(r, args[0])
        if head in LISTS:
            n = r.array_header()
            return None if n is None else [self.typed(r, args[0]) for _ in range(n)]
        if head in MAPS:
            n = r.map_header()
            if n is None: return None
            out = [(self.typed(r, args[0]), self.typed(r, args[1])) for _ in range(n)]
            try:
                return dict(out)
            except TypeError:
                return out
        if head in ('KeyValuePair', 'ValueTuple', 'Tuple'):
            n = r.array_header()
            return None if n is None else [self.typed(r, args[i]) if i < len(args) else r.value() for i in range(n)]
        if head == 'object':
            return self.obj(r)
        if head in self.enums:
            v = r.value()
            return self.enums[head].get(v, v) if self.names and isinstance(v, int) else v
        if head in self.prefixed:
            op = r.u16()
            if op == 0:
                return None
            cname = self.opcodes.get(op)
            if cname in self.classes:
                return self.cls(r, cname)
            raise ValueError(f'unknown polymorphic type {typ} opcode {op}')
        if head in self.classes:
            return self.cls(r, head)
        return r.value()

    def obj(self, r):
        """Common.ObjectFormatter: a type-code byte then the value."""
        code = r.value()
        if code in (7, 17): return None
        if code == 18:
            n = r.array_header()
            return [self.obj(r) for _ in range(n)]
        if code == 16:
            return self.typed(r, 'SourceOperate')
        return r.value()

# ----------------------------------------------------------------------------- frames

def frames(stream, hdr):
    i = 0
    while i + hdr <= len(stream):
        if stream[i:i + 2] != b'\xf0\xf0':
            raise ValueError(f'desync at {i}')
        ln = struct.unpack_from('<H', stream, i + 2)[0]
        yield i, stream[i + 4:i + hdr], stream[i + hdr:i + hdr + ln]
        i += hdr + ln

def default(o):
    return o.hex() if isinstance(o, bytes) else str(o)

def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ('schema', 'decode'):
        print(__doc__); return
    if sys.argv[1] == 'schema':
        build_schema(); return
    schema = json.load(open(SCHEMA))
    dec = Decoder(schema)
    rep = json.load(open(sys.argv[2]))
    out = []
    for d, hdr in (('c2s', 16), ('s2c', 12)):
        if d not in rep:
            continue
        for off, h, body in frames(bytes.fromhex(rep[d]['raw']), hdr):
            if not body:
                continue  # heartbeat
            name, obj, rest = dec.message(body)
            seq = h[6] | (h[7] << 8) if d == 'c2s' else h[0] | (h[1] << 8)
            out.append(dict(dir=d, off=off, seq=seq, hdr=h.hex(), len=len(body), type=name, rest=rest, data=obj))
            print(f'{d} @{off:6d} seq {seq:5d} len {len(body):5d} rest {rest:3d}  {name}')
    dst = sys.argv[3] if len(sys.argv) > 3 else 'decoded.json'
    json.dump(out, open(dst, 'w'), indent=1, default=default)
    if dec.problems:
        print('problems:', *dec.problems[:10], sep='\n  ')
    print('wrote', dst)

if __name__ == '__main__':
    main()
