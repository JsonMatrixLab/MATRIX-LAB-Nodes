"""Spec-section-11 numeric and media-role acceptance boundaries."""

import pytest

from matrix_lab_nodes._core.wan3.catalog import ContractError, build_payload
from matrix_lab_nodes._core.wan3.journal import TaskJournal
from matrix_lab_nodes._core.wan3.media import MediaError
from matrix_lab_nodes._core.wan3.runner import _prepare_media, execute_live, media_slots


def base_values(**overrides):
    values = {
        "prompt": "A calm scene",
        "resolution": "720p",
        "duration": 5,
        "aspect_ratio": "16:9",
        "enable_audio": True,
        "enable_prompt_expansion": False,
        "seed_mode": "Random",
        "seed": 0,
        "generate_audio": True,
        "edit_duration": "Auto",
    }
    values.update(overrides)
    return values


def text_payload(**overrides):
    return build_payload(
        operation="Text to Video", tier="Standard", values=base_values(**overrides), media={},
    )[1]


@pytest.mark.parametrize(("duration", "accepted"), [(1, False), (2, True), (30, True), (31, False)])
def test_generate_duration_minimum_and_maximum(duration, accepted):
    if accepted:
        assert text_payload(duration=duration)["duration"] == duration
    else:
        with pytest.raises(ContractError, match="Duration"):
            text_payload(duration=duration)


@pytest.mark.parametrize(("duration", "accepted"), [(1, False), (2, True), (15, True), (16, False), ("Auto", True)])
def test_edit_output_duration_boundary_and_auto_omission(duration, accepted):
    values = base_values(edit_duration=duration)
    if accepted:
        _, payload = build_payload(operation="Edit Video", tier="Standard", values=values, media={"video": "source"})
        if duration == "Auto":
            assert "duration" not in payload
        else:
            assert payload["duration"] == duration
    else:
        with pytest.raises(ContractError, match="Edit duration"):
            build_payload(operation="Edit Video", tier="Standard", values=values, media={"video": "source"})


@pytest.mark.parametrize("duration", [True, False, 2.0, 5.5, float("nan")])
def test_generate_duration_rejects_boolean_float_and_nan(duration):
    with pytest.raises(ContractError, match="Duration"):
        text_payload(duration=duration)


@pytest.mark.parametrize("duration", [True, 2.0, 2.5, float("nan")])
def test_edit_duration_rejects_boolean_float_and_nan(duration):
    with pytest.raises(ContractError, match="Edit duration"):
        build_payload(operation="Edit Video", tier="Standard", values=base_values(edit_duration=duration), media={"video": "source"})


@pytest.mark.parametrize("resolution", ["360p", "4K", "", None])
def test_unsupported_resolution_is_rejected(resolution):
    with pytest.raises(ContractError, match="Resolution"):
        text_payload(resolution=resolution)


@pytest.mark.parametrize("aspect", ["Auto", "2:1", "", None, 16 / 9])
def test_aspect_contract_accepts_auto_for_t2v_as_normalized_ratio_and_rejects_unsupported(aspect):
    if aspect == "Auto":
        assert text_payload(aspect_ratio=aspect)["aspect_ratio"] == "16:9"
    else:
        with pytest.raises(ContractError, match="aspect ratios"):
            text_payload(aspect_ratio=aspect)


def test_seed_random_sentinel_and_fixed_integer_edges():
    random_payload = text_payload(seed_mode="Random", seed=-1)
    assert random_payload["seed"] == -1
    assert text_payload(seed_mode="Fixed", seed=0)["seed"] == 0
    assert text_payload(seed_mode="Fixed", seed=2_147_483_647)["seed"] == 2_147_483_647
    for invalid in (-1, -2, 2_147_483_648, 1.5, float("nan"), True, "1"):
        with pytest.raises(ContractError, match="Seed"):
            text_payload(seed_mode="Fixed", seed=invalid)


@pytest.mark.parametrize(
    ("operation", "required_media", "forbidden_media"),
    [
        ("Text to Video", {}, {"image": "img"}),
        ("Image to Video", {"image": "first"}, {"reference_images": ["ref"]}),
        ("Reference to Video", {"reference_images": ["ref"]}, {"video": "source"}),
        ("Edit Video", {"video": "source"}, {"image": "img"}),
        ("Extend Video", {"video": "source"}, {"reference_audios": ["audio"]}),
    ],
)
def test_mode_specific_media_roles_reject_incompatible_connections(operation, required_media, forbidden_media):
    media = {**required_media, **forbidden_media}
    with pytest.raises(ContractError, match="incompatible with this operation"):
        build_payload(operation=operation, tier="Standard", values=base_values(), media=media)


@pytest.mark.parametrize(
    ("field", "maximum", "minimum_media"),
    [
        ("reference_images", 10, {"reference_videos": [], "reference_audios": []}),
        ("reference_videos", 5, {"reference_images": [], "reference_audios": []}),
        ("reference_audios", 5, {"reference_images": [], "reference_videos": []}),
    ],
)
def test_each_reference_type_accepts_exact_maximum_and_rejects_maximum_plus_one(field, maximum, minimum_media):
    accepted = {**minimum_media, field: [f"{field}-{index}" for index in range(maximum)]}
    _, payload = build_payload(operation="Reference to Video", tier="Standard", values=base_values(), media=accepted)
    assert payload[field] == accepted[field]
    rejected = {**minimum_media, field: [f"{field}-{index}" for index in range(maximum + 1)]}
    with pytest.raises(ContractError, match=f"At most {maximum}"):
        build_payload(operation="Reference to Video", tier="Standard", values=base_values(), media=rejected)


def test_references_are_required_and_order_and_optional_slot_gaps_are_preserved():
    with pytest.raises(ContractError, match="at least one"):
        build_payload(operation="Reference to Video", tier="Standard", values=base_values(), media={})
    slots = media_slots(
        operation="Reference to Video", image=None, last_image=None, video=None,
        reference_images=[None, "image-B", None, "image-D", None, "image-F", None, None, None, None],
        reference_videos=[None, "video-B", None, None, None],
        reference_audios=[None, None, "audio-C", None, None],
    )
    _, payload = build_payload(operation="Reference to Video", tier="Standard", values=base_values(), media=slots)
    assert payload["reference_images"] == ["image-B", "image-D", "image-F"]
    assert payload["reference_videos"] == ["video-B"]
    assert payload["reference_audios"] == ["audio-C"]
    _, reversed_payload = build_payload(
        operation="Reference to Video", tier="Standard", values=base_values(),
        media={"reference_images": ["image-F", "image-D", "image-B"]},
    )
    assert reversed_payload["reference_images"] == ["image-F", "image-D", "image-B"]


class FakePreparedVideo:
    def __init__(self, duration, width, height, size=1):
        self.duration, self.width, self.height, self.size = duration, width, height, size
        self.sha256 = "a" * 64
        self.content_type = "video/mp4"
        self.path = None
        self.cleanup_called = False

    def cleanup(self):
        self.cleanup_called = True


def _fake_reference_prep(monkeypatch, specs):
    import matrix_lab_nodes._core.wan3.runner as runner

    prepared = [FakePreparedVideo(*spec) for spec in specs]
    remaining = iter(prepared)
    monkeypatch.setattr(runner, "prepare_video", lambda *_args, **_kwargs: next(remaining))
    return prepared


@pytest.mark.parametrize("operation,duration,reason", [
    ("Edit Video", 0.5, "normalizes subsecond"),
    ("Edit Video", 15.01, "first 15 seconds"),
    ("Extend Video", 120.01, "last 120 seconds"),
])
def test_source_video_adjustment_requires_explicit_consent(monkeypatch, operation, duration, reason):
    blocked = _fake_reference_prep(monkeypatch, [(duration, 240, 240)])
    with pytest.raises(MediaError, match=reason):
        _prepare_media({"video": object()}, allow_video_materialization=True,
                       operation=operation, acknowledge_provider_trimming=False)
    assert blocked[0].cleanup_called
    allowed = _fake_reference_prep(monkeypatch, [(duration, 240, 240)])
    resources, prepared, digests = _prepare_media(
        {"video": object()}, allow_video_materialization=True,
        operation=operation, acknowledge_provider_trimming=True)
    assert resources["video"] is allowed[0]
    assert digests["video"]["duration"] == duration
    for asset in prepared:
        asset.cleanup()


@pytest.mark.parametrize("duration", [1, 15])
def test_reference_video_individual_duration_inclusive_edges(monkeypatch, duration):
    _fake_reference_prep(monkeypatch, [(duration, 240, 240)])
    resources, prepared, digests = _prepare_media(
        {"reference_videos": [object()]}, allow_video_materialization=True,
        operation="Reference to Video", acknowledge_provider_trimming=False,
    )
    assert resources["reference_videos"][0].duration == duration
    assert digests["reference_videos"][0]["duration"] == duration
    for asset in prepared:
        asset.cleanup()


@pytest.mark.parametrize("duration", [0.99, 15.01])
def test_reference_video_individual_duration_outside_edges_refuses(monkeypatch, duration):
    prepared = _fake_reference_prep(monkeypatch, [(duration, 240, 240)])
    with pytest.raises(MediaError, match="1 to 15 seconds"):
        _prepare_media(
            {"reference_videos": [object()]}, allow_video_materialization=True,
            operation="Reference to Video", acknowledge_provider_trimming=False,
        )
    assert prepared[0].cleanup_called


@pytest.mark.parametrize("dimensions", [(240, 240), (4096, 4096), (4096, 512), (512, 4096)])
def test_reference_video_geometry_inclusive_dimensions_and_eight_to_one_edges(monkeypatch, dimensions):
    _fake_reference_prep(monkeypatch, [(1, *dimensions)])
    resources, prepared, _digests = _prepare_media(
        {"reference_videos": [object()]}, allow_video_materialization=True,
        operation="Reference to Video", acknowledge_provider_trimming=False,
    )
    assert (resources["reference_videos"][0].width, resources["reference_videos"][0].height) == dimensions
    for asset in prepared:
        asset.cleanup()


@pytest.mark.parametrize("dimensions", [(239, 240), (4097, 4096), (4096, 511), (511, 4096)])
def test_reference_video_geometry_outside_dimension_or_aspect_boundary_refuses(monkeypatch, dimensions):
    prepared = _fake_reference_prep(monkeypatch, [(1, *dimensions)])
    with pytest.raises(MediaError, match="dimensions|aspect ratio"):
        _prepare_media(
            {"reference_videos": [object()]}, allow_video_materialization=True,
            operation="Reference to Video", acknowledge_provider_trimming=False,
        )
    assert prepared[0].cleanup_called


@pytest.mark.parametrize(("durations", "accepted"), [([15], True), ([7.5, 7.5], True), ([7.5, 7.51], False)])
def test_reference_video_total_duration_15_second_edge(monkeypatch, durations, accepted):
    prepared_assets = _fake_reference_prep(monkeypatch, [(seconds, 240, 240) for seconds in durations])
    media = {"reference_videos": [object() for _ in durations]}
    if accepted:
        resources, prepared, digests = _prepare_media(
            media, allow_video_materialization=True, operation="Reference to Video", acknowledge_provider_trimming=False,
        )
        assert sum(item["duration"] for item in digests["reference_videos"]) == pytest.approx(sum(durations))
        for asset in prepared:
            asset.cleanup()
    else:
        with pytest.raises(MediaError, match="Combined reference video duration"):
            _prepare_media(media, allow_video_materialization=True, operation="Reference to Video", acknowledge_provider_trimming=False)
        assert all(asset.cleanup_called for asset in prepared_assets)


@pytest.mark.parametrize(("durations", "accepted"), [([15], True), ([7.5, 7.5], True), ([7.5, 7.51], False)])
def test_reference_audio_total_duration_15_second_edge(monkeypatch, durations, accepted):
    import matrix_lab_nodes._core.wan3.runner as runner

    prepared_assets = [FakePreparedVideo(seconds, 0, 0) for seconds in durations]
    assets = iter(prepared_assets)
    monkeypatch.setattr(runner, "prepare_audio", lambda *_args, **_kwargs: next(assets))
    if accepted:
        resources, prepared, digests = _prepare_media(
            {"reference_audios": [object() for _ in durations]}, allow_video_materialization=False,
            operation="Reference to Video", acknowledge_provider_trimming=False,
        )
        assert sum(item["duration"] for item in digests["reference_audios"]) == pytest.approx(sum(durations))
        for asset in prepared:
            asset.cleanup()
    else:
        with pytest.raises(MediaError, match="Combined reference audio duration"):
            _prepare_media(
                {"reference_audios": [object() for _ in durations]}, allow_video_materialization=False,
                operation="Reference to Video", acknowledge_provider_trimming=False,
            )
        assert all(asset.cleanup_called for asset in prepared_assets)


class FakeClient:
    def __init__(self):
        self.uploads, self.submits = [], []

    def upload(self, asset, *, account_scope, check_cancelled=None):
        self.uploads.append(asset)
        return f"https://asset.example.test/{len(self.uploads)}"

    def submit(self, model, payload):
        self.submits.append((model, dict(payload)))
        return "boundary-prediction"

    def poll(self, prediction_id):
        return {"status": "completed", "outputs": ["https://cdn.example.test/result.mp4"]}

    def download_result(self, url, destination, *, check_cancelled=None):
        destination.write_bytes(b"boundary-fixture")
        return destination


@pytest.mark.parametrize(("duration", "accepted"), [(15, True), (16, False)])
def test_reference_video_plus_output_duration_30_second_boundary(monkeypatch, tmp_path, duration, accepted):
    import matrix_lab_nodes._core.wan3.runner as runner

    client = FakeClient()
    asset = FakePreparedVideo(15, 240, 240)
    monkeypatch.setattr(runner, "_prepare_media", lambda *_args, **_kwargs: (
        {"reference_videos": [asset]}, [asset],
        {"reference_videos": [{"sha256": "b" * 64, "duration": 15, "width": 240, "height": 240}]},
    ))
    monkeypatch.setattr(runner, "_probe_video", lambda _path: "c" * 64)
    monkeypatch.setattr(runner, "_native_video_from_file", lambda path: path)
    values = {
        "operation": "Reference to Video", "tier": "Standard", "image_variant": "Regular",
        "prompt": "Continue the reference", "resolution": "720p", "duration": duration,
        "aspect_ratio": "16:9", "enable_audio": True, "enable_prompt_expansion": False,
        "seed_mode": "Fixed", "seed": 0, "intent_nonce": f"r2v-boundary-{duration}",
        "allow_video_materialization": True, "acknowledge_provider_trimming": False,
    }
    kwargs = {
        "node_id": "boundary-scope", "values": values,
        "media": {"reference_videos": [object()]}, "api_key": "offline-test-key",
        "client_factory": lambda _key: client, "journal": TaskJournal(tmp_path / f"tasks-{duration}.sqlite3"),
        "user_data_dir": tmp_path / f"user-{duration}", "sleep": lambda _seconds: None,
    }
    if accepted:
        assert execute_live(**kwargs).is_file()
        assert len(client.submits) == 1
    else:
        with pytest.raises(MediaError, match="cannot exceed 30 seconds"):
            execute_live(**kwargs)
        assert client.uploads == []
        assert client.submits == []
