# liveproto: decoding the live game protocol

Passive, read-only decoding of what the game client already sends and receives. It records the
emulator's own traffic on this PC, nothing is injected, no custom client is run, and no credentials
are involved. Captures contain other players' names and ids, so they live under `out/` (gitignored)
and are never committed.

## What the wire looks like

- Transport: KCP over UDP to the planes server on port 8033 (9033 on the backup host), TCP fallback.
  The client resolves `zhangjcsomqreleaseplanes6.boltraygames.com` to four addresses and picks the
  lowest-latency one per session, so filter by port, not by IP.
- Not encrypted. Payloads are MessagePack in the clear.
- Frame: `F0 F0` magic, u16 body length, then 12 more header bytes (client to server) or 8 (server
  to client), then the body. Body length 0 is the heartbeat.
- Body: u16 opcode (`Common.SerializeType` const of the message class) + a MessagePack array of the
  class's `[Key(n)]` fields in the order the generated `<Class>Formatter.Serialize` writes them.
- Fields whose declared type is one of the `BaseSerializable<T>` types in
  `AutoMPG/RootSerializer.GetFormatters` (abstract bases, `MySerializable`, interfaces) are written as
  a raw u16 opcode (0 = null) followed by the concrete class's array. Every other class is a plain
  array. Enums are ints, DateTime is the msgpack timestamp extension.
- This build writes `float` as 4 raw big-endian bytes with no `0xCA` marker.

All of the above was checked against a real capture: every frame in both directions decodes with no
trailing bytes.

## Pipeline

```
powershell -ExecutionPolicy Bypass -File tools\liveproto\capture.ps1 -Seconds 120 -OutDir out\liveproto   (admin shell)
python tools\liveproto\gproto.py schema                                  # once, from out/decompiled
python tools\liveproto\parse.py out\liveproto\game.pcapng out\liveproto\streams.json
python tools\liveproto\gproto.py decode out\liveproto\streams.json out\liveproto\decoded.json
```

`schema.json` is derived from the decompiled client and is regenerated, not committed.

Keep what you decode with `roster.py`: it merges every capture into `out/liveproto/roster.json` (one entry
per player: name, class, level, rank, combat rating, the live `BattleProps`, the full sheet, and a short
history), prints a table, and exports fighters for the simulators. The site build turns that export into
`web/dist/assets/fighters.json` (gitignored) for the team battle page, so `combat/team.html` lists every
captured top-100 player; a long capture while clicking through the whole list fills it (98 of 100 in one pass).

```
python tools\liveproto\roster.py ingest out\liveproto\cap3\decoded.json
python tools\liveproto\roster.py show Wei Elexarie
python tools\liveproto\roster.py fighters --top -o out\liveproto\fighters.json     # captured players of the latest top-100, in rank order
```

A live `BattleProps` block was checked against the in-game Character Stats screen of the same player:
all 33 stats shown there (ATK, DEF, HP, SPD, crit, block, boosts, masteries, affinities, aegis) matched
to the digit. "Accuracy" on that screen is `BlockAvoidPercent` (26.6% shown, 2660 in the block).

## What the messages carry

Seen while browsing the Arena for two minutes:

| Message | Direction | Content |
|---|---|---|
| `PlayerGetPersonalTopContentDataResponse` | s2c | Top-100 player ids and combat ratings for the requested ranking, plus your own rank |
| `PlayerLiteInfoGetResponse` | s2c | Per player: name, class, level, sub rank, combat rating, appearance, online flag |
| `PlayerBriefInfo` | s2c | An opponent's whole sheet: every equipped item with level, gems and rolled props, both skill plans with skill ranks and levels, treasures, furniture, cooking, NPC friendship levels, Fantomon, talent trees |
| `RpcResponse251D7A29` (`WrappedRpcResponse<Dictionary<long, CharacterLiteStatusInfo>>`) | s2c | A player's live computed battle stats (`BattleProps`, keyed by `PropType`), HP %, level, combat rating |
| `CharacterLiteStatusInfo` | s2c push | The same live stats for players around you on the map |
| `ChatInfo` | s2c push | Chat and system messages |

Known gap: the reply to `LegionInfoRequest` arrives with opcode 12714, which is not in this build's
`SerializeType` table, so it is left as a generic value (it holds a `LegionDisplayInfo` list).
