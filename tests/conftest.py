import pytest

from curator import pipeline
from curator.sources import RAW_DIR, load_registry, source_dir


def _raw_present() -> bool:
    reg = load_registry()
    return all((source_dir(m) / "_manifest.json").exists() for m in reg.values())


@pytest.fixture(scope="session")
def registry():
    return load_registry()


@pytest.fixture(scope="session")
def trials():
    """The real combined table. Downloads from Zenodo the first time if needed."""
    try:
        return pipeline.build(fetch=not _raw_present())
    except OSError as e:   # offline and nothing cached
        pytest.skip(f"raw data not available: {e}")


@pytest.fixture(scope="session")
def raw_dir(trials):
    return RAW_DIR
