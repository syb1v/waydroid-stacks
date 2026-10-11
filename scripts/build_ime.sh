#!/usr/bin/env bash
# Сборка тихой IME (third_party/wdsime.apk) из исходников ime/
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SDK="${ANDROID_HOME:-$HOME/Android/Sdk}"

if [ ! -d "$SDK" ]; then
    echo "Android SDK не найден: $SDK" >&2
    exit 1
fi

BT="$(ls -d "$SDK"/build-tools/* | sort -V | tail -1)"
PLATFORM_JAR="$(ls -d "$SDK"/platforms/android-* | sort -V | tail -1)/android.jar"
BUILD="$ROOT/ime/build"
OUT="$ROOT/third_party/wdsime.apk"

rm -rf "$BUILD"
mkdir -p "$BUILD/classes" "$BUILD/dex"

echo "== aapt2 compile =="
"$BT/aapt2" compile --dir "$ROOT/ime/res" -o "$BUILD/res.zip"

echo "== aapt2 link =="
"$BT/aapt2" link \
    -o "$BUILD/base.apk" \
    -I "$PLATFORM_JAR" \
    --manifest "$ROOT/ime/AndroidManifest.xml" \
    --min-sdk-version 26 \
    --target-sdk-version 33 \
    "$BUILD/res.zip"

echo "== javac =="
javac -source 8 -target 8 -Xlint:-options \
    -cp "$PLATFORM_JAR" \
    -d "$BUILD/classes" \
    "$ROOT/ime/src/io/github/syb1v/wdsime/WdsIme.java"

echo "== d8 =="
"$BT/d8" --release --lib "$PLATFORM_JAR" --min-api 26 \
    --output "$BUILD/dex" \
    "$BUILD"/classes/io/github/syb1v/wdsime/*.class

echo "== упаковка =="
cp "$BUILD/base.apk" "$BUILD/unsigned.apk"
python3 - "$BUILD/unsigned.apk" "$BUILD/dex/classes.dex" <<'PY'
import sys, zipfile
apk, dex = sys.argv[1], sys.argv[2]
with zipfile.ZipFile(apk, "a", zipfile.ZIP_DEFLATED) as z:
    z.write(dex, "classes.dex")
PY
"$BT/zipalign" -f 4 "$BUILD/unsigned.apk" "$BUILD/aligned.apk"

KS="$BUILD/debug.keystore"
if [ ! -f "$KS" ]; then
    keytool -genkeypair -v -keystore "$KS" -alias androiddebugkey \
        -storepass android -keypass android \
        -keyalg RSA -keysize 2048 -validity 10000 \
        -dname "CN=Android Debug,O=Android,C=US"
fi

"$BT/apksigner" sign \
    --ks "$KS" --ks-pass pass:android --key-pass pass:android \
    --ks-key-alias androiddebugkey \
    --out "$OUT" "$BUILD/aligned.apk"

echo "OK: $OUT"
