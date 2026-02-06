## Release C Final Test Evidence

This file is auto-appended by `scripts/release_c_final_tests.sh`.

- Tokens and secrets are masked.
- Raw curl outputs are saved under `/tmp/sedi_release_c/<run_id>/`.


## Release C Final Test Evidence

- **Run (UTC)**: `20260206T062736Z`
- **BASE_URL**: `http://91.107.168.130:8000`
- **USER_ID**: `1`
- **DEVICE_ID**: `Sedi001`
- **DEVICE_AUTH_HEADER**: `X-DEVICE-TOKEN`
- **Artifacts dir**: `/tmp/sedi_release_c/20260206T062736Z`

> Note: tokens/secrets are masked in this report.

### 00_root

- **URL**: `http://91.107.168.130:8000/`
- **Method**: `GET`
- **Auth header**: `X-DEVICE-TOKEN: (none)`
- **HTTP status (curl)**: **200**

**Response (tail, raw)**:

```
{"status":"Sedi AI Backend Running ✅","version":"2.0.1","base_language":"en","supported_languages":["en","fa","ar"],"server_time":"2026-02-06T06:27:40.433377","message":"Welcome to Sedi – your intelligent, caring, and proactive health companion 🌿"}
CURL_HTTP_STATUS:200
```

### 01_register_token1

- **URL**: `http://91.107.168.130:8000/devices/register?user_id=1`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: (none)`
- **HTTP status (curl)**: **200**

**Response (tail, raw)**:

```
{"ok":true,"data":{"device_id":"Sedi001","token":"***","rotated":true},"error":null}
CURL_HTTP_STATUS:200
```

### 02_reregister_token2

- **URL**: `http://91.107.168.130:8000/devices/register?user_id=1`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: (none)`
- **HTTP status (curl)**: **200**

**Response (tail, raw)**:

```
{"ok":true,"data":{"device_id":"Sedi001","token":"***","rotated":true},"error":null}
CURL_HTTP_STATUS:200
```

### 03_heartbeat_token2

- **URL**: `http://91.107.168.130:8000/device/heartbeat`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: (none)`
- **HTTP status (curl)**: **200**

**Response (tail, raw)**:

```
{"ok":true,"data":{"message":"Heartbeat received successfully."},"error":null}
CURL_HTTP_STATUS:200
```

### 04_heartbeat_token1

- **URL**: `http://91.107.168.130:8000/device/heartbeat`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: (none)`
- **HTTP status (curl)**: **200**

**Response (tail, raw)**:

```
{"ok":true,"data":{"message":"Heartbeat received successfully."},"error":null}
CURL_HTTP_STATUS:200
```

### 05_ingest_token2

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: (none)`
- **HTTP status (curl)**: **422**

**Response (tail, raw)**:

```
{"detail":[{"type":"missing","loc":["header","X-DEVICE-TOKEN"],"msg":"Field required","input":null}]}
CURL_HTTP_STATUS:422
```

### 06_ingest_duplicate

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: (none)`
- **HTTP status (curl)**: **422**

**Response (tail, raw)**:

```
{"detail":[{"type":"missing","loc":["header","X-DEVICE-TOKEN"],"msg":"Field required","input":null}]}
CURL_HTTP_STATUS:422
```

### 07_ingest_old_token1

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: (none)`
- **HTTP status (curl)**: **422**

**Response (tail, raw)**:

```
{"detail":[{"type":"missing","loc":["header","X-DEVICE-TOKEN"],"msg":"Field required","input":null}]}
CURL_HTTP_STATUS:422
```

### 08_rate_01

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: (none)`
- **HTTP status (curl)**: **422**

**Response (tail, raw)**:

```
{"detail":[{"type":"missing","loc":["header","X-DEVICE-TOKEN"],"msg":"Field required","input":null}]}
CURL_HTTP_STATUS:422
```

### 08_rate_02

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: (none)`
- **HTTP status (curl)**: **422**

**Response (tail, raw)**:

```
{"detail":[{"type":"missing","loc":["header","X-DEVICE-TOKEN"],"msg":"Field required","input":null}]}
CURL_HTTP_STATUS:422
```

### 08_rate_03

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: (none)`
- **HTTP status (curl)**: **422**

**Response (tail, raw)**:

```
{"detail":[{"type":"missing","loc":["header","X-DEVICE-TOKEN"],"msg":"Field required","input":null}]}
CURL_HTTP_STATUS:422
```

### 08_rate_04

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: (none)`
- **HTTP status (curl)**: **422**

**Response (tail, raw)**:

```
{"detail":[{"type":"missing","loc":["header","X-DEVICE-TOKEN"],"msg":"Field required","input":null}]}
CURL_HTTP_STATUS:422
```

### 08_rate_05

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: (none)`
- **HTTP status (curl)**: **422**

**Response (tail, raw)**:

```
{"detail":[{"type":"missing","loc":["header","X-DEVICE-TOKEN"],"msg":"Field required","input":null}]}
CURL_HTTP_STATUS:422
```

### 08_rate_06

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: (none)`
- **HTTP status (curl)**: **422**

**Response (tail, raw)**:

```
{"detail":[{"type":"missing","loc":["header","X-DEVICE-TOKEN"],"msg":"Field required","input":null}]}
CURL_HTTP_STATUS:422
```

### 08_rate_07

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: (none)`
- **HTTP status (curl)**: **422**

**Response (tail, raw)**:

```
{"detail":[{"type":"missing","loc":["header","X-DEVICE-TOKEN"],"msg":"Field required","input":null}]}
CURL_HTTP_STATUS:422
```

### 08_rate_08

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: (none)`
- **HTTP status (curl)**: **422**

**Response (tail, raw)**:

```
{"detail":[{"type":"missing","loc":["header","X-DEVICE-TOKEN"],"msg":"Field required","input":null}]}
CURL_HTTP_STATUS:422
```

### 08_rate_09

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: (none)`
- **HTTP status (curl)**: **422**

**Response (tail, raw)**:

```
{"detail":[{"type":"missing","loc":["header","X-DEVICE-TOKEN"],"msg":"Field required","input":null}]}
CURL_HTTP_STATUS:422
```

### 08_rate_10

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: (none)`
- **HTTP status (curl)**: **422**

**Response (tail, raw)**:

```
{"detail":[{"type":"missing","loc":["header","X-DEVICE-TOKEN"],"msg":"Field required","input":null}]}
CURL_HTTP_STATUS:422
```

### 08_rate_11

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: (none)`
- **HTTP status (curl)**: **422**

**Response (tail, raw)**:

```
{"detail":[{"type":"missing","loc":["header","X-DEVICE-TOKEN"],"msg":"Field required","input":null}]}
CURL_HTTP_STATUS:422
```

### 08_rate_12

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: (none)`
- **HTTP status (curl)**: **422**

**Response (tail, raw)**:

```
{"detail":[{"type":"missing","loc":["header","X-DEVICE-TOKEN"],"msg":"Field required","input":null}]}
CURL_HTTP_STATUS:422
```

### 08_rate_13

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: (none)`
- **HTTP status (curl)**: **422**

**Response (tail, raw)**:

```
{"detail":[{"type":"missing","loc":["header","X-DEVICE-TOKEN"],"msg":"Field required","input":null}]}
CURL_HTTP_STATUS:422
```

### 08_rate_14

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: (none)`
- **HTTP status (curl)**: **422**

**Response (tail, raw)**:

```
{"detail":[{"type":"missing","loc":["header","X-DEVICE-TOKEN"],"msg":"Field required","input":null}]}
CURL_HTTP_STATUS:422
```

### 08_rate_15

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: (none)`
- **HTTP status (curl)**: **422**

**Response (tail, raw)**:

```
{"detail":[{"type":"missing","loc":["header","X-DEVICE-TOKEN"],"msg":"Field required","input":null}]}
CURL_HTTP_STATUS:422
```

### 08_rate_16

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: (none)`
- **HTTP status (curl)**: **422**

**Response (tail, raw)**:

```
{"detail":[{"type":"missing","loc":["header","X-DEVICE-TOKEN"],"msg":"Field required","input":null}]}
CURL_HTTP_STATUS:422
```

### 08_rate_17

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: (none)`
- **HTTP status (curl)**: **422**

**Response (tail, raw)**:

```
{"detail":[{"type":"missing","loc":["header","X-DEVICE-TOKEN"],"msg":"Field required","input":null}]}
CURL_HTTP_STATUS:422
```

### 08_rate_18

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: (none)`
- **HTTP status (curl)**: **422**

**Response (tail, raw)**:

```
{"detail":[{"type":"missing","loc":["header","X-DEVICE-TOKEN"],"msg":"Field required","input":null}]}
CURL_HTTP_STATUS:422
```

### 08_rate_19

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: (none)`
- **HTTP status (curl)**: **422**

**Response (tail, raw)**:

```
{"detail":[{"type":"missing","loc":["header","X-DEVICE-TOKEN"],"msg":"Field required","input":null}]}
CURL_HTTP_STATUS:422
```

### 08_rate_20

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: (none)`
- **HTTP status (curl)**: **422**

**Response (tail, raw)**:

```
{"detail":[{"type":"missing","loc":["header","X-DEVICE-TOKEN"],"msg":"Field required","input":null}]}
CURL_HTTP_STATUS:422
```

### 08_rate_21

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: (none)`
- **HTTP status (curl)**: **422**

**Response (tail, raw)**:

```
{"detail":[{"type":"missing","loc":["header","X-DEVICE-TOKEN"],"msg":"Field required","input":null}]}
CURL_HTTP_STATUS:422
```

### 08_rate_22

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: (none)`
- **HTTP status (curl)**: **422**

**Response (tail, raw)**:

```
{"detail":[{"type":"missing","loc":["header","X-DEVICE-TOKEN"],"msg":"Field required","input":null}]}
CURL_HTTP_STATUS:422
```

### 08_rate_23

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: (none)`
- **HTTP status (curl)**: **422**

**Response (tail, raw)**:

```
{"detail":[{"type":"missing","loc":["header","X-DEVICE-TOKEN"],"msg":"Field required","input":null}]}
CURL_HTTP_STATUS:422
```

### 08_rate_24

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: (none)`
- **HTTP status (curl)**: **422**

**Response (tail, raw)**:

```
{"detail":[{"type":"missing","loc":["header","X-DEVICE-TOKEN"],"msg":"Field required","input":null}]}
CURL_HTTP_STATUS:422
```

### 08_rate_25

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: (none)`
- **HTTP status (curl)**: **422**

**Response (tail, raw)**:

```
{"detail":[{"type":"missing","loc":["header","X-DEVICE-TOKEN"],"msg":"Field required","input":null}]}
CURL_HTTP_STATUS:422
```

### 08_rate_26

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: (none)`
- **HTTP status (curl)**: **422**

**Response (tail, raw)**:

```
{"detail":[{"type":"missing","loc":["header","X-DEVICE-TOKEN"],"msg":"Field required","input":null}]}
CURL_HTTP_STATUS:422
```

### 08_rate_27

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: (none)`
- **HTTP status (curl)**: **422**

**Response (tail, raw)**:

```
{"detail":[{"type":"missing","loc":["header","X-DEVICE-TOKEN"],"msg":"Field required","input":null}]}
CURL_HTTP_STATUS:422
```

### 08_rate_28

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: (none)`
- **HTTP status (curl)**: **422**

**Response (tail, raw)**:

```
{"detail":[{"type":"missing","loc":["header","X-DEVICE-TOKEN"],"msg":"Field required","input":null}]}
CURL_HTTP_STATUS:422
```

### 08_rate_29

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: (none)`
- **HTTP status (curl)**: **422**

**Response (tail, raw)**:

```
{"detail":[{"type":"missing","loc":["header","X-DEVICE-TOKEN"],"msg":"Field required","input":null}]}
CURL_HTTP_STATUS:422
```

### 08_rate_30

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: (none)`
- **HTTP status (curl)**: **422**

**Response (tail, raw)**:

```
{"detail":[{"type":"missing","loc":["header","X-DEVICE-TOKEN"],"msg":"Field required","input":null}]}
CURL_HTTP_STATUS:422
```

### 08_rate_31

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: (none)`
- **HTTP status (curl)**: **422**

**Response (tail, raw)**:

```
{"detail":[{"type":"missing","loc":["header","X-DEVICE-TOKEN"],"msg":"Field required","input":null}]}
CURL_HTTP_STATUS:422
```

### 08_rate_32

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: (none)`
- **HTTP status (curl)**: **422**

**Response (tail, raw)**:

```
{"detail":[{"type":"missing","loc":["header","X-DEVICE-TOKEN"],"msg":"Field required","input":null}]}
CURL_HTTP_STATUS:422
```

### 08_rate_33

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: (none)`
- **HTTP status (curl)**: **422**

**Response (tail, raw)**:

```
{"detail":[{"type":"missing","loc":["header","X-DEVICE-TOKEN"],"msg":"Field required","input":null}]}
CURL_HTTP_STATUS:422
```

### 08_rate_34

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: (none)`
- **HTTP status (curl)**: **422**

**Response (tail, raw)**:

```
{"detail":[{"type":"missing","loc":["header","X-DEVICE-TOKEN"],"msg":"Field required","input":null}]}
CURL_HTTP_STATUS:422
```

### 08_rate_35

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: (none)`
- **HTTP status (curl)**: **422**

**Response (tail, raw)**:

```
{"detail":[{"type":"missing","loc":["header","X-DEVICE-TOKEN"],"msg":"Field required","input":null}]}
CURL_HTTP_STATUS:422
```

### 08_rate_36

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: (none)`
- **HTTP status (curl)**: **422**

**Response (tail, raw)**:

```
{"detail":[{"type":"missing","loc":["header","X-DEVICE-TOKEN"],"msg":"Field required","input":null}]}
CURL_HTTP_STATUS:422
```

### 08_rate_37

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: (none)`
- **HTTP status (curl)**: **422**

**Response (tail, raw)**:

```
{"detail":[{"type":"missing","loc":["header","X-DEVICE-TOKEN"],"msg":"Field required","input":null}]}
CURL_HTTP_STATUS:422
```

### 08_rate_38

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: (none)`
- **HTTP status (curl)**: **422**

**Response (tail, raw)**:

```
{"detail":[{"type":"missing","loc":["header","X-DEVICE-TOKEN"],"msg":"Field required","input":null}]}
CURL_HTTP_STATUS:422
```

### 08_rate_39

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: (none)`
- **HTTP status (curl)**: **422**

**Response (tail, raw)**:

```
{"detail":[{"type":"missing","loc":["header","X-DEVICE-TOKEN"],"msg":"Field required","input":null}]}
CURL_HTTP_STATUS:422
```

### 08_rate_40

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: (none)`
- **HTTP status (curl)**: **422**

**Response (tail, raw)**:

```
{"detail":[{"type":"missing","loc":["header","X-DEVICE-TOKEN"],"msg":"Field required","input":null}]}
CURL_HTTP_STATUS:422
```

### 09_list_devices

- **URL**: `http://91.107.168.130:8000/devices?user_id=1`
- **Method**: `GET`
- **Auth header**: `X-DEVICE-TOKEN: (none)`
- **HTTP status (curl)**: **200**

**Response (tail, raw)**:

```
{"ok":true,"data":{"devices":[{"device_id":"test-device-01","device_type":"prototype","status":"active","last_seen_at":"2026-02-04T12:41:47.523632","created_at":"2026-02-04T08:37:06.515752","revoked_at":null},{"device_id":"Sedi001","device_type":"heart_rate","status":"ok","last_seen_at":"2026-02-06T06:27:49.865481","created_at":"2026-02-04T07:09:19.700336","revoked_at":null}],"count":2},"error":null}
CURL_HTTP_STATUS:200
```

## Database Evidence (best-effort)

- **psql**: not found on PATH; skipping DB evidence.

## PASS/FAIL Summary

```
test	result	notes
Root endpoint reachable	INFO	See 00_root
Register issues device token	FAIL	Could not parse data.token (jq/python may be missing or response not ok)
Re-register rotates token (token2 != token1)	FAIL	Could not parse data.token
Heartbeat with token2 works (200 expected)	INFO	See 03_heartbeat_token2
Heartbeat with token1 behavior recorded	INFO	See 04_heartbeat_token1
Ingest with token2 works (200 and event_id returned)	FAIL	ok= event_id=
Ingest duplicate does NOT create new event	INFO	Unexpected duplicate response; see 06_ingest_duplicate
Ingest with invalid/old token returns HTTP 401	FAIL	status=422 ok= error.code= (BUG: HTTP status masking?)
Rate limit returns 429 after bursts	INFO	No 429 observed in 40 requests (limit may be higher or server uses multiple workers)
last_seen behavior observed (API-level)	INFO	See 09_list_devices for last_seen_at
```

## Bugs found

- Register issues device token: Could not parse data.token (jq/python may be missing or response not ok)
- Re-register rotates token (token2 != token1): Could not parse data.token
- Ingest with token2 works (200 and event_id returned): ok= event_id=
- Ingest with invalid/old token returns HTTP 401: status=422 ok= error.code= (BUG: HTTP status masking?)


## Release C Final Test Evidence

- **Run (UTC)**: `20260206T063219Z`
- **BASE_URL**: `http://91.107.168.130:8000`
- **USER_ID**: `1`
- **DEVICE_ID**: `Sedi001`
- **DEVICE_AUTH_HEADER**: `X-DEVICE-TOKEN`
- **Artifacts dir**: `/tmp/sedi_release_c/20260206T063219Z`

> Note: tokens/secrets are masked in this report.

### 00_root

- **URL**: `http://91.107.168.130:8000/`
- **Method**: `GET`
- **Auth header**: `X-DEVICE-TOKEN: (none)`
- **HTTP status (curl)**: **200**

**Response (tail, raw)**:

```
{"status":"Sedi AI Backend Running ✅","version":"2.0.1","base_language":"en","supported_languages":["en","fa","ar"],"server_time":"2026-02-06T06:32:20.533802","message":"Welcome to Sedi – your intelligent, caring, and proactive health companion 🌿"}
CURL_HTTP_STATUS:200
```

### 01_register_token1

- **URL**: `http://91.107.168.130:8000/devices/register?user_id=1`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: (none)`
- **HTTP status (curl)**: **200**

**Response (tail, raw)**:

```
{"ok":true,"data":{"device_id":"Sedi001","token":"***","rotated":true},"error":null}
CURL_HTTP_STATUS:200
```

### 02_reregister_token2

- **URL**: `http://91.107.168.130:8000/devices/register?user_id=1`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: (none)`
- **HTTP status (curl)**: **200**

**Response (tail, raw)**:

```
{"ok":true,"data":{"device_id":"Sedi001","token":"***","rotated":true},"error":null}
CURL_HTTP_STATUS:200
```

### 03_heartbeat_token2

- **URL**: `http://91.107.168.130:8000/device/heartbeat`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: _OTJ***TX3I`
- **HTTP status (curl)**: **200**

**Response (tail, raw)**:

```
{"ok":true,"data":{"message":"Heartbeat received successfully."},"error":null}
CURL_HTTP_STATUS:200
```

### 04_heartbeat_token1

- **URL**: `http://91.107.168.130:8000/device/heartbeat`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: CTaU***Yzu4`
- **HTTP status (curl)**: **200**

**Response (tail, raw)**:

```
{"ok":true,"data":{"message":"Heartbeat received successfully."},"error":null}
CURL_HTTP_STATUS:200
```

### 05_ingest_token2

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: _OTJ***TX3I`
- **HTTP status (curl)**: **200**

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 06_ingest_duplicate

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: _OTJ***TX3I`
- **HTTP status (curl)**: **200**

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 07_ingest_old_token1

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: CTaU***Yzu4`
- **HTTP status (curl)**: **200**

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_01

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: _OTJ***TX3I`
- **HTTP status (curl)**: **200**

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_02

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: _OTJ***TX3I`
- **HTTP status (curl)**: **200**

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_03

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: _OTJ***TX3I`
- **HTTP status (curl)**: **200**

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_04

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: _OTJ***TX3I`
- **HTTP status (curl)**: **200**

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_05

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: _OTJ***TX3I`
- **HTTP status (curl)**: **200**

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_06

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: _OTJ***TX3I`
- **HTTP status (curl)**: **200**

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_07

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: _OTJ***TX3I`
- **HTTP status (curl)**: **200**

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_08

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: _OTJ***TX3I`
- **HTTP status (curl)**: **200**

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_09

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: _OTJ***TX3I`
- **HTTP status (curl)**: **200**

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_10

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: _OTJ***TX3I`
- **HTTP status (curl)**: **200**

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_11

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: _OTJ***TX3I`
- **HTTP status (curl)**: **200**

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_12

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: _OTJ***TX3I`
- **HTTP status (curl)**: **200**

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_13

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: _OTJ***TX3I`
- **HTTP status (curl)**: **200**

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_14

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: _OTJ***TX3I`
- **HTTP status (curl)**: **200**

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_15

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: _OTJ***TX3I`
- **HTTP status (curl)**: **200**

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_16

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: _OTJ***TX3I`
- **HTTP status (curl)**: **200**

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_17

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: _OTJ***TX3I`
- **HTTP status (curl)**: **200**

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_18

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: _OTJ***TX3I`
- **HTTP status (curl)**: **200**

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_19

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: _OTJ***TX3I`
- **HTTP status (curl)**: **200**

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_20

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: _OTJ***TX3I`
- **HTTP status (curl)**: **200**

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_21

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: _OTJ***TX3I`
- **HTTP status (curl)**: **200**

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_22

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: _OTJ***TX3I`
- **HTTP status (curl)**: **200**

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_23

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: _OTJ***TX3I`
- **HTTP status (curl)**: **200**

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_24

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: _OTJ***TX3I`
- **HTTP status (curl)**: **200**

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_25

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: _OTJ***TX3I`
- **HTTP status (curl)**: **200**

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_26

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: _OTJ***TX3I`
- **HTTP status (curl)**: **200**

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_27

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: _OTJ***TX3I`
- **HTTP status (curl)**: **200**

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_28

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: _OTJ***TX3I`
- **HTTP status (curl)**: **000**

**Response (tail, raw)**:

```
CURL_HTTP_STATUS:000
```

### 08_rate_29

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: _OTJ***TX3I`
- **HTTP status (curl)**: **000**

**Response (tail, raw)**:

```
CURL_HTTP_STATUS:000
```

### 08_rate_30

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: _OTJ***TX3I`
- **HTTP status (curl)**: **000**

**Response (tail, raw)**:

```
CURL_HTTP_STATUS:000
```

### 08_rate_31

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: _OTJ***TX3I`
- **HTTP status (curl)**: **200**

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_32

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: _OTJ***TX3I`
- **HTTP status (curl)**: **200**

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_33

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: _OTJ***TX3I`
- **HTTP status (curl)**: **200**

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_34

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: _OTJ***TX3I`
- **HTTP status (curl)**: **200**

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_35

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: _OTJ***TX3I`
- **HTTP status (curl)**: **200**

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_36

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: _OTJ***TX3I`
- **HTTP status (curl)**: **200**

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_37

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: _OTJ***TX3I`
- **HTTP status (curl)**: **200**

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_38

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: _OTJ***TX3I`
- **HTTP status (curl)**: **200**

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_39

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: _OTJ***TX3I`
- **HTTP status (curl)**: **200**

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_40

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: _OTJ***TX3I`
- **HTTP status (curl)**: **200**

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 09_list_devices

- **URL**: `http://91.107.168.130:8000/devices?user_id=1`
- **Method**: `GET`
- **Auth header**: `X-DEVICE-TOKEN: (none)`
- **HTTP status (curl)**: **200**

**Response (tail, raw)**:

```
{"ok":true,"data":{"devices":[{"device_id":"test-device-01","device_type":"prototype","status":"active","last_seen_at":"2026-02-04T12:41:47.523632","created_at":"2026-02-04T08:37:06.515752","revoked_at":null},{"device_id":"Sedi001","device_type":"heart_rate","status":"ok","last_seen_at":"2026-02-06T06:32:28.903992","created_at":"2026-02-04T07:09:19.700336","revoked_at":null}],"count":2},"error":null}
CURL_HTTP_STATUS:200
```

## Database Evidence (best-effort)

- **psql**: not found on PATH; skipping DB evidence.

## PASS/FAIL Summary

```
test	result	notes
Root endpoint reachable	INFO	See 00_root
Register issues device token	PASS	token1=CTaU***Yzu4
Re-register rotates token (token2 != token1)	PASS	token2=_OTJ***TX3I
Heartbeat with token2 works (200 expected)	INFO	See 03_heartbeat_token2
Heartbeat with token1 behavior recorded	INFO	See 04_heartbeat_token1
Ingest with token2 works (200 and event_id returned)	FAIL	ok=false event_id=
Ingest duplicate does NOT create new event	INFO	Unexpected duplicate response; see 06_ingest_duplicate
Ingest with invalid/old token returns HTTP 401	FAIL	status=200 ok=false error.code=INTERNAL_ERROR (BUG: HTTP status masking?)
Rate limit returns 429 after bursts	INFO	No 429 observed in 40 requests (limit may be higher or server uses multiple workers)
last_seen behavior observed (API-level)	INFO	See 09_list_devices for last_seen_at
```

## Bugs found

- Ingest with token2 works (200 and event_id returned): ok=false event_id=
- Ingest with invalid/old token returns HTTP 401: status=200 ok=false error.code=INTERNAL_ERROR (BUG: HTTP status masking?)

---

## Post-fix summary (code changes applied)

**Run (UTC)**: `20260206T_post_fix` (evidence from code fix; re-run script in bash to regenerate full evidence)

### Root cause of prior INTERNAL_ERROR

- **HTTP status masking**: `HTTPException` (401 from invalid token, 422/429 from validation/rate-limit) was caught by the broad `except Exception` in `app/routers/device.py` and converted to HTTP 200 with `{"ok": false, "error": {"code": "INTERNAL_ERROR"}}`. Invalid token therefore appeared as 200 instead of 401.
- **Unexpected exceptions**: Any other exception (e.g. DB or memory layer) was also returned as HTTP 200 with INTERNAL_ERROR instead of HTTP 500.

### Code changes applied

1. **`app/routers/device.py`**
   - Re-raise `HTTPException` so 401/422/429 are preserved.
   - Order: `HTTPException` → `VitalValidationError` → `DeviceRateLimitExceeded` → `ValueError` → `Exception`.
   - For unexpected `Exception`: `logger.exception(...)` and return **HTTP 500** with `JSONResponse(content={"ok": False, "error": {"code": "INTERNAL_ERROR", "message": "Failed to ingest event"}})`.

2. **`app/services/device_ingestion.py`**
   - Replaced `logger.error(..., exc_info=True)` with `logger.exception(...)` for memory and alert failure paths so full tracebacks appear in logs.

3. **`scripts/release_c_final_tests.sh`**
   - **psql**: Use `/usr/bin/psql` if executable, else `command -v psql`; log detected path; on connect failure log exact error.
   - **Rate limit**: Burst increased to 200 requests; note that backend default is 30/min per process and multiple workers may not trigger 429.
   - Evidence header includes root-cause note for prior ingest failure.

### Expected PASS/FAIL after fix

| Test | Expected |
|------|----------|
| Ingest with invalid/old token returns HTTP 401 | **PASS** (status=401) |
| Ingest with token2 works (200 and event_id) | **PASS** if auth and DB are OK; if still failing, server logs will show full traceback (HTTP 500 with INTERNAL_ERROR) |
| Unexpected ingest errors | HTTP **500** with same JSON shape; traceback in server logs via `logger.exception` |

Re-run the test script from repo root with bash: `bash scripts/release_c_final_tests.sh` (requires bash, curl; jq or python for JSON; optional psql for DB evidence).

## Release C Final Test Evidence

- **Run (UTC)**: `20260206T064036Z`
- **BASE_URL**: `http://91.107.168.130:8000`
- **USER_ID**: `1`
- **DEVICE_ID**: `Sedi001`
- **DEVICE_AUTH_HEADER**: `X-DEVICE-TOKEN`
- **Artifacts dir**: `/tmp/sedi_release_c/20260206T064036Z`

> Note: tokens/secrets are masked in this report.

### 00_root

- **URL**: `http://91.107.168.130:8000/`
- **Method**: `GET`
- **Auth header**: `X-DEVICE-TOKEN: (none)`
- **HTTP status (curl)**: **200**

**Response headers (head, raw)**:

```
HTTP/1.1 200 OK
date: Fri, 06 Feb 2026 06:40:38 GMT
server: uvicorn
content-length: 255
content-type: application/json
```

**Response (tail, raw)**:

```
{"status":"Sedi AI Backend Running ✅","version":"2.0.1","base_language":"en","supported_languages":["en","fa","ar"],"server_time":"2026-02-06T06:40:38.574853","message":"Welcome to Sedi – your intelligent, caring, and proactive health companion 🌿"}
CURL_HTTP_STATUS:200
```

### 01_register_token1

- **URL**: `http://91.107.168.130:8000/devices/register?user_id=1`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: (none)`
- **HTTP status (curl)**: **200**

**Response headers (head, raw)**:

```
HTTP/1.1 200 OK
date: Fri, 06 Feb 2026 06:40:41 GMT
server: uvicorn
content-length: 124
content-type: application/json
```

**Response (tail, raw)**:

```
{"ok":true,"data":{"device_id":"Sedi001","token":"***","rotated":true},"error":null}
CURL_HTTP_STATUS:200
```

### 02_reregister_token2

- **URL**: `http://91.107.168.130:8000/devices/register?user_id=1`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: (none)`
- **HTTP status (curl)**: **200**

**Response headers (head, raw)**:

```
HTTP/1.1 200 OK
date: Fri, 06 Feb 2026 06:40:44 GMT
server: uvicorn
content-length: 124
content-type: application/json
```

**Response (tail, raw)**:

```
{"ok":true,"data":{"device_id":"Sedi001","token":"***","rotated":true},"error":null}
CURL_HTTP_STATUS:200
```

### 03_heartbeat_token2

- **URL**: `http://91.107.168.130:8000/device/heartbeat`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: JJBV***Dj8Q`
- **HTTP status (curl)**: **200**

**Response headers (head, raw)**:

```
HTTP/1.1 200 OK
date: Fri, 06 Feb 2026 06:40:47 GMT
server: uvicorn
content-length: 78
content-type: application/json
```

**Response (tail, raw)**:

```
{"ok":true,"data":{"message":"Heartbeat received successfully."},"error":null}
CURL_HTTP_STATUS:200
```

### 04_heartbeat_token1

- **URL**: `http://91.107.168.130:8000/device/heartbeat`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: hmW3***ao2A`
- **HTTP status (curl)**: **200**

**Response headers (head, raw)**:

```
HTTP/1.1 200 OK
date: Fri, 06 Feb 2026 06:40:50 GMT
server: uvicorn
content-length: 78
content-type: application/json
```

**Response (tail, raw)**:

```
{"ok":true,"data":{"message":"Heartbeat received successfully."},"error":null}
CURL_HTTP_STATUS:200
```

### 05_ingest_token2

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: JJBV***Dj8Q`
- **HTTP status (curl)**: **200**

**Response headers (head, raw)**:

```
HTTP/1.1 200 OK
date: Fri, 06 Feb 2026 06:40:52 GMT
server: uvicorn
content-length: 93
content-type: application/json
```

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 06_ingest_duplicate

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: JJBV***Dj8Q`
- **HTTP status (curl)**: **200**

**Response headers (head, raw)**:

```
HTTP/1.1 200 OK
date: Fri, 06 Feb 2026 06:40:56 GMT
server: uvicorn
content-length: 93
content-type: application/json
```

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 07_ingest_old_token1

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: hmW3***ao2A`
- **HTTP status (curl)**: **200**

**Response headers (head, raw)**:

```
HTTP/1.1 200 OK
date: Fri, 06 Feb 2026 06:40:59 GMT
server: uvicorn
content-length: 93
content-type: application/json
```

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_01

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: JJBV***Dj8Q`
- **HTTP status (curl)**: **200**

**Response headers (head, raw)**:

```
HTTP/1.1 200 OK
date: Fri, 06 Feb 2026 06:41:02 GMT
server: uvicorn
content-length: 93
content-type: application/json
```

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_02

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: JJBV***Dj8Q`
- **HTTP status (curl)**: **200**

**Response headers (head, raw)**:

```
HTTP/1.1 200 OK
date: Fri, 06 Feb 2026 06:41:05 GMT
server: uvicorn
content-length: 93
content-type: application/json
```

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_03

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: JJBV***Dj8Q`
- **HTTP status (curl)**: **200**

**Response headers (head, raw)**:

```
HTTP/1.1 200 OK
date: Fri, 06 Feb 2026 06:41:08 GMT
server: uvicorn
content-length: 93
content-type: application/json
```

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_04

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: JJBV***Dj8Q`
- **HTTP status (curl)**: **200**

**Response headers (head, raw)**:

```
HTTP/1.1 200 OK
date: Fri, 06 Feb 2026 06:41:10 GMT
server: uvicorn
content-length: 93
content-type: application/json
```

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_05

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: JJBV***Dj8Q`
- **HTTP status (curl)**: **200**

**Response headers (head, raw)**:

```
HTTP/1.1 200 OK
date: Fri, 06 Feb 2026 06:41:13 GMT
server: uvicorn
content-length: 93
content-type: application/json
```

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_06

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: JJBV***Dj8Q`
- **HTTP status (curl)**: **200**

**Response headers (head, raw)**:

```
HTTP/1.1 200 OK
date: Fri, 06 Feb 2026 06:41:16 GMT
server: uvicorn
content-length: 93
content-type: application/json
```

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_07

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: JJBV***Dj8Q`
- **HTTP status (curl)**: **200**

**Response headers (head, raw)**:

```
HTTP/1.1 200 OK
date: Fri, 06 Feb 2026 06:41:19 GMT
server: uvicorn
content-length: 93
content-type: application/json
```

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_08

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: JJBV***Dj8Q`
- **HTTP status (curl)**: **200**

**Response headers (head, raw)**:

```
HTTP/1.1 200 OK
date: Fri, 06 Feb 2026 06:41:21 GMT
server: uvicorn
content-length: 93
content-type: application/json
```

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_09

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: JJBV***Dj8Q`
- **HTTP status (curl)**: **200**

**Response headers (head, raw)**:

```
HTTP/1.1 200 OK
date: Fri, 06 Feb 2026 06:41:24 GMT
server: uvicorn
content-length: 93
content-type: application/json
```

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_10

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: JJBV***Dj8Q`
- **HTTP status (curl)**: **200**

**Response headers (head, raw)**:

```
HTTP/1.1 200 OK
date: Fri, 06 Feb 2026 06:41:27 GMT
server: uvicorn
content-length: 93
content-type: application/json
```

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_11

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: JJBV***Dj8Q`
- **HTTP status (curl)**: **200**

**Response headers (head, raw)**:

```
HTTP/1.1 200 OK
date: Fri, 06 Feb 2026 06:41:30 GMT
server: uvicorn
content-length: 93
content-type: application/json
```

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_12

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: JJBV***Dj8Q`
- **HTTP status (curl)**: **200**

**Response headers (head, raw)**:

```
HTTP/1.1 200 OK
date: Fri, 06 Feb 2026 06:41:53 GMT
server: uvicorn
content-length: 93
content-type: application/json
```

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_13

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: JJBV***Dj8Q`
- **HTTP status (curl)**: **200**

**Response headers (head, raw)**:

```
HTTP/1.1 200 OK
date: Fri, 06 Feb 2026 06:41:55 GMT
server: uvicorn
content-length: 93
content-type: application/json
```

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_14

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: JJBV***Dj8Q`
- **HTTP status (curl)**: **200**

**Response headers (head, raw)**:

```
HTTP/1.1 200 OK
date: Fri, 06 Feb 2026 06:41:58 GMT
server: uvicorn
content-length: 93
content-type: application/json
```

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_15

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: JJBV***Dj8Q`
- **HTTP status (curl)**: **200**

**Response headers (head, raw)**:

```
HTTP/1.1 200 OK
date: Fri, 06 Feb 2026 06:42:01 GMT
server: uvicorn
content-length: 93
content-type: application/json
```

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_16

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: JJBV***Dj8Q`
- **HTTP status (curl)**: **200**

**Response headers (head, raw)**:

```
HTTP/1.1 200 OK
date: Fri, 06 Feb 2026 06:42:04 GMT
server: uvicorn
content-length: 93
content-type: application/json
```

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_17

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: JJBV***Dj8Q`
- **HTTP status (curl)**: **200**

**Response headers (head, raw)**:

```
HTTP/1.1 200 OK
date: Fri, 06 Feb 2026 06:42:07 GMT
server: uvicorn
content-length: 93
content-type: application/json
```

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_18

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: JJBV***Dj8Q`
- **HTTP status (curl)**: **200**

**Response headers (head, raw)**:

```
HTTP/1.1 200 OK
date: Fri, 06 Feb 2026 06:42:09 GMT
server: uvicorn
content-length: 93
content-type: application/json
```

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_19

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: JJBV***Dj8Q`
- **HTTP status (curl)**: **200**

**Response headers (head, raw)**:

```
HTTP/1.1 200 OK
date: Fri, 06 Feb 2026 06:42:12 GMT
server: uvicorn
content-length: 93
content-type: application/json
```

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_20

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: JJBV***Dj8Q`
- **HTTP status (curl)**: **200**

**Response headers (head, raw)**:

```
HTTP/1.1 200 OK
date: Fri, 06 Feb 2026 06:42:15 GMT
server: uvicorn
content-length: 93
content-type: application/json
```

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_21

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: JJBV***Dj8Q`
- **HTTP status (curl)**: **200**

**Response headers (head, raw)**:

```
HTTP/1.1 200 OK
date: Fri, 06 Feb 2026 06:42:17 GMT
server: uvicorn
content-length: 93
content-type: application/json
```

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_22

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: JJBV***Dj8Q`
- **HTTP status (curl)**: **200**

**Response headers (head, raw)**:

```
HTTP/1.1 200 OK
date: Fri, 06 Feb 2026 06:42:20 GMT
server: uvicorn
content-length: 93
content-type: application/json
```

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_23

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: JJBV***Dj8Q`
- **HTTP status (curl)**: **200**

**Response headers (head, raw)**:

```
HTTP/1.1 200 OK
date: Fri, 06 Feb 2026 06:42:23 GMT
server: uvicorn
content-length: 93
content-type: application/json
```

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_24

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: JJBV***Dj8Q`
- **HTTP status (curl)**: **200**

**Response headers (head, raw)**:

```
HTTP/1.1 200 OK
date: Fri, 06 Feb 2026 06:42:25 GMT
server: uvicorn
content-length: 93
content-type: application/json
```

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_25

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: JJBV***Dj8Q`
- **HTTP status (curl)**: **200**

**Response headers (head, raw)**:

```
HTTP/1.1 200 OK
date: Fri, 06 Feb 2026 06:42:28 GMT
server: uvicorn
content-length: 93
content-type: application/json
```

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_26

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: JJBV***Dj8Q`
- **HTTP status (curl)**: **200**

**Response headers (head, raw)**:

```
HTTP/1.1 200 OK
date: Fri, 06 Feb 2026 06:43:27 GMT
server: uvicorn
content-length: 93
content-type: application/json
```

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_27

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: JJBV***Dj8Q`
- **HTTP status (curl)**: **200**

**Response headers (head, raw)**:

```
HTTP/1.1 200 OK
date: Fri, 06 Feb 2026 06:43:30 GMT
server: uvicorn
content-length: 93
content-type: application/json
```

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_28

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: JJBV***Dj8Q`
- **HTTP status (curl)**: **200**

**Response headers (head, raw)**:

```
HTTP/1.1 200 OK
date: Fri, 06 Feb 2026 06:43:33 GMT
server: uvicorn
content-length: 93
content-type: application/json
```

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_29

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: JJBV***Dj8Q`
- **HTTP status (curl)**: **200**

**Response headers (head, raw)**:

```
HTTP/1.1 200 OK
date: Fri, 06 Feb 2026 06:43:36 GMT
server: uvicorn
content-length: 93
content-type: application/json
```

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_30

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: JJBV***Dj8Q`
- **HTTP status (curl)**: **200**

**Response headers (head, raw)**:

```
HTTP/1.1 200 OK
date: Fri, 06 Feb 2026 06:43:38 GMT
server: uvicorn
content-length: 93
content-type: application/json
```

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_31

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: JJBV***Dj8Q`
- **HTTP status (curl)**: **200**

**Response headers (head, raw)**:

```
HTTP/1.1 200 OK
date: Fri, 06 Feb 2026 06:43:41 GMT
server: uvicorn
content-length: 93
content-type: application/json
```

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_32

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: JJBV***Dj8Q`
- **HTTP status (curl)**: **200**

**Response headers (head, raw)**:

```
HTTP/1.1 200 OK
date: Fri, 06 Feb 2026 06:43:43 GMT
server: uvicorn
content-length: 93
content-type: application/json
```

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_33

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: JJBV***Dj8Q`
- **HTTP status (curl)**: **200**

**Response headers (head, raw)**:

```
HTTP/1.1 200 OK
date: Fri, 06 Feb 2026 06:43:47 GMT
server: uvicorn
content-length: 93
content-type: application/json
```

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_34

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: JJBV***Dj8Q`
- **HTTP status (curl)**: **200**

**Response headers (head, raw)**:

```
HTTP/1.1 200 OK
date: Fri, 06 Feb 2026 06:43:49 GMT
server: uvicorn
content-length: 93
content-type: application/json
```

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_35

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: JJBV***Dj8Q`
- **HTTP status (curl)**: **200**

**Response headers (head, raw)**:

```
HTTP/1.1 200 OK
date: Fri, 06 Feb 2026 06:43:52 GMT
server: uvicorn
content-length: 93
content-type: application/json
```

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_36

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: JJBV***Dj8Q`
- **HTTP status (curl)**: **200**

**Response headers (head, raw)**:

```
HTTP/1.1 200 OK
date: Fri, 06 Feb 2026 06:43:55 GMT
server: uvicorn
content-length: 93
content-type: application/json
```

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_37

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: JJBV***Dj8Q`
- **HTTP status (curl)**: **200**

**Response headers (head, raw)**:

```
HTTP/1.1 200 OK
date: Fri, 06 Feb 2026 06:43:58 GMT
server: uvicorn
content-length: 93
content-type: application/json
```

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_38

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: JJBV***Dj8Q`
- **HTTP status (curl)**: **200**

**Response headers (head, raw)**:

```
HTTP/1.1 200 OK
date: Fri, 06 Feb 2026 06:44:00 GMT
server: uvicorn
content-length: 93
content-type: application/json
```

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_39

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: JJBV***Dj8Q`
- **HTTP status (curl)**: **200**

**Response headers (head, raw)**:

```
HTTP/1.1 200 OK
date: Fri, 06 Feb 2026 06:44:03 GMT
server: uvicorn
content-length: 93
content-type: application/json
```

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 08_rate_40

- **URL**: `http://91.107.168.130:8000/device/ingest`
- **Method**: `POST`
- **Auth header**: `X-DEVICE-TOKEN: JJBV***Dj8Q`
- **HTTP status (curl)**: **200**

**Response headers (head, raw)**:

```
HTTP/1.1 200 OK
date: Fri, 06 Feb 2026 06:44:07 GMT
server: uvicorn
content-length: 93
content-type: application/json
```

**Response (tail, raw)**:

```
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"Failed to ingest event"}}
CURL_HTTP_STATUS:200
```

### 09_list_devices

- **URL**: `http://91.107.168.130:8000/devices?user_id=1`
- **Method**: `GET`
- **Auth header**: `X-DEVICE-TOKEN: (none)`
- **HTTP status (curl)**: **200**

**Response headers (head, raw)**:

```
HTTP/1.1 200 OK
date: Fri, 06 Feb 2026 06:44:10 GMT
server: uvicorn
content-length: 403
content-type: application/json
```

**Response (tail, raw)**:

```
{"ok":true,"data":{"devices":[{"device_id":"test-device-01","device_type":"prototype","status":"active","last_seen_at":"2026-02-04T12:41:47.523632","created_at":"2026-02-04T08:37:06.515752","revoked_at":null},{"device_id":"Sedi001","device_type":"heart_rate","status":"ok","last_seen_at":"2026-02-06T06:40:50.562376","created_at":"2026-02-04T07:09:19.700336","revoked_at":null}],"count":2},"error":null}
CURL_HTTP_STATUS:200
```

## Database Evidence (best-effort)

- **psql**: not found on PATH; skipping DB evidence.

## PASS/FAIL Summary

```
test	result	notes
Root endpoint reachable	INFO	See 00_root
Register issues device token	PASS	token1=hmW3***ao2A
Re-register rotates token (token2 != token1)	PASS	token2=JJBV***Dj8Q
Heartbeat with token2 works (200 expected)	INFO	See 03_heartbeat_token2
Heartbeat with token1 behavior recorded	INFO	See 04_heartbeat_token1
Ingest with token2 works (200 and event_id returned)	FAIL	ok=false event_id=
Ingest duplicate does NOT create new event	INFO	Unexpected duplicate response; see 06_ingest_duplicate
Ingest with invalid/old token returns HTTP 401	FAIL	status=200 ok=false error.code=INTERNAL_ERROR (BUG: HTTP status masking?)
Rate limit returns 429 after bursts	INFO	No 429 observed in 40 requests (limit may be higher or server uses multiple workers)
last_seen behavior observed (API-level)	INFO	See 09_list_devices for last_seen_at
```

## Bugs found

- Ingest with token2 works (200 and event_id returned): ok=false event_id=
- Ingest with invalid/old token returns HTTP 401: status=200 ok=false error.code=INTERNAL_ERROR (BUG: HTTP status masking?)

---

## Post-fix summary (code changes applied)

**Run (UTC)**: `20260206T_post_fix` (evidence from code fix; re-run script in bash to regenerate full evidence)

### Root cause of prior INTERNAL_ERROR

- **HTTP status masking**: `HTTPException` (401 from invalid token, 422/429 from validation/rate-limit) was caught by the broad `except Exception` in `app/routers/device.py` and converted to HTTP 200 with `{"ok": false, "error": {"code": "INTERNAL_ERROR"}}`. Invalid token therefore appeared as 200 instead of 401.
- **Unexpected exceptions**: Any other exception (e.g. DB or memory layer) was also returned as HTTP 200 with INTERNAL_ERROR instead of HTTP 500.

### Code changes applied

1. **`app/routers/device.py`**
   - Re-raise `HTTPException` so 401/422/429 are preserved.
   - Order: `HTTPException` → `VitalValidationError` → `DeviceRateLimitExceeded` → `ValueError` → `Exception`.
   - For unexpected `Exception`: `logger.exception(...)` and return **HTTP 500** with `JSONResponse(content={"ok": False, "error": {"code": "INTERNAL_ERROR", "message": "Failed to ingest event"}})`.

2. **`app/services/device_ingestion.py`**
   - Replaced `logger.error(..., exc_info=True)` with `logger.exception(...)` for memory and alert failure paths so full tracebacks appear in logs.

3. **`scripts/release_c_final_tests.sh`**
   - **psql**: Use `/usr/bin/psql` if executable, else `command -v psql`; log detected path; on connect failure log exact error.
   - **Rate limit**: Burst increased to 200 requests; note that backend default is 30/min per process and multiple workers may not trigger 429.
   - Evidence header includes root-cause note for prior ingest failure.

### Expected PASS/FAIL after fix

| Test | Expected |
|------|----------|
| Ingest with invalid/old token returns HTTP 401 | **PASS** (status=401) |
| Ingest with token2 works (200 and event_id) | **PASS** if auth and DB are OK; if still failing, server logs will show full traceback (HTTP 500 with INTERNAL_ERROR) |
| Unexpected ingest errors | HTTP **500** with same JSON shape; traceback in server logs via `logger.exception` |

Re-run the test script from repo root with bash: `bash scripts/release_c_final_tests.sh` (requires bash, curl; jq or python for JSON; optional psql for DB evidence).
