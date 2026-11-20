import hashlib
import json
import re
import shutil
import stat
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from zipfile import ZipFile

REPO = "Favelado157/Ghostt_Macro"
ZIP_NAME = "Zyon-Macro-Windows11.zip"
INSTALLER_NAME = "Zyon-Macro-Setup.exe"
MAX_SIZE = 128 * 1024 * 1024


@dataclass(frozen=True)
class ReleaseAsset:
    url: str
    digest: str
    size: int


def version_key(value):
    if not isinstance(value, str) or not re.fullmatch(r"v?\d+\.\d+\.\d+", value):
        raise ValueError("Versão inválida")
    return tuple(map(int, value.removeprefix("v").split(".")))


def find_update(config_dir, current):
    manifest = config_dir / "update.json"
    if manifest.is_file():
        data = json.loads(manifest.read_text(encoding="utf-8-sig"))
        installer = (config_dir / data["installer"]).resolve()
        if version_key(data["version"]) > version_key(current) and installer.is_file() and installer.suffix.lower() == ".exe":
            return data["version"], installer

    headers = {"Accept": "application/vnd.github+json"}
    request = Request(f"https://api.github.com/repos/{REPO}/releases/latest", headers=headers)
    with urlopen(request, timeout=5) as response:
        release = json.load(response)
    tag = release["tag_name"]
    if version_key(tag) <= version_key(current):
        return None
    expected = f"https://github.com/{REPO}/releases/download/{tag}/{ZIP_NAME}"
    for asset in release.get("assets", []):
        if (asset.get("name") == ZIP_NAME and asset.get("state") == "uploaded"
                and asset.get("browser_download_url") == expected):
            digest, size = asset.get("digest"), asset.get("size")
            if not isinstance(digest, str) or not re.fullmatch(r"sha256:[a-f0-9]{64}", digest):
                raise ValueError("O GitHub não forneceu o SHA-256 da atualização.")
            if type(size) is not int or not 0 < size <= MAX_SIZE:
                raise ValueError("O tamanho da atualização é inválido.")
            return tag, ReleaseAsset(expected, digest, size)
    return None


def download_installer(asset, cache_dir, progress):
    cache_dir.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=cache_dir) as temporary:
        directory = Path(temporary)
        archive = directory / ZIP_NAME
        received = 0
        digest = hashlib.sha256()
        with urlopen(asset.url, timeout=20) as response, archive.open("wb") as output:
            if urlparse(response.geturl()).scheme != "https":
                raise ValueError("O download da atualização exige HTTPS.")
            while chunk := response.read(256 * 1024):
                received += len(chunk)
                if received > asset.size:
                    raise ValueError("O tamanho do download diverge do publicado.")
                digest.update(chunk)
                output.write(chunk)
                progress(received * 100 // asset.size)
        if received != asset.size or f"sha256:{digest.hexdigest()}" != asset.digest:
            raise ValueError("A verificação de integridade da atualização falhou.")

        installer = directory / INSTALLER_NAME
        with ZipFile(archive) as package:
            matches = [item for item in package.infolist() if item.filename == INSTALLER_NAME]
            if len(matches) != 1:
                raise ValueError("O pacote não contém um instalador único.")
            info = matches[0]
            if stat.S_ISLNK(info.external_attr >> 16) or not 2 <= info.file_size <= MAX_SIZE:
                raise ValueError("O instalador no pacote é inválido.")
            with package.open(info) as source, installer.open("wb") as output:
                signature = source.read(2)
                if signature != b"MZ":
                    raise ValueError("O instalador não é um executável do Windows.")
                output.write(signature)
                shutil.copyfileobj(source, output)
        target = cache_dir / INSTALLER_NAME
        installer.replace(target)
        return target
