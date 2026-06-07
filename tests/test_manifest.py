from audiobooker.manifest import Manifest, hash_parts, sha256_file


def test_hash_parts_stable_and_sensitive():
    a = hash_parts("extract-v1", "abc", 300)
    assert a == hash_parts("extract-v1", "abc", 300)
    assert a != hash_parts("extract-v1", "abc", 200)
    assert a != hash_parts("extract-v2", "abc", 300)


def test_sha256_file(tmp_path):
    f = tmp_path / "x.bin"
    f.write_bytes(b"hello")
    assert sha256_file(f) == (
        "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    )


def test_stage_roundtrip_and_staleness(tmp_path):
    m = Manifest.load_or_create(tmp_path)
    h = hash_parts("extract-v1", "src", 300)

    assert not m.stage_fresh("extract", h)
    m.stage_done("extract", h)
    assert m.stage_fresh("extract", h)
    # Different inputs → stale
    assert not m.stage_fresh("extract", hash_parts("extract-v1", "src", 200))

    # Persisted across load
    m2 = Manifest.load_or_create(tmp_path)
    assert m2.stage_fresh("extract", h)


def test_stage_with_missing_artifact_not_fresh(tmp_path):
    m = Manifest.load_or_create(tmp_path)
    h = hash_parts("x")
    m.stage_done("extract", h, artifact="pages.jsonl")
    assert not m.stage_fresh("extract", h)          # artifact doesn't exist
    (tmp_path / "pages.jsonl").write_text("{}")
    assert m.stage_fresh("extract", h)


def test_downstream_invalidation(tmp_path):
    m = Manifest.load_or_create(tmp_path)
    m.stage_done("segment", hash_parts("seg"))
    assert m.stage_fresh("segment", hash_parts("seg"))
    # Re-running an upstream stage marks segment stale
    m.stage_done("extract", hash_parts("ext"))
    assert not m.stage_fresh("segment", hash_parts("seg"))
