"""Pull Sword x Staff game traffic out of a pktmon pcapng and reassemble it into two byte streams.

  python tools/liveproto/parse.py game.pcapng streams.json

The game talks KCP over UDP (TCP fallback) to the planes server on port 8033 (9033 on the backup
host). pktmon writes raw IPv4 frames and logs each packet once per NDIS component, so packets are
de-duplicated. KCP push segments are ordered by sequence number per direction; the result is the
byte stream the client's GodNetClient sees. Feed the output to gproto.py.
"""
import sys, struct, json, math, re, hashlib, collections

GAME_PORTS = {8033, 9033}

def blocks(path):
    b = open(path, 'rb').read()
    i, endian = 0, '<'
    while i + 8 <= len(b):
        btype, blen = struct.unpack_from(endian + 'II', b, i)
        if btype == 0x0A0D0D0A:  # section header block carries the byte order
            endian = '<' if b[i + 8:i + 12] == b'\x4d\x3c\x2b\x1a' else '>'
            btype, blen = struct.unpack_from(endian + 'II', b, i)
        if blen < 12:
            break
        yield btype, b[i + 8:i + blen - 4], endian
        i += blen

def frames(path):
    linktypes = []
    for btype, body, e in blocks(path):
        if btype == 1:
            linktypes.append(struct.unpack_from(e + 'H', body, 0)[0])
        elif btype == 6:
            ifid, tsh, tsl, caplen, origlen = struct.unpack_from(e + 'IIIII', body, 0)
            yield ((tsh << 32) | tsl) / 1e6, body[20:20 + caplen]
        elif btype == 3:
            origlen = struct.unpack_from(e + 'I', body, 0)[0]
            yield 0.0, body[4:4 + origlen]

def ip_layer(f):
    if len(f) >= 20 and f[0] >> 4 == 4 and (f[0] & 15) >= 5:  # raw IPv4 (what pktmon emits)
        return f
    if len(f) >= 14:  # ethernet
        et = struct.unpack_from('!H', f, 12)[0]
        off = 14
        while et == 0x8100 and len(f) >= off + 4:
            et = struct.unpack_from('!H', f, off + 2)[0]; off += 4
        if et == 0x0800:
            return f[off:]
    return None

def parse_ip(p):
    ihl = (p[0] & 15) * 4
    total = struct.unpack_from('!H', p, 2)[0]
    ident = struct.unpack_from('!H', p, 4)[0]
    proto = p[9]
    src = '.'.join(map(str, p[12:16])); dst = '.'.join(map(str, p[16:20]))
    body = p[ihl:total] if total >= ihl else p[ihl:]
    if proto == 17 and len(body) >= 8:
        sp, dp, ln = struct.unpack_from('!HHH', body, 0)
        return dict(proto='udp', src=src, dst=dst, sp=sp, dp=dp, id=ident, data=body[8:ln] if ln >= 8 else body[8:])
    if proto == 6 and len(body) >= 20:
        sp, dp, seq = struct.unpack_from('!HHI', body, 0)
        doff = (body[12] >> 4) * 4
        return dict(proto='tcp', src=src, dst=dst, sp=sp, dp=dp, id=ident, seq=seq, data=body[doff:])
    return None

def entropy(b):
    if not b:
        return 0.0
    c = collections.Counter(b); n = len(b)
    return -sum(v / n * math.log2(v / n) for v in c.values())

def kcp_segments(data):
    """Split one UDP datagram into KCP segments; None if it is not KCP (the connect handshake is not)."""
    out, i = [], 0
    while i + 24 <= len(data):
        conv, cmd, frg, wnd, ts, sn, una, ln = struct.unpack_from('<IBBHIIII', data, i)
        if cmd not in (81, 82, 83, 84) or ln > len(data) - i - 24:
            return None
        out.append(dict(cmd=cmd, sn=sn, data=data[i + 24:i + 24 + ln]))
        i += 24 + ln
    return out if i == len(data) else None

def main():
    path = sys.argv[1]
    outp = sys.argv[2] if len(sys.argv) > 2 else 'streams.json'
    seen, pkts, total = set(), [], 0
    for ts, f in frames(path):
        total += 1
        ipl = ip_layer(f)
        p = parse_ip(ipl) if ipl else None
        if not p or (p['sp'] not in GAME_PORTS and p['dp'] not in GAME_PORTS):
            continue
        key = (p['src'], p['dst'], p['sp'], p['dp'], p['id'], hashlib.md5(p['data']).hexdigest())
        if key in seen:
            continue
        seen.add(key); p['ts'] = ts; pkts.append(p)
    print(f'frames in file: {total}; unique game packets: {len(pkts)}')
    if not pkts:
        return
    for k, v in collections.Counter((p['proto'], p['src'], p['sp'], p['dst'], p['dp']) for p in pkts).most_common():
        print('  flow', k, v)
    streams = collections.defaultdict(dict)
    for p in pkts:
        if p['proto'] != 'udp':
            continue
        d = 'c2s' if p['dp'] in GAME_PORTS else 's2c'
        for s in kcp_segments(p['data']) or []:
            if s['cmd'] == 81:
                streams[d][s['sn']] = s['data']
    tcp = collections.defaultdict(list)
    for p in pkts:
        if p['proto'] == 'tcp' and p['data']:
            d = 'c2s' if p['dp'] in GAME_PORTS else 's2c'
            tcp[d].append((p['seq'], p['data']))
    report = {}
    for d in ('c2s', 's2c'):
        data = b''.join(streams[d][k] for k in sorted(streams[d]))
        if not data and tcp[d]:
            data = b''.join(x[1] for x in sorted(tcp[d]))
        if not data:
            continue
        sns = sorted(streams[d])
        gaps = sum(1 for a, b in zip(sns, sns[1:]) if b != a + 1)
        print(f'{d}: {len(sns)} KCP segments ({gaps} gaps), {len(data)} bytes, entropy {entropy(data):.2f} bits/byte')
        report[d] = dict(bytes=len(data), gaps=gaps, raw=data.hex())
    json.dump(report, open(outp, 'w'))
    print('wrote', outp)

if __name__ == '__main__':
    main()
