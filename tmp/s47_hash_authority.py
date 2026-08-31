from pathlib import Path
import hashlib

files = {
    "master": Path(r"D:\Rimiya Design Studio\Sedi\software\Sedi-v-1\workspace\docs\SEDI_SECTION15_MASTER_EXECUTION_LOG_FA.md"),
    "v601": Path(r"D:\Rimiya Design Studio\Sedi\software\Sedi-v-1\workspace\references\authoritative\Sedi_Cursor_Authoritative_Handoff_v601_FA.md"),
    "v615": Path(r"C:\Users\Javad Meighandi\Dropbox\Sedi\References\ChatGPT\Sedi_ChatGPT_Independent_Continuity_v615_FA.md"),
    "v614": Path(r"C:\Users\Javad Meighandi\Dropbox\Sedi\References\ChatGPT\Sedi_ChatGPT_Independent_Continuity_v614_FA.md"),
}
for k, p in files.items():
    b = p.read_bytes()
    crlf = b.count(b"\r\n")
    lf = b.count(b"\n") - crlf
    print(f"{k}|size={len(b)}|sha256={hashlib.sha256(b).hexdigest().upper()}|crlf={crlf}|lf={lf}")
