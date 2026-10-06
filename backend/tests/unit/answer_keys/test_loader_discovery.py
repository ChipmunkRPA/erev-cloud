"""Answer-key discovery, safe parsing and models (docs/dev-guide.md §9.5.8 DG-AK-30, DG-AK-31;
BUILD_SPEC EKC-8)."""

from __future__ import annotations

import hashlib
import shutil
import tempfile
from collections import Counter
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml
from support.answer_keys.loader import (
    ANSWER_KEY_ROOT,
    REPO_ROOT,
    SCHEMA_ID,
    AnswerKeyError,
    discover,
    load,
    parse_yaml,
)

SAMPLE = ANSWER_KEY_ROOT / "rnd" / "RND-CHK-001.yaml"
WITHDRAWN = ("POS-S9-PRESENTATION-EX38-CASEA", "POS-S9-PRESENTATION-EX38-CASEB")


@pytest.fixture
def scratch_root() -> Iterator[Path]:
    base = REPO_ROOT / ".run" / "tmp"
    base.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="answer-keys-", dir=base))
    try:
        yield root
    finally:
        shutil.rmtree(root)


def _write_key(root: Path, data: object, name: str = "rnd/RND-CHK-001.yaml") -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path


def _sample() -> dict[str, object]:
    data = parse_yaml(SAMPLE.read_text(encoding="utf-8"), path=SAMPLE)
    assert isinstance(data, dict)
    return data


def test_discover_corpus(scratch_root: Path) -> None:
    paths = discover()
    # 243 + eight ENG-D1 + three ENG-C6 keys (D-91, D-97) + one of R-116 (a)
    assert len(paths) == 255
    assert paths == sorted(paths)
    assert all(path.suffix == ".yaml" for path in paths)
    assert not [path for path in paths if "_coverage" in path.relative_to(ANSWER_KEY_ROOT).parts]
    assert ANSWER_KEY_ROOT / "_coverage" in ANSWER_KEY_ROOT.iterdir()

    (scratch_root / "README.md").write_text("# Corpus\n", encoding="utf-8")
    (scratch_root / "_coverage").mkdir()
    (scratch_root / "_coverage" / "notes.md").write_text("ignored\n", encoding="utf-8")
    key_path = scratch_root / "rnd" / "RND-CHK-001.yaml"
    key_path.parent.mkdir()
    shutil.copyfile(SAMPLE, key_path)
    assert discover(scratch_root) == [key_path]

    notes = scratch_root / "notes.txt"
    notes.write_text("not a key\n", encoding="utf-8")
    with pytest.raises(AnswerKeyError) as raised:
        discover(scratch_root)
    assert raised.value.path == notes
    notes.unlink()

    root_yaml = scratch_root / "RND-CHK-001.yaml"
    shutil.copyfile(SAMPLE, root_yaml)
    with pytest.raises(AnswerKeyError) as raised:
        discover(scratch_root)
    assert raised.value.path == root_yaml


def test_safe_loader_keeps_scalars_as_strings(tmp_path: Path) -> None:
    text = "amount: 12.30\ndate: 2026-01-01\nn: 5\nnothing: null\ntilde: ~\nflag: true\nword: yes\n"
    assert parse_yaml(text, path=tmp_path / "scalars.yaml") == {
        "amount": "12.30",
        "date": "2026-01-01",
        "n": "5",
        "nothing": None,
        "tilde": None,
        "flag": True,
        "word": "yes",
    }

    duplicate = "world:\n  currencies: [USD]\n  currencies: [EUR]\n"
    with pytest.raises(AnswerKeyError) as raised:
        parse_yaml(duplicate, path=tmp_path / "duplicate.yaml")
    assert raised.value.pointer == "/world/currencies"
    assert "duplicate mapping key 'currencies'" in raised.value.message


def test_load_every_file() -> None:
    loaded = [load(path) for path in discover()]
    # 243 + eight ENG-D1 + three ENG-C6 keys (D-91, D-97) + one of R-116 (a)
    assert len(loaded) == 255
    assert {item.key.schema_id for item in loaded} == {SCHEMA_ID}
    statuses = Counter(item.key.status for item in loaded)
    assert statuses == {"active": 253, "withdrawn": 2}
    assert sorted(item.key.id for item in loaded if item.key.status == "withdrawn") == list(
        WITHDRAWN
    )
    runners = Counter(item.key.runner for item in loaded if item.key.status == "active")
    assert runners == {"engine": 248, "platform": 5}
    assert len({item.key.id for item in loaded}) == 255
    for item in loaded:
        assert item.path.stem == item.key.id
        assert item.sha256 == hashlib.sha256(item.path.read_bytes()).hexdigest()


def test_models_forbid_extra_fields(scratch_root: Path) -> None:
    data = _sample()
    data["foo"] = "bar"
    with pytest.raises(AnswerKeyError) as raised:
        load(_write_key(scratch_root, data))
    assert raised.value.pointer == "/foo"

    nested = _sample()
    timeline = nested["timeline"]
    assert isinstance(timeline, list) and isinstance(timeline[0], dict)
    timeline[0]["colour"] = "blue"
    with pytest.raises(AnswerKeyError) as raised:
        load(_write_key(scratch_root, nested))
    assert raised.value.pointer == "/timeline/0/colour"

    missing = _sample()
    del missing["title"]
    with pytest.raises(AnswerKeyError) as raised:
        load(_write_key(scratch_root, missing))
    assert raised.value.pointer == "/title"
