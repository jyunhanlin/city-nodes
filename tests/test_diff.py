from pipeline.diff import compute_diff, DiffResult


def _item(name: str, lat: float, lng: float, note: str = "") -> dict:
    return {
        "name": name,
        "address": f"區{name}",
        "lat": lat,
        "lng": lng,
        "category": "trash_bin",
        "note": note,
    }


def test_no_changes():
    old = [_item("A", 25.0, 121.0)]
    new = [_item("A", 25.0, 121.0)]
    diff = compute_diff(old, new)
    assert diff.added == 0
    assert diff.removed == 0
    assert diff.changed == 0
    assert diff.has_changes is False
    assert diff.summary == "無變更"


def test_added_items():
    old = [_item("A", 25.0, 121.0)]
    new = [_item("A", 25.0, 121.0), _item("B", 25.1, 121.1)]
    diff = compute_diff(old, new)
    assert diff.added == 1
    assert diff.removed == 0
    assert diff.has_changes is True
    assert "新增 1 筆" in diff.summary


def test_removed_items():
    old = [_item("A", 25.0, 121.0), _item("B", 25.1, 121.1)]
    new = [_item("A", 25.0, 121.0)]
    diff = compute_diff(old, new)
    assert diff.removed == 1
    assert diff.added == 0
    assert "刪除 1 筆" in diff.summary


def test_changed_items():
    # Same name and coordinates, only a field change — should register as changed
    old = [_item("A", 25.0, 121.0, note="old")]
    new = [_item("A", 25.0, 121.0, note="new")]
    diff = compute_diff(old, new)
    assert diff.changed == 1
    assert diff.added == 0
    assert diff.removed == 0
    assert "變更 1 筆" in diff.summary


def test_mixed_changes():
    # A stays (same name/coords) but gets a field change, B is removed, C is added
    old = [_item("A", 25.0, 121.0, note="old"), _item("B", 25.1, 121.1)]
    new = [_item("A", 25.0, 121.0, note="new"), _item("C", 25.2, 121.2)]
    diff = compute_diff(old, new)
    assert diff.added == 1     # C added
    assert diff.removed == 1   # B removed
    assert diff.changed == 1   # A changed
    assert diff.has_changes is True


def test_empty_old_data():
    new = [_item("A", 25.0, 121.0)]
    diff = compute_diff([], new)
    assert diff.added == 1
    assert diff.has_changes is True


def test_empty_both():
    diff = compute_diff([], [])
    assert diff.has_changes is False
