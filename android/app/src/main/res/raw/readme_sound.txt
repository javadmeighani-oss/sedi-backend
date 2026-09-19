Custom notification sound for Sedi alerts
==========================================

FILE NAME (exact):
  sedi_alarm.wav

LOCATION:
  android/app/src/main/res/raw/sedi_alarm.wav

STATUS (G1):
  Binary present. Canonical V1 signature sound.
  See frontend/docs/SEDI_ALARM_SOUND_LICENSE_G1.md

RULES:
  - Android references raw resources by name WITHOUT extension.
  - The code uses: RawResourceAndroidNotificationSound('sedi_alarm').
  - Runtime download of notification sound is PROHIBITED.
