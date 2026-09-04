import UnityPy, glob, os, json, sys
sys.stdout.reconfigure(encoding='utf-8')
ROOT=r"C:/Users/lemac/Swordxstafd-datamine"
OUT=ROOT+"/out"
DEST=OUT+"/skill_icons"; os.makedirs(DEST,exist_ok=True)
data=json.load(open(OUT+"/_skills.json",encoding='utf-8'))
want={f"skill_{s['id']}":s['id'] for t in data['tiers'] for c in t['classes'] for s in c['skills']}
# class icons too: ItemIcon/ProfessionSmall/NNN
for t in data['tiers']:
    for c in t['classes']:
        ic=(c.get('icon') or '').strip()
        if ic: want[os.path.basename(ic)]=f"class_{os.path.basename(ic)}"
print(f"looking for {len(want)} sprites",flush=True)
have=set()
files=sorted(glob.glob(OUT+"/device_cache/files/yoo/*/CacheFiles/*/*/__data"))
print(f"scanning {len(files)} cached bundles",flush=True)
for n,f in enumerate(files,1):
    if n%1500==0: print(f"  {n}/{len(files)} found={len(have)}",flush=True)
    try:
        if open(f,'rb').read(7)!=b'UnityFS': continue
        env=UnityPy.load(f)
    except Exception: continue
    try: keys=" ".join(env.container.keys()).lower()
    except Exception: keys=""
    if 'itemicon/skill' not in keys and 'professionsmall' not in keys: continue
    for o in env.objects:
        if o.type.name not in ("Sprite","Texture2D"): continue
        try:
            d=o.read(); nm=getattr(d,'m_Name','') or ''
            if nm in want and want[nm] not in have:
                tag=want[nm]
                d.image.save(os.path.join(DEST,f"{tag}.png"))
                have.add(tag)
        except Exception: pass
print(f"DONE extracted {len(have)}",flush=True)
