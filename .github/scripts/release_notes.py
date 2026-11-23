import ast
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TAG = os.environ.get("GITHUB_REF_NAME", "").strip()
VERSION = TAG if TAG.startswith("v") else "v" + TAG

notes = ""
try:
    tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(getattr(target, "id", "") == "CHANGELOG" for target in node.targets):
            continue
        changelog = ast.literal_eval(node.value)
        for version, _exe_name, items in changelog:
            if version == VERSION:
                notes = "\n".join("- " + item for item in items)
                break
        break
except Exception as exc:
    print("Failed to parse CHANGELOG: " + str(exc))

if not notes:
    notes = "- 版本更新 " + VERSION

release_notes = "## " + VERSION + "\n\n" + notes + "\n"
(ROOT / "release-notes.md").write_text(release_notes, encoding="utf-8")
print(release_notes)
