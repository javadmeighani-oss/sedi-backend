# SMS Gateway – Environment Variables

No secrets or API keys are stored in code. All configuration is via environment variables.

| Variable | Values | Description |
|----------|--------|-------------|
| `SMS_PROVIDER` | `mediana` (default), `dummy` | Real SMS uses `mediana`. `dummy` for tests/dev without network. |
| `SMS_DISABLED` | `true`, `false` | When `true`, no SMS is sent; OTP is logged (masked) and `dev_code` may be returned. |
| `MEDIANA_API_KEY` | *(required for mediana)* | API key from Mediana panel (`X-API-KEY` header). Do not commit. |
| `MEDIANA_OTP_PATTERN_CODE` | *(required for mediana)* | Approved OTP pattern code from Mediana panel. |

**DEV:** Set `SMS_PROVIDER=dummy` and/or `SMS_DISABLED=true` to avoid sending real SMS.  
**PROD:** Set `SMS_DISABLED=false`, `SMS_PROVIDER=mediana`, `MEDIANA_API_KEY`, and `MEDIANA_OTP_PATTERN_CODE` on the server (e.g. `/etc/sedi/sedi-backend.env`); do not put them in the repo.

Legacy `SMS_PROVIDER=kavenegar` and other unknown values are **not supported**. With `SMS_DISABLED=false`, OTP requests fail with a provider error. With `SMS_DISABLED=true`, the gateway is not called.

Mediana sends OTP via `POST https://api.mediana.ir/sms/v1/send/otp` with `patternCode`, `recipient` (`09xxxxxxxxx`), and `otpCode` (6-digit code from backend).
