#!/usr/bin/env bash
# 构建讯飞 C1 桌面助理屏保 APK。
#
#   零第三方依赖：只用 Android SDK build-tools + 本目录自带的 core/java。
#   产物：c1/C1Assistant.apk
#
#   依赖：
#     - Android SDK（ANDROID_HOME 或 ANDROID_SDK_ROOT）
#     - JDK 8+（javac/d8）
#   构建：
#     ./build.sh
#   真机安装：
#     adb install -r C1Assistant.apk
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"

SDK="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-$HOME/Library/Android/sdk}}"
BT="$SDK/build-tools/33.0.2"
[ -x "$BT/aapt2" ] || BT="$(ls -d "$SDK"/build-tools/* 2>/dev/null | sort | tail -1)"
PLAT="$(ls -d "$SDK"/platforms/android-* 2>/dev/null | sort | tail -1)"
JAR="$PLAT/android.jar"
CORE="$HERE/core/java"            # 自包含：Eink.java（波形控制）+ Prefs.java
SRC="$HERE/app"                   # APK 源码（com.c1mini.assistant）
OUT="$HERE/build"
KS="$HERE/debug.keystore"         # 调试签名；正式发布请换成自己的 keystore

for f in "$BT/aapt2" "$BT/d8" "$BT/zipalign" "$BT/apksigner" "$JAR" "$KS"; do
  [ -e "$f" ] || { echo "缺少构建工具: $f"; echo "请检查 ANDROID_HOME=$SDK"; exit 1; }
done

echo "=== C1 Assistant ==="
rm -rf "$OUT"; mkdir -p "$OUT/flat" "$OUT/classes" "$OUT/dex" "$OUT/gen"

echo "[1/5] 编译资源"
"$BT/aapt2" compile --dir "$SRC/res" -o "$OUT/flat"
flats="$(find "$OUT/flat" -name '*.flat' | sort)"

echo "[2/5] 链接 Manifest + assets"
"$BT/aapt2" link -o "$OUT/base.apk" -I "$JAR" \
  --manifest "$SRC/AndroidManifest.xml" -A "$SRC/assets" \
  --min-sdk-version 27 --target-sdk-version 27 \
  --java "$OUT/gen" --auto-add-overlay $flats

echo "[3/5] 编译 Java（core + app）"
{ find "$CORE" -name '*.java'; find "$SRC/java" -name '*.java'; find "$OUT/gen" -name 'R.java'; } > "$OUT/sources.txt"
javac -source 8 -target 8 -parameters -encoding UTF-8 -Xlint:-options -nowarn \
  -cp "$JAR" -d "$OUT/classes" @"$OUT/sources.txt"
"$BT/d8" --lib "$JAR" --min-api 27 --output "$OUT/dex" \
  $(find "$OUT/classes" -name '*.class' | sort)

echo "[4/5] 注入 dex"
python3 - "$OUT/base.apk" "$OUT/dex" <<'PY'
import os, sys, zipfile
apk, dexdir = sys.argv[1], sys.argv[2]
with zipfile.ZipFile(apk, 'a', zipfile.ZIP_DEFLATED) as z:
    for name in sorted(os.listdir(dexdir)):
        if name.endswith('.dex'):
            z.write(os.path.join(dexdir, name), name)
PY

echo "[5/5] 对齐 + 签名"
"$BT/zipalign" -f 4 "$OUT/base.apk" "$OUT/aligned.apk"
"$BT/apksigner" sign --ks "$KS" --ks-pass pass:c1mini --key-pass pass:c1mini \
  --out "$HERE/C1Assistant.apk" "$OUT/aligned.apk"
"$BT/apksigner" verify "$HERE/C1Assistant.apk"
ls -lh "$HERE/C1Assistant.apk"
echo "完成。真机安装：adb install -r $HERE/C1Assistant.apk"
