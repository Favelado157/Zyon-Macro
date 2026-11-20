import json
import re
from pathlib import Path
from urllib.request import Request, urlopen

REPO = "Favelado157/Ghostt_Macro"


def version_key(value):
    if not isinstance(value, str) or not re.fullmatch(r"v?\d+\.\d+\.\d+", value):
        raise ValueError("Versão inválida")
    return tuple(map(int, value.removeprefix("v").split(".")))


def find_update(config_dir, current):
    manifest = config_dir / "update.json"
    if manifest.is_file():
        data = json.loads(manifest.read_text(encoding="utf-8-sig"))
        raw_path = Path(data["installer"])
        installer = (config_dir / raw_path).resolve()
        if version_key(data["version"]) > version_key(current) and installer.is_file() and installer.suffix.lower() == ".exe":
            return data["version"], installer

    headers = {"Accept": "application/vnd.github+json"}
    request = Request(f"https://api.github.com/repos/{REPO}/releases/latest", headers=headers)
    with urlopen(request, timeout=5) as response:
        release = json.load(response)
    tag = release["tag_name"]
    has_installer = any(asset.get("name") == "GhosttzzKBot-Windows11.zip" and asset.get("state") == "uploaded"
                        for asset in release.get("assets", []))
    if has_installer and version_key(tag) > version_key(current):
        return tag, f"https://github.com/{REPO}/releases/tag/{tag}"
    return None
