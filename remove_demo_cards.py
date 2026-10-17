from pathlib import Path
from datetime import datetime
import re
import shutil
root = Path(r"C:\Users\DELL\code_seller_static")
files = ["index.html", "bestsellers.html", "deals.html"]
demo_names = {
    "AI Starter Project",
    "Modern Web Starter",
    "Game Development Kit",
    "Developer Utility",
}
backup_dir = root / "backups" / f"before_demo_card_removal_{datetime.now():%Y%m%d_%H%M%S}"
backup_dir.mkdir(parents=True, exist_ok=True)
pattern = re.compile(
    r'<article\b[^>]*class=["\'][^"\']*\bproduct-card\b[^"\']*["\'][^>]*>.*?</article>',
    re.IGNORECASE | re.DOTALL,
)
total_removed = 0
for filename in files:
    path = root / filename
    if not path.exists():
        print(f"SKIPPED: {filename} not found")
        continue
    original = path.read_text(encoding="utf-8")
    matches = list(pattern.finditer(original))
    remove = [
        m for m in matches
        if any(
            re.search(r"<h3\b[^>]*>\s*" + re.escape(name) + r"\s*</h3>",
                      m.group(0), re.IGNORECASE)
            for name in demo_names
        )
    ]
    if not remove:
        print(f"{filename}: no matching demo cards")
        continue
    shutil.copy2(path, backup_dir / filename)
    updated = original
    for match in reversed(remove):
        updated = updated[:match.start()] + updated[match.end():]
    path.write_text(updated, encoding="utf-8")
    total_removed += len(remove)
    print(f"{filename}: removed {len(remove)} demo card(s)")
print(f"\nTotal demo cards removed: {total_removed}")
print(f"Backups saved in: {backup_dir}")
# Verify that the target product cards are gone.
for filename in files:
    path = root / filename
    if not path.exists():
        continue
    text = path.read_text(encoding="utf-8")
    remaining = [
        name for name in demo_names
        if re.search(r"<h3\b[^>]*>\s*" + re.escape(name) + r"\s*</h3>",
                     text, re.IGNORECASE)
    ]
    print(f"{filename} remaining demo names: {remaining}")
