"""Durable queue aliases prevent a second billable POST while one intent is open."""

from concurrent.futures import ThreadPoolExecutor
import threading

import pytest

from matrix_lab_nodes._core.wan3.journal import TaskJournal


def test_new_queue_resumes_unfinished_intent_and_replay_survives_restart(tmp_path):
    path = tmp_path / "tasks.sqlite3"
    journal = TaskJournal(path)
    assert journal.bind_queue(node_key="scope:node:0", queue_id="p1:0", proposed_nonce="n1") == "n1"
    journal.get_or_create("identity-1", "guard-1", nonce="n1")
    assert journal.claim_submit("identity-1", {"prompt": "one"})
    journal.record_prediction("identity-1", "prediction-1")
    assert journal.bind_queue(node_key="scope:node:0", queue_id="p2:0", proposed_nonce="n2") == "n1"
    assert TaskJournal(path).bind_queue(node_key="scope:node:0", queue_id="p3:0", proposed_nonce="n3") == "n1"
    journal.mark("identity-1", "complete")
    assert journal.bind_queue(node_key="scope:node:0", queue_id="p4:0", proposed_nonce="n4") == "n4"
    assert TaskJournal(path).bind_queue(node_key="scope:node:0", queue_id="p2:0", proposed_nonce="ignored") == "n1"


def test_ambiguous_submit_blocks_later_queue_and_distinct_nodes_stay_independent(tmp_path):
    journal = TaskJournal(tmp_path / "tasks.sqlite3")
    assert journal.bind_queue(node_key="scope:A:0", queue_id="p1:0", proposed_nonce="nA") == "nA"
    journal.get_or_create("identity-A", "guard-A", nonce="nA")
    assert journal.claim_submit("identity-A", {"prompt": "one"})
    journal.mark("identity-A", "indeterminate")
    assert journal.bind_queue(node_key="scope:A:0", queue_id="p2:0", proposed_nonce="nA2") == "nA"
    assert journal.bind_queue(node_key="scope:B:0", queue_id="p1:0", proposed_nonce="nB") == "nB"
    assert journal.bind_queue(node_key="scope:A:1", queue_id="p1:1", proposed_nonce="nA-list") == "nA-list"


@pytest.mark.parametrize("status", ["accepted", "indeterminate"])
def test_legacy_unfinished_nonce_is_adopted_before_new_queue(tmp_path, status):
    journal = TaskJournal(tmp_path / "tasks.sqlite3")
    journal.get_or_create("old-identity", "old-guard", nonce="legacy-uuid")
    assert journal.claim_submit("old-identity", {"prompt": "old"})
    if status == "accepted":
        journal.record_prediction("old-identity", "old-prediction")
    else:
        journal.mark("old-identity", "indeterminate")
    assert journal.bind_queue(node_key="scope:node:0", queue_id="new:0", proposed_nonce="new-uuid",
                              legacy_nonce="legacy-uuid") == "legacy-uuid"
    assert TaskJournal(journal.path).bind_queue(node_key="scope:node:0", queue_id="later:0",
                                                proposed_nonce="later-uuid", legacy_nonce="legacy-uuid") == "legacy-uuid"


def test_concurrent_queues_for_one_node_share_a_single_nonce(tmp_path):
    journal = TaskJournal(tmp_path / "tasks.sqlite3")
    def bind(index):
        return journal.bind_queue(node_key="scope:node:0", queue_id=f"p{index}:0", proposed_nonce=f"n{index}")
    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = pool.map(bind, (1, 2))
    assert first == second


def test_concurrent_first_open_of_fresh_journals_retries_wal_transition(tmp_path):
    with ThreadPoolExecutor(max_workers=4) as pool:
        for round_index in range(16):
            path = tmp_path / f"fresh-{round_index}.sqlite3"
            barrier = threading.Barrier(4)
            def bind(worker):
                barrier.wait(timeout=5)
                return TaskJournal(path).bind_queue(
                    node_key="scope:node:0", queue_id=f"p{worker}:0", proposed_nonce=f"n{worker}")
            assert len(set(pool.map(bind, range(4)))) == 1


def test_new_queue_supersedes_only_prepared_work_before_a_paid_claim(tmp_path):
    journal = TaskJournal(tmp_path / "tasks.sqlite3")
    assert journal.bind_queue(node_key="scope:node:0", queue_id="p1:0", proposed_nonce="n1") == "n1"
    journal.get_or_create("identity-1", "guard-1", nonce="n1")
    assert journal.bind_queue(node_key="scope:node:0", queue_id="p2:0", proposed_nonce="n2") == "n2"
    assert journal.intent("identity-1").status == "failed"
    assert not journal.claim_submit("identity-1", {"prompt": "old"})
    journal.get_or_create("identity-2", "guard-2", nonce="n2")
    assert journal.claim_submit("identity-2", {"prompt": "new"})
    assert journal.bind_queue(node_key="scope:node:0", queue_id="p3:0", proposed_nonce="n3") == "n2"
