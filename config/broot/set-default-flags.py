import re
import sys
from pathlib import Path

conf = Path(sys.argv[1])
text = conf.read_text(encoding="utf-8")
if re.search(r"(?m)^\s*default_flags:", text):
    raise SystemExit(0)
patched, count = re.subn(r"(?m)^#\s*default_flags:.*$", "default_flags: g", text, count=1)
if count == 0:
    patched = text.rstrip() + "\n\ndefault_flags: g\n"
conf.write_text(patched, encoding="utf-8")
