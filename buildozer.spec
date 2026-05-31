[app]
title           = Nexus AI
package.name    = nexusai
package.domain  = org.nexus
source.dir      = .
source.include_exts = py,png,jpg,kv,atlas,json
version         = 1.0

requirements    = python3,kivy,psutil,SpeechRecognition,pyjnius

android.permissions = RECORD_AUDIO, INTERNET, MODIFY_AUDIO_SETTINGS

android.api         = 33
android.minapi      = 21
android.archs       = arm64-v8a, armeabi-v7a

orientation         = portrait
fullscreen          = 0

[buildozer]
log_level = 2
