from pathlib import Path
import hashlib
from datetime import datetime, timezone

p = Path(r"D:\Rimiya Design Studio\Sedi\software\Sedi-v-1\workspace\docs\SEDI_SECTION15_MASTER_EXECUTION_LOG_FA.md")
b = p.read_bytes()
print("SIZE", len(b))
print("SHA", hashlib.sha256(b).hexdigest())
print("END", b[-24:])
print("CRLF", b.endswith(b"\r\n"))
print("HAS360", "\u00a7360".encode("utf-8") in b)
print("UTC", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
