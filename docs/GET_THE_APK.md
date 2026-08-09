# Getting the Sword x Staff package

The pipeline needs the game's `.apk` or `.xapk` on a machine that can reach
an app source. Pick whichever fits what you have. **Sword x Staff** is
`com.zjcs.android.us` (Boltray Games), ~2.4 GB.

> Only obtain the game through means allowed by Boltray's terms and your app
> store. This is for analyzing a copy you're entitled to run.

## Option A — pull it from your own Android device (cleanest)

If you have the game installed on a phone:

```bash
# with adb (Android platform-tools) and USB debugging on:
adb shell pm path com.zjcs.android.us        # lists base.apk + split apks
# copy each path it prints:
adb pull /data/app/.../base.apk ./SwordxStaff/base.apk
# ...repeat for every split***.apk line, into the same folder, then:
cd SwordxStaff && zip -r ../SwordxStaff.xapk .   # bundle into one file
./datamine.sh SwordxStaff.xapk
```

This gives you the exact build you're playing, no third-party mirror.

## Option B — an Android emulator on your computer

Install an emulator (e.g. the one bundled with Android Studio, or a
standard x86_64/arm system image), sign in, install the game from Google
Play, then use the `adb pull` steps from Option A. IL2CPP dumping wants the
**arm64-v8a** `libil2cpp.so`; if your emulator is x86 you'll still get all
the data and `dump.cs` structure, but for native-body analysis prefer an
arm64 image or the device route.

## Option C — a reputable APK mirror

Sites like APKPure/APKCombo/Uptodown host the `.xapk`. Download the full
`.xapk` (not a "lite"/"mod" build — you want the untouched original), then:

```bash
./datamine.sh ~/Downloads/Sword-x-Staff_1.0.0.xapk
```

Verify you grabbed the official package name `com.zjcs.android.us` and a
plausible size (~2.4 GB). Avoid anything labeled "mod", "cracked", or
"unlimited" — those are repacked and will give you wrong or tampered data.

## What the pipeline needs from it

- `lib/arm64-v8a/libil2cpp.so`  ← native code (IL2CPP)
- `assets/bin/Data/Managed/Metadata/global-metadata.dat`  ← symbol names
- `assets/**` AssetBundles / `resources.assets`  ← balance data

Stage 2 confirms all three are present and tells you if anything's missing.
