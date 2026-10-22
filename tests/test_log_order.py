"""Latest must mean chronology, even when filenames share the same second."""

import json

from procurecheck.observability.commands import load_logs


def test_latest_uses_recorded_time_before_random_filename_suffix(tmp_path):
    for suffix, milliseconds in [("zzzz", "100"), ("aaaa", "900")]:
        path = tmp_path / f"20261023-090000-workflow-{suffix}.jsonl"
        path.write_text(json.dumps({
            "kind": "run_started", "run_id": suffix,
            "at": f"2026-10-23T09:00:00.{milliseconds}+00:00",
        }) + "\n", encoding="utf-8")
    assert [log.run_id for log in load_logs(tmp_path)] == ["aaaa", "zzzz"]
    assert [log.run_id for log in load_logs(tmp_path, last=1)] == ["aaaa"]
