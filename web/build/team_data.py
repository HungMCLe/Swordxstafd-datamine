"""Turn decoded live players (tools/liveproto roster export) into fighters the team simulator can load.

The input is out/liveproto/fighters.json (never committed). Each fighter's sheet comes straight from the
server's BattleProps block, which was checked against the in-game Character Stats screen. Skills keep
their own rank and level, as the game stores them."""
from __future__ import annotations
import json
from pathlib import Path

CLASS_NAME = {"Zhanshi": "Warrior", "Fashi": "Mage", "Huwei": "Knight", "Doushi": "Duelist", "Shushi": "Sorcerer",
              "Xianzhe": "Sage", "Dunjiashi": "Paladin", "Kuangzhanshi": "Berserker", "Modaoshi": "Archmage",
              "Mishushi": "Arcanist", "Shouhuzhe": "Guardian", "Zhengfuzhe": "Conqueror", "Huimiezhe": "Destroyer",
              "Zhangkongzhe": "Dominator"}

# BattleProps -> sheet field. Percent props are stored x100 by the game.
PCT = {"CritRatePercent": "cr", "CritPowerPercent": "cd", "CritAvoidPercent": "critres", "BlockPercent": "blockrate",
       "BlockValuePercent": "blockeff", "BlockAvoidPercent": "blockavoid", "DmgAddPercent": "boost",
       "DmgReducePercent": "dmgres", "PlayerDmgAddScale": "pvpadd", "PlayerDmgReduceScale": "pvpres",
       "CureAddPercent": "cureadd", "BeCureAddPercent": "becureadd", "FinalCureScale": "finalcure",
       "DodgePercent": "dodge"}
FLAT = {"MaxHp": "hp", "Attack": "atk", "Defence": "def", "Speed": "spd", "ElementMaster": "mast",
        "KongFuMaster": "kfm", "ElementResistance": "eres", "KongFuResistance": "kfr", "EffectRate": "erate",
        "EffectDodge": "edodge", "MoveDist": "move",
        # flat "value" forms that join the percent rolls divided by their per-rank base (CalcDamageTypeImpl, CalcCureAdd)
        "CritRatePercentValue": "crv", "CritAvoidPercentValue": "crav", "BlockPercentValue": "bv",
        "BlockAvoidPercentValue": "bav", "CureAdd": "cureaddv", "BeCureAdd": "becureaddv", "CritPower": "critpowerv",
        "BlockValue": "blockvaluev"}
ELE = ["Wind", "Water", "Fire", "Light", "Dark"]
BASES = ["BaseElementMaster", "BaseElementResistance", "BaseKongFuMaster", "BaseKongFuResistance",
         "BaseCritRatePercentValue", "BaseCritAvoidPercentValue", "BaseBlockPercentValue",
         "BaseBlockAvoidPercentValue", "BaseElementAdd", "BaseElementReduce", "BaseEffectRate", "BaseEffectDodge",
         "PlayerSkillDmgReduceScale", "ProSkillDmgReduceScale", "BaseCureAdd", "BaseBeCureAdd"]


def sheet_of(bp: dict) -> dict:
    s = {}
    for k, f in FLAT.items():
        s[f] = bp.get(k, 0)
    for k, f in PCT.items():
        s[f] = bp.get(k, 0) / 10000.0   # 2960 -> 29.60% -> 0.296
    s["aff"] = {e: bp.get(f"{e}DamageAdd", 0) for e in ELE}
    s["aegis"] = {e: bp.get(f"{e}DamageReduce", 0) for e in ELE}
    s["bases"] = {k: bp.get(k, 0) for k in BASES}
    return s


def build(out: Path, ranks: list, skills_by_id: dict) -> list:
    src = out / "liveproto" / "fighters.json"
    if not src.exists():
        return []
    raw = json.loads(src.read_text(encoding="utf-8"))
    rank_index = {r["internal"]: i for i, r in enumerate(ranks)}
    fighters = []
    for f in raw:
        if not f.get("battleProps") or not f.get("skills"):
            continue
        techs, charms = [], []
        for sk in f["skills"]:
            entry = {"id": sk["id"], "rank": sk.get("rank") or 1, "level": sk.get("level") or 1}
            if sk["id"] not in skills_by_id:
                continue
            (techs if skills_by_id[sk["id"]].get("kind") == "Technique" else charms).append(entry)
        fighters.append({
            "id": f["id"], "name": f["name"],
            "cls": CLASS_NAME.get(f.get("profession"), f.get("profession")),
            "level": f.get("level"), "subRank": f.get("subRank"),
            "rank": rank_index.get(f.get("subRank"), 0),
            "rating": f.get("combatRating") or f.get("rankScore"),
            "rankPos": f.get("rankPos"),
            "sheet": sheet_of(f["battleProps"]),
            "techs": techs[:4], "charms": charms[:4],
            "pet": f.get("engagePet"),
        })
    return fighters
