"""
Unit tests for AsyncDigestManager.
"""

import tempfile
from pathlib import Path
from swarmgate.digest import AsyncDigestManager
from swarmgate.evaluator import EscalationEvaluator


def test_digest_append_and_filtering():
    with tempfile.TemporaryDirectory() as tmpdir:
        digest_file = Path(tmpdir) / "digest.jsonl"
        mgr = AsyncDigestManager(digest_file=digest_file)

        evaluator = EscalationEvaluator()
        d1 = evaluator.evaluate("file:src/utils/a.py", lines_changed=15)
        d2 = evaluator.evaluate("file:src/utils/b.py", lines_changed=25)

        mgr.record(d1)
        mgr.record(d2)

        entries = mgr.get_entries()
        assert len(entries) == 2
        assert entries[0]["decision_id"] == d1.decision_id
        assert entries[1]["decision_id"] == d2.decision_id

        mgr.clear()
        assert len(mgr.get_entries()) == 0