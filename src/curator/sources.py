"""Source registry (sources.yaml) and verified download from Zenodo."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import pathlib
import urllib.request

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "sources.yaml"
RAW_DIR = ROOT / "data" / "raw"
ZENODO_API = "https://zenodo.org/api/records/{}"


def load_registry(path: pathlib.Path = REGISTRY) -> dict[str, dict]:
    with open(path, encoding="utf-8") as f:
        reg = yaml.safe_load(f)
    return {s["id"]: s for s in reg["sources"]}


def citation(meta: dict) -> str:
    creators = "; ".join(meta["creators"]) if isinstance(meta["creators"], list) else meta["creators"]
    return f"{creators} ({meta['year']}). {meta['title']}. Zenodo. https://doi.org/{meta['doi']}"


def source_dir(meta: dict, raw_dir: pathlib.Path = RAW_DIR) -> pathlib.Path:
    return raw_dir / str(meta["zenodo_record"])


def _md5(path: pathlib.Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "spatial-experience-dataset-curator"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def download(meta: dict, raw_dir: pathlib.Path = RAW_DIR) -> pathlib.Path:
    """Download the files a source needs and check each against Zenodo's md5.

    Files already on disk with the right checksum are not downloaded again.
    """
    out = source_dir(meta, raw_dir)
    out.mkdir(parents=True, exist_ok=True)
    record = json.loads(_get(ZENODO_API.format(meta["zenodo_record"])))

    licence = record["metadata"].get("license", {}).get("id", "").upper()
    if licence != meta["licence"].upper():
        raise RuntimeError(
            f"{meta['id']}: Zenodo now lists licence {licence!r}, registry says {meta['licence']!r}")

    wanted = [f for f in record["files"]
              if any(fnmatch.fnmatch(f["key"], pat) for pat in meta["files"])]
    if not wanted:
        raise RuntimeError(f"{meta['id']}: no files on Zenodo match {meta['files']}")

    manifest = {}
    for f in wanted:
        target = out / f["key"]
        expected = f["checksum"].split(":", 1)[1]
        if not (target.exists() and _md5(target) == expected):
            target.write_bytes(_get(f["links"]["self"]))
            got = _md5(target)
            if got != expected:
                target.unlink()
                raise RuntimeError(f"{meta['id']}/{f['key']}: md5 {got} != {expected}")
        manifest[f["key"]] = expected
    (out / "_manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True))
    return out
