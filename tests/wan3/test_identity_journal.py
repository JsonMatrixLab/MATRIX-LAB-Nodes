from concurrent.futures import ThreadPoolExecutor
import hashlib

import pytest

from matrix_lab_nodes._core.wan3.identity import credential_scope, generation_intent, request_identity
from matrix_lab_nodes._core.wan3.journal import SubmissionUncertain, TaskJournal


def _ids(key):
    args = {"route": "alibaba/wan-3.0/text-to-video", "payload": {"prompt": "demo"}, "media_digests": {}, "nonce": "same-run"}
    return (
        request_identity(**args, scope=credential_scope(key)),
        generation_intent(**args),
    )


def _prepared(journal, identity, guard):
    journal.get_or_create(identity, guard, request={"route": "test", "payload_template": {"prompt": "demo"}}, media={}, nonce="same-run")
    journal.freeze_payload(identity, {"prompt": "demo", "seed": 7})
    journal.freeze_submission(identity, {"prompt": "demo", "seed": 7})


def test_identity_never_contains_raw_credential_and_scope_isolation_is_explicit():
    first, guard1 = _ids("sentinel-secret-A")
    second, guard2 = _ids("sentinel-secret-B")
    assert "sentinel-secret" not in first + second + guard1 + guard2
    assert first != second
    assert guard1 == guard2


def test_only_one_concurrent_worker_can_claim_a_billable_submission(tmp_path):
    journal = TaskJournal(tmp_path / "state" / "tasks.sqlite3")
    identity, guard = _ids("test-key")
    _prepared(journal, identity, guard)
    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(lambda _: journal.claim_submit(identity), range(36)))
    assert results.count(True) == 1
    assert journal.intent(identity).status == "submitting"


def test_uncertain_submission_recovers_id_and_never_grants_a_second_post(tmp_path):
    db = tmp_path / "tasks.sqlite3"
    first = TaskJournal(db)
    identity, guard = _ids("test-key")
    _prepared(first, identity, guard)
    assert first.claim_submit(identity)
    restarted = TaskJournal(db)
    record = restarted.get_or_create(identity, guard)
    assert record.status == "submitting"
    assert not restarted.claim_submit(identity)
    assert record.prediction_id is None  # unknown submit outcome is not permission to send again


def test_credential_rotation_cannot_replay_the_same_generation_nonce(tmp_path):
    journal = TaskJournal(tmp_path / "tasks.sqlite3")
    first_id, guard = _ids("key-A")
    second_id, second_guard = _ids("key-B")
    assert guard == second_guard
    _prepared(journal, first_id, guard)
    first = journal.get_or_create(first_id, guard, request={"route": "test"}, media={}, nonce="same-run")
    assert first.identity == first_id
    assert journal.claim_submit(first_id)
    replay = journal.get_or_create(second_id, second_guard)
    assert replay.identity == first_id
    assert replay.status == "submitting"
    assert replay.identity != second_id  # caller must block before polling or submission
    assert not journal.claim_submit(first_id)


def test_prediction_id_is_immutable_and_survives_restart(tmp_path):
    journal = TaskJournal(tmp_path / "tasks.sqlite3")
    identity, guard = _ids("test-key")
    _prepared(journal, identity, guard)
    assert journal.claim_submit(identity)
    journal.record_prediction(identity, "pred-1")
    with pytest.raises(SubmissionUncertain, match="immutable"):
        journal.record_prediction(identity, "pred-2")
    assert TaskJournal(tmp_path / "tasks.sqlite3").intent(identity).prediction_id == "pred-1"


def test_completed_result_is_durable_and_never_becomes_a_new_submit(tmp_path):
    journal = TaskJournal(tmp_path / "tasks.sqlite3")
    identity, guard = _ids("test-key")
    _prepared(journal, identity, guard)
    assert journal.claim_submit(identity)
    journal.record_prediction(identity, "pred-1")
    journal.mark(identity, "complete", result_path="/tmp/video.mp4")
    recovered = journal.get_or_create(identity, guard)
    assert recovered.status == "complete"
    assert recovered.result_path == "/tmp/video.mp4"
    assert not journal.claim_submit(identity)


def test_stale_runner_cannot_downgrade_completed_or_failed_prediction(tmp_path):
    first = TaskJournal(tmp_path / "tasks.sqlite3")
    stale = TaskJournal(tmp_path / "tasks.sqlite3")
    identity, guard = _ids("test-key")
    _prepared(first, identity, guard)
    assert first.claim_submit(identity)
    first.record_prediction(identity, "pred-1")
    first.mark(identity, "complete", result_path="video.mp4", result_sha256="good-hash")
    stale.mark(identity, "polling")
    stale.mark(identity, "failed", detail="stale response")
    with pytest.raises(SubmissionUncertain):
        stale.record_prediction(identity, "pred-1")
    record = first.intent(identity)
    assert (record.status, record.prediction_id, record.result_sha256) == ("complete", "pred-1", "good-hash")
    first.recover_result(identity)
    assert first.intent(identity).status == "accepted"


def test_winning_claim_atomically_binds_its_own_submission_digest(tmp_path):
    journal = TaskJournal(tmp_path / "tasks.sqlite3")
    identity, guard = _ids("test-key")
    _prepared(journal, identity, guard)
    loser = {"image_url": "https://upload.example/loser"}
    winner = {"image_url": "https://upload.example/winner"}
    journal.freeze_submission(identity, loser)
    assert journal.claim_submit(identity, winner)
    from matrix_lab_nodes._core.wan3.journal import compact_payload
    assert journal.intent(identity).submission_hash == hashlib.sha256(compact_payload(winner).encode()).hexdigest()
    assert not journal.claim_submit(identity, loser)
