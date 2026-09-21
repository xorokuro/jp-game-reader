#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
command -v xcodegen >/dev/null || brew install xcodegen
xcodegen generate
xcodebuild -project JapaneseReader.xcodeproj -scheme JapaneseReader -configuration Release -sdk iphoneos -destination 'generic/platform=iOS' -derivedDataPath build CODE_SIGNING_ALLOWED=NO build
mkdir -p build/package/Payload
cp -R build/Build/Products/Release-iphoneos/JapaneseReader.app build/package/Payload/
(cd build/package && ditto -c -k --keepParent Payload ../JapaneseReader.ipa)
echo "Built: ios/build/JapaneseReader.ipa (unsigned; sign with AltStore or your Apple account)"
