# SMS Gateway – Environment Variables

No secrets or API keys are stored in code. All configuration is via environment variables.

| Variable | Values | Description |
|----------|--------|-------------|
| `SMS_PROVIDER` | `kavenegar` (default), `dummy` | Which sender to use. Unknown values fall back to `dummy`. |
| `SMS_DISABLED` | `true`, `false` | Used by the OTP service: when `true`, no SMS is sent and OTP is only logged. This module does not enforce it. |
| `KAVENEGAR_API_KEY` | *(required for kavenegar)* | API key from Kavenegar panel. Do not commit. |
| `KAVENEGAR_SENDER` | *(optional)* | Sender line / short number. If unset, Kavenegar default is used. |

**DEV:** Set `SMS_PROVIDER=dummy` and/or `SMS_DISABLED=true` to avoid sending real SMS.  
**PROD:** Set `KAVENEGAR_API_KEY` in the environment (e.g. systemd or secret manager); do not put it in repo or config files.
