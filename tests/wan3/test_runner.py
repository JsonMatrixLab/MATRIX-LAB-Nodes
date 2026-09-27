import hashlib
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from matrix_lab_nodes._core.wan3.journal import SubmissionUncertain, TaskJournal
from matrix_lab_nodes._core.wan3.runner import execute_live, media_slots
from matrix_lab_nodes._core.wan3.catalog import ROUTES


@pytest.mark.parametrize("status", ["failed", "cancelled", "deleted"])
def test_terminal_outcome_is_durable_and_replay_does_not_poll(monkeypatch, tmp_path, status):
    from matrix_lab_nodes._core.wan3.runner import RunError
    client = FakeClient("test-key")
    _runner, _journal, kwargs = setup_runner(monkeypatch, tmp_path, client)
    polls = []
    def terminal(prediction_id):
        polls.append(prediction_id)
        return {"status": status}
    client.poll = terminal
    for _ in range(2):
        with pytest.raises(RunError):
            execute_live(**kwargs)
    assert polls == ["prediction-1"]
    assert len(client.submits) == 1


@pytest.mark.parametrize("status", ["timeout", "unrecognized", "", None])
def test_unknown_poll_state_retains_prediction_for_resume(monkeypatch, tmp_path, status):
    from matrix_lab_nodes._core.wan3.runner import RunError
    client = FakeClient("test-key")
    _runner, journal, kwargs = setup_runner(monkeypatch, tmp_path, client)
    polls = []
    client.poll = lambda prediction_id: polls.append(prediction_id) or {"status": status}
    for _ in range(2):
        with pytest.raises(RunError, match="prediction ID is retained"):
            execute_live(**kwargs)
    assert polls == ["prediction-1", "prediction-1"]
    assert len(client.submits) == 1
    with sqlite3.connect(journal.path) as con:
        assert con.execute("SELECT status,prediction_id FROM tasks").fetchone() == ("accepted", "prediction-1")


def test_two_runners_finalize_one_accepted_prediction_once(monkeypatch, tmp_path):
    client = FakeClient("test-key")
    _runner, journal, kwargs = setup_runner(monkeypatch, tmp_path, client)
    client.poll = lambda _prediction_id: (_ for _ in ()).throw(InterruptedError("pause after accepted ID"))
    with pytest.raises(InterruptedError):
        execute_live(**kwargs)
    barrier = threading.Barrier(2)
    def completed_together(_prediction_id):
        barrier.wait(timeout=5)
        return {"status": "completed", "outputs": ["https://cdn.example.test/video.mp4"]}
    client.poll = completed_together
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: execute_live(**kwargs), range(2)))
    assert results[0] == results[1]
    assert results[0].read_bytes() == b"fixture-video"
    assert client.downloads == 1
    assert len(client.submits) == 1


def test_two_runners_recover_corrupt_completed_result_once(monkeypatch, tmp_path):
    client = FakeClient("test-key")
    _runner, _journal, kwargs = setup_runner(monkeypatch, tmp_path, client)
    completed = execute_live(**kwargs)
    completed.write_bytes(b"corrupt-local-result")
    barrier = threading.Barrier(2)
    def completed_together(_prediction_id):
        barrier.wait(timeout=5)
        return {"status": "completed", "outputs": ["https://cdn.example.test/video.mp4"]}
    client.poll = completed_together
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: execute_live(**kwargs), range(2)))
    assert results == [completed, completed]
    assert completed.read_bytes() == b"fixture-video"
    assert client.downloads == 2  # initial result and one shared repair
    assert len(client.submits) == 1


def values(prompt="A quiet street"):
    return {
        "operation": "Text to Video", "tier": "Standard", "image_variant": "Regular", "prompt": prompt,
        "resolution": "720p", "duration": 5, "aspect_ratio": "16:9", "enable_audio": True,
        "enable_prompt_expansion": False, "seed_mode": "Random", "edit_duration": "Auto",
        "intent_nonce": "stable-run-uuid", "allow_video_materialization": False,
    }


def no_media():
    return media_slots(operation="Text to Video", image=None, last_image=None, video=None,
                       reference_images=[None] * 10, reference_videos=[None] * 5, reference_audios=[None] * 5)


class FakeClient:
    def __init__(self, key):
        self.key = key
        self.uploads = 0
        self.submits = []
        self.polls = []
        self.downloads = 0
        self.submit_error = None

    def upload(self, media, *, account_scope, check_cancelled=None):
        self.uploads += 1
        return f"https://asset.example.test/{media.sha256}"

    def submit(self, model, payload):
        self.submits.append((model, dict(payload)))
        if self.submit_error:
            raise self.submit_error
        return "prediction-1"

    def poll(self, prediction_id):
        self.polls.append(prediction_id)
        return {"status": "completed", "outputs": ["https://cdn.example.test/video.mp4"]}

    def download_result(self, url, destination, *, check_cancelled=None):
        self.downloads += 1
        destination.write_bytes(b"fixture-video")
        return destination


def setup_runner(monkeypatch, tmp_path, client):
    import matrix_lab_nodes._core.wan3.runner as runner

    monkeypatch.setattr(runner, "_probe_video", lambda path: hashlib.sha256(path.read_bytes()).hexdigest())
    monkeypatch.setattr(runner, "_native_video_from_file", lambda path: path)
    journal = TaskJournal(tmp_path / "tasks.sqlite3")
    kwargs = {
        "node_id": "session-scope", "values": values(), "media": no_media(), "api_key": "sentinel-test-key",
        "journal": journal, "client_factory": lambda _key: client, "user_data_dir": tmp_path,
        "sleep": lambda _seconds: None, "poll_interval": 0, "max_polls": 2,
    }
    return runner, journal, kwargs


@pytest.mark.parametrize("route_key", list(ROUTES))
def test_every_route_reaches_exact_mock_submit_once(monkeypatch, tmp_path, route_key):
    operation, tier, variant = route_key
    route = ROUTES[route_key]
    client = FakeClient("test-key")
    runner, _journal, kwargs = setup_runner(monkeypatch, tmp_path, client)
    selected = values("" if variant == "Spicy" else "A quiet street")
    selected.update(operation=operation, tier=tier, image_variant=variant, seed_mode="Fixed", seed=123,
                    aspect_ratio="Auto" if operation == "Image to Video" else "16:9")
    if operation == "Edit Video" and tier == "Standard":
        selected.update(edit_duration=15, generate_audio=False)
    media = no_media()
    role = {"Image to Video": "image", "Reference to Video": "reference_images",
            "Edit Video": "video", "Extend Video": "video"}.get(operation)
    if role:
        media[role] = [object()] if role == "reference_images" else object()

    class Asset:
        sha256 = "test-digest"
        def cleanup(self):
            pass

    asset = Asset()
    def prepared(source, **_options):
        resources = {role: [asset] if role == "reference_images" else asset} if role else {}
        digests = {role: [{"sha256": asset.sha256}] if role == "reference_images" else {"sha256": asset.sha256}} if role else {}
        return resources, [asset] if role else [], digests

    monkeypatch.setattr(runner, "_prepare_media", prepared)
    monkeypatch.setattr(runner.UploadCache, "get_or_upload", lambda *_args, **_kwargs: "https://asset.example.test/mock")
    kwargs.update(values=selected, media=media)
    result = execute_live(**kwargs)
    assert result.read_bytes() == b"fixture-video"
    assert len(client.submits) == 1
    model, payload = client.submits[0]
    assert model == route.model_id
    assert set(payload) <= route.allowed
    assert route.required <= set(payload)
    omitted = {
        "Text to Video": set(),
        "Image to Video": {"last_image", "aspect_ratio"} | ({"prompt"} if variant == "Spicy" else set()),
        "Reference to Video": {"reference_videos", "reference_audios"},
        "Edit Video": {"reference_images", "reference_audios"} | ({"duration"} if tier == "Prime" else set()),
        "Extend Video": {"last_image"},
    }[operation]
    assert set(payload) == route.allowed - omitted
    assert payload["seed"] == 123
    if operation == "Image to Video":
        assert "aspect_ratio" not in payload
    if operation == "Edit Video":
        assert "enable_audio" not in payload and "generate_audio" in payload
        if tier == "Standard":
            assert payload["duration"] == 15 and payload["generate_audio"] is False
    else:
        assert "generate_audio" not in payload and "enable_audio" in payload
    execute_live(**kwargs)
    assert len(client.submits) == 1


@pytest.mark.parametrize("resolution,aspect,audio,expansion", [
    ("480p", "9:16", False, True),
    ("720p", "1:1", True, False),
    ("1080p", "4:3", False, True),
    ("480p", "3:4", True, False),
    ("1080p", "16:9", False, True),
])
def test_visible_settings_reach_fake_provider(monkeypatch, tmp_path, resolution, aspect, audio, expansion):
    client = FakeClient("test-key")
    _runner, _journal, kwargs = setup_runner(monkeypatch, tmp_path, client)
    selected = values()
    selected.update(resolution=resolution, aspect_ratio=aspect, enable_audio=audio,
                    enable_prompt_expansion=expansion, seed_mode="Fixed", seed=0)
    kwargs["values"] = selected
    execute_live(**kwargs)
    assert len(client.submits) == 1
    model, payload = client.submits[0]
    assert model == "alibaba/wan-3.0/text-to-video"
    assert payload == {"prompt": "A quiet street", "resolution": resolution, "seed": 0,
                       "enable_prompt_expansion": expansion, "duration": 5,
                       "enable_audio": audio, "aspect_ratio": aspect}


def test_shared_live_engine_submits_once_freezes_random_seed_and_reuses_complete_result(monkeypatch, tmp_path):
    client = FakeClient("test-key")
    runner, journal, kwargs = setup_runner(monkeypatch, tmp_path, client)
    first = execute_live(**kwargs)
    record = journal.get_or_create(
        runner.request_identity(route="alibaba/wan-3.0/text-to-video", payload={"prompt": "A quiet street", "resolution": "720p", "seed": -1, "enable_prompt_expansion": False, "duration": 5, "enable_audio": True, "aspect_ratio": "16:9"}, media_digests={"image": None, "last_image": None, "video": None, "reference_images": [], "reference_videos": [], "reference_audios": []}, nonce="stable-run-uuid", scope=runner.credential_scope("test-key")),
        runner.generation_intent(route="alibaba/wan-3.0/text-to-video", payload={"prompt": "A quiet street", "resolution": "720p", "seed": -1, "enable_prompt_expansion": False, "duration": 5, "enable_audio": True, "aspect_ratio": "16:9"}, media_digests={"image": None, "last_image": None, "video": None, "reference_images": [], "reference_videos": [], "reference_audios": []}, nonce="stable-run-uuid"),
    )
    assert first.read_bytes() == b"fixture-video"
    assert len(client.submits) == 1
    sent_payload = client.submits[0][1]
    assert 1 <= sent_payload["seed"] <= 9_999
    assert record.payload_json and '"seed":-1' not in record.payload_json
    assert record.prediction_id == "prediction-1"
    assert record.result_sha256 == hashlib.sha256(b"fixture-video").hexdigest()
    assert record.submission_hash and len(record.submission_hash) == 64  # only a digest is persisted, never the remote URL

    again = execute_live(**kwargs)
    assert again == first
    assert len(client.submits) == 1


@pytest.mark.parametrize("draw, expected", [(0, 1), (9_998, 9_999)])
def test_random_seed_edges_are_frozen_inside_displayed_contract(monkeypatch, tmp_path, draw, expected):
    import secrets
    client = FakeClient("test-key")
    _runner, _journal, kwargs = setup_runner(monkeypatch, tmp_path, client)
    def choose(upper):
        assert upper == 9_999
        return draw
    monkeypatch.setattr(secrets, "randbelow", choose)
    execute_live(**kwargs)
    assert client.submits[0][1]["seed"] == expected


def test_changed_prompt_under_same_nonce_refuses_second_purchase(monkeypatch, tmp_path):
    client = FakeClient("test-key")
    runner, _journal, kwargs = setup_runner(monkeypatch, tmp_path, client)
    execute_live(**kwargs)
    changed = dict(kwargs, values=values("Changed prompt"))
    with pytest.raises(SubmissionUncertain, match="earlier request"):
        execute_live(**changed)
    assert len(client.submits) == 1


def test_credential_rotation_cannot_resubmit_one_intent(monkeypatch, tmp_path):
    first_client = FakeClient("test-key")
    _runner, journal, kwargs = setup_runner(monkeypatch, tmp_path, first_client)
    execute_live(**kwargs)
    second_client = FakeClient("rotated-key")
    changed = dict(kwargs, api_key="rotated-key", client_factory=lambda _key: second_client)
    with pytest.raises(SubmissionUncertain, match="earlier request"):
        execute_live(**changed)
    assert len(first_client.submits) == 1
    assert not second_client.submits


def test_cancel_before_post_sends_nothing(monkeypatch, tmp_path):
    client = FakeClient("test-key")
    _runner, journal, kwargs = setup_runner(monkeypatch, tmp_path, client)
    def stop():
        raise InterruptedError("cancelled before submit")
    with pytest.raises(InterruptedError):
        execute_live(**dict(kwargs, check_cancelled=stop))
    assert not client.submits


def test_cancel_after_accepted_id_retains_it_and_rerun_only_polls(monkeypatch, tmp_path):
    client = FakeClient("test-key")
    runner, journal, kwargs = setup_runner(monkeypatch, tmp_path, client)
    calls = {"count": 0}
    def stop_after_acceptance():
        calls["count"] += 1
        if calls["count"] == 4:
            raise InterruptedError("cancelled while polling")
    with pytest.raises(InterruptedError):
        execute_live(**dict(kwargs, check_cancelled=stop_after_acceptance))
    with journal._connect() as con:
        row = con.execute("SELECT prediction_id FROM tasks WHERE nonce=?", ("stable-run-uuid",)).fetchone()
    assert row == ("prediction-1",)
    assert len(client.submits) == 1
    execute_live(**kwargs)
    assert len(client.submits) == 1


def test_ambiguous_submit_is_persistently_blocked(monkeypatch, tmp_path):
    client = FakeClient("test-key")
    client.submit_error = TimeoutError("lost response")
    _runner, _journal, kwargs = setup_runner(monkeypatch, tmp_path, client)
    with pytest.raises(SubmissionUncertain, match="blocked from retry"):
        execute_live(**kwargs)
    client.submit_error = None
    with pytest.raises(SubmissionUncertain, match="ambiguous"):
        execute_live(**kwargs)
    assert len(client.submits) == 1


def test_distinct_queues_resume_pending_prediction_then_submit_fresh_after_completion(monkeypatch, tmp_path):
    client = FakeClient("test-key")
    _runner, _journal, kwargs = setup_runner(monkeypatch, tmp_path, client)
    first = dict(kwargs, queue_id="prompt-1:0", node_instance="scope:node:0",
                 values=dict(values(), intent_nonce="queue-nonce-1"))
    client.poll = lambda _prediction_id: (_ for _ in ()).throw(InterruptedError("pause after acceptance"))
    with pytest.raises(InterruptedError):
        execute_live(**first)
    second = dict(first, queue_id="prompt-2:0", values=dict(values(), intent_nonce="queue-nonce-2"))
    client.poll = lambda _prediction_id: {"status": "completed", "outputs": ["https://cdn.example.test/video.mp4"]}
    execute_live(**second)
    assert len(client.submits) == 1
    third = dict(first, queue_id="prompt-3:0", values=dict(values(), intent_nonce="queue-nonce-3"))
    execute_live(**third)
    assert len(client.submits) == 2
    execute_live(**second)
    assert len(client.submits) == 2


def test_later_queue_cannot_retry_ambiguous_paid_submit(monkeypatch, tmp_path):
    client = FakeClient("test-key")
    client.submit_error = TimeoutError("lost response")
    _runner, _journal, kwargs = setup_runner(monkeypatch, tmp_path, client)
    first = dict(kwargs, queue_id="prompt-1:0", node_instance="scope:node:0",
                 values=dict(values(), intent_nonce="queue-nonce-1"))
    with pytest.raises(SubmissionUncertain):
        execute_live(**first)
    client.submit_error = None
    second = dict(first, queue_id="prompt-2:0", values=dict(values(), intent_nonce="queue-nonce-2"))
    with pytest.raises(SubmissionUncertain, match="ambiguous"):
        execute_live(**second)
    assert len(client.submits) == 1


def test_later_queue_with_changed_inputs_cannot_split_active_paid_intent(monkeypatch, tmp_path):
    client = FakeClient("test-key")
    _runner, journal, kwargs = setup_runner(monkeypatch, tmp_path, client)
    first = dict(kwargs, queue_id="prompt-1:0", node_instance="scope:node:0",
                 values=dict(values(), intent_nonce="queue-nonce-1"))
    client.poll = lambda _prediction_id: (_ for _ in ()).throw(InterruptedError("pending"))
    with pytest.raises(InterruptedError):
        execute_live(**first)
    changed = dict(first, queue_id="prompt-2:0",
                   values=dict(values("Different scene"), intent_nonce="queue-nonce-2"))
    with pytest.raises(SubmissionUncertain, match="earlier request"):
        execute_live(**changed)
    with journal._connect() as con:
        assert con.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 1
    assert len(client.submits) == 1


def test_new_queue_recovers_from_pre_submit_failure_without_double_post(monkeypatch, tmp_path):
    client = FakeClient("test-key")
    _runner, journal, kwargs = setup_runner(monkeypatch, tmp_path, client)
    first = dict(kwargs, queue_id="prompt-1:0", node_instance="scope:node:0",
                 values=dict(values(), intent_nonce="queue-nonce-1"))
    freeze = journal.freeze_payload
    journal.freeze_payload = lambda *_args: (_ for _ in ()).throw(RuntimeError("local preparation failed"))
    with pytest.raises(RuntimeError, match="local preparation failed"):
        execute_live(**first)
    assert not client.submits
    journal.freeze_payload = freeze
    corrected = dict(first, queue_id="prompt-2:0",
                     values=dict(values("Corrected scene"), intent_nonce="queue-nonce-2"))
    execute_live(**corrected)
    assert len(client.submits) == 1


def test_upgrade_adopts_legacy_accepted_prediction_without_new_post(monkeypatch, tmp_path):
    client = FakeClient("test-key")
    _runner, _journal, kwargs = setup_runner(monkeypatch, tmp_path, client)
    client.poll = lambda _prediction_id: (_ for _ in ()).throw(InterruptedError("old prediction still running"))
    with pytest.raises(InterruptedError):
        execute_live(**kwargs)
    upgraded = dict(kwargs, queue_id="new-prompt:0", node_instance="scope:node:0",
                    legacy_nonce="stable-run-uuid", values=dict(values(), intent_nonce="new-queue-nonce"))
    client.poll = lambda _prediction_id: {"status": "completed", "outputs": ["https://cdn.example.test/video.mp4"]}
    execute_live(**upgraded)
    assert len(client.submits) == 1


def test_upgrade_blocks_legacy_ambiguous_submit(monkeypatch, tmp_path):
    client = FakeClient("test-key")
    client.submit_error = TimeoutError("old ambiguous submit")
    _runner, _journal, kwargs = setup_runner(monkeypatch, tmp_path, client)
    with pytest.raises(SubmissionUncertain):
        execute_live(**kwargs)
    client.submit_error = None
    upgraded = dict(kwargs, queue_id="new-prompt:0", node_instance="scope:node:0",
                    legacy_nonce="stable-run-uuid", values=dict(values(), intent_nonce="new-queue-nonce"))
    with pytest.raises(SubmissionUncertain, match="ambiguous"):
        execute_live(**upgraded)
    assert len(client.submits) == 1


def test_preflight_rejects_incompatible_media_before_any_encoder_runs(monkeypatch, tmp_path):
    client = FakeClient("test-key")
    _runner, _journal, kwargs = setup_runner(monkeypatch, tmp_path, client)
    class InvalidImage:
        def detach(self):
            raise AssertionError("image encoder should not run")
    changed = dict(kwargs, media=dict(kwargs["media"], image=InvalidImage()))
    with pytest.raises(ValueError, match="incompatible"):
        execute_live(**changed)
    assert not client.uploads
    assert not client.submits
