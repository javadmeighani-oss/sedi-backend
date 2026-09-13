# Sedi Gadget BLE and Data Interface Spec V1 (FA/EN)

**Audience:** electronics / firmware team  
**Scope:** implement this interface only. Do not invent Sedi clinical, account, or notification policy.

## 1. Purpose / responsibility boundary

| Gadget (firmware) | Mobile | Sedi backend (I9) |
|---|---|---|
| Sense + prepare measurements | BLE relay + durable forward | Persist, attribute HealthSubject, rollup |
| Emit DEVICE_REPORTED STABLE/UNSTABLE when device computes it | Preserve facts; never diagnose | Source class DEVICE_REPORTED |
| Possess device_secret + setup code | Gateway install id + claim UX | Claim / gateway / binding authority |

Firmware MUST NOT create: `user_id`, `account_id`, `health_subject_id`, caregiver/mother/son semantics, Sedi notification policy, or Sedi clinical conclusions.

## 2. Device ID

Format: `SEDI-<TYPE>-<12_DIGIT_SERIAL>`  
Immutable for device lifetime. Exposed via DEVICE_INFO.

## 3. Protocol

`PROTOCOL_VERSION = 1`  
Characteristic payloads = UTF-8 JSON objects with `"protocol": 1`.

## 4. Frozen GATT

**Primary Service:** `f2e6981f-4dc1-526d-a2c8-a043a1cddfa5`

| Characteristic | UUID | Properties |
|---|---|---|
| DEVICE_INFO | `467febf0-6629-59ed-a748-009d244af686` | READ |
| CLAIM_CHALLENGE | `3a8d703c-ac28-58b4-8eaa-84ac990fae71` | WRITE |
| CLAIM_PROOF | `4d2c701d-1d1d-5a72-a961-e8d23fe9dfa0` | READ / INDICATE |
| DEVICE_DATA | `f144aeda-24e5-56df-a132-2e428b0dc1c2` | NOTIFY |
| DEVICE_STATUS | `46b5efee-7522-5e4a-abbf-4d391478109b` | READ / NOTIFY |
| DEVICE_CONTROL | `82db957c-b074-5e7b-b484-23fc0165aee1` | WRITE |

## 5. DEVICE_INFO (minimum)

```json
{
  "protocol": 1,
  "device_id": "SEDI-HR-000000000001",
  "device_type": "heart_rate",
  "model": "SEDI-G1",
  "firmware_version": "1.0.0"
}
```

## 6. DEVICE_DATA (minimum)

```json
{
  "protocol": 1,
  "packet_id": "stable-unique-id",
  "measured_at": "2026-09-12T18:00:00Z",
  "measurements": [
    { "type": "heart_rate", "bpm": 72 }
  ],
  "stability": "STABLE"
}
```

- `packet_id`: stable identity for this prepared packet. **Retransmission MUST reuse the same `packet_id`.**
- `measured_at`: original observation time (UTC ISO-8601). Do not rewrite on retry.
- `stability` / per-measurement `stability`: optional `STABLE` | `UNSTABLE` = **DEVICE_REPORTED** only (gadget SoT). Not a Sedi diagnosis.

### Supported prepared measurement examples

| type | example fields |
|---|---|
| heart_rate / HR | `bpm` |
| blood_pressure / BP | `systolic`, `diastolic` |
| spo2 | `spo2` (percent) |
| temperature | `celsius` or `value` |
| glucose | device-supported glucose fields |

## 7. DEVICE_STATUS (non-clinical)

Device/transport facts only, e.g.:

```json
{
  "protocol": 1,
  "battery_percent": 86,
  "contact_ok": true,
  "operating_status": "measuring"
}
```

Do not place clinical STABLE/UNSTABLE authority exclusively in DEVICE_STATUS; prefer DEVICE_DATA when reporting vital stability.

## 8. Setup code + possession proof

- Setup code: `^[0-9]{4}$` (commissioning UX / claim).
- Possession proof: `HMAC-SHA256(device_secret, device_id || challenge_nonce)` via CLAIM_CHALLENGE / CLAIM_PROOF.
- Bluetooth Bond ≠ Sedi Claim ≠ Mobile Gateway Authorization.

## 9. Reconnect

Firmware should remain advertise/connectable under normal power policy. Mobile performs minimal in-process reconnect. Background CompanionDeviceManager is out of scope for this interface revision.

## 10. Raw ECG

Raw ECG waveform = **separate G6 contract**. Do not embed raw ECG arrays in protocol v1 DEVICE_DATA JSON for this Gate.

## 11. Explicit firmware forbids

- user_id / account_id / health_subject_id  
- caregiver / mother / son semantics  
- Sedi notification policy  
- Sedi diagnosis or clinical conclusions  
- Inventing thresholds for Sedi clinical STABLE/UNSTABLE  

Electronics team implements this interface only.
