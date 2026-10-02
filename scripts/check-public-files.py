"""Basic public-package checks; not a complete secret scanner."""
from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[1]
skip = {"node_modules", ".next", ".venv", "__pycache__", ".pytest_cache", ".git", ".runtime"}
issues = []
for path in root.rglob("*"):
    if any(part in skip for part in path.relative_to(root).parts) or not path.is_file():
        continue
    name = path.name
    if name.startswith(".env") and name != ".env.example":
        issues.append(f"{path.relative_to(root)}: local environment file exists; exclude from publication")
    if path.suffix in {".sqlite3", ".db", ".log"}:
        issues.append(f"{path.relative_to(root)}: runtime file")
    if path.suffix in {".py", ".ts", ".tsx", ".json"} and path.name != Path(__file__).name:
        content = path.read_text(encoding="utf-8-sig")
        if re.search(r"""(?:api_key|client_secret)\s*=\s*['"][A-Za-z0-9_+/=-]{28,}['"]""", content, re.I):
            issues.append(f"{path.relative_to(root)}: possible hardcoded secret")
if issues:
    print("\n".join(issues))
    sys.exit(1)
print("Basic public-file checks passed. Also inspect Git history before publication.")
