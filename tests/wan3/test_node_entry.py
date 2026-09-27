"""Offline entry-point/schema checks; these are not a Comfy host test."""

import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace


class Field:
    def __init__(self, kind, id, **options):
        self.kind, self.id, self.options = kind, id, options


class Option:
    def __init__(self, key, inputs):
        self.key, self.inputs = key, inputs


def _io_stub():
    def field_type(kind):
        return SimpleNamespace(Input=lambda id, **options: Field(kind, id, **options), Output=lambda id="output", **options: Field(kind, id, **options))

    def autogrow_input(id, *, template, **options):
        return Field("AUTOGROW", id, template=template, **options)

    def template_names(input, *, names, min):
        return SimpleNamespace(input=input, names=names, min=min)

    def dynamic_input(id, *, options, **kwargs):
        return Field("DYNAMIC_COMBO", id, options=options, **kwargs)

    def schema(**kwargs):
        return SimpleNamespace(**kwargs)

    return SimpleNamespace(
        ComfyNode=object,
        NodeOutput=lambda value: (value,),
        Schema=schema,
        Hidden=SimpleNamespace(unique_id="UNIQUE_ID"),
        DynamicCombo=SimpleNamespace(Input=dynamic_input, Option=Option),
        Autogrow=SimpleNamespace(Input=autogrow_input, TemplateNames=template_names),
        Combo=field_type("COMBO"), String=field_type("STRING"), Int=field_type("INT"),
        Boolean=field_type("BOOLEAN"), Image=field_type("IMAGE"), Video=field_type("VIDEO"),
        Audio=field_type("AUDIO"),
    )


def _load_module(monkeypatch):
    latest = ModuleType("comfy_api.latest")
    latest.io = _io_stub()
    monkeypatch.setitem(sys.modules, "comfy_api", ModuleType("comfy_api"))
    monkeypatch.setitem(sys.modules, "comfy_api.latest", latest)
    path = Path(__file__).parents[2] / "nodes/video_generation/matrix_wan3.py"
    spec = importlib.util.spec_from_file_location("matrix_lab_nodes.nodes.video_generation.matrix_wan3_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "_queue_context", lambda: SimpleNamespace(prompt_id="queue-1", node_id="native-node-42", list_index=0))
    return module


def test_legacy_demo_or_missing_activation_cannot_resolve_key_or_submit(monkeypatch):
    module = _load_module(monkeypatch)
    def forbidden(*_args, **_kwargs):
        raise AssertionError("must fail before key, upload, or submit")
    monkeypatch.setattr(module, "resolve_key", forbidden)
    monkeypatch.setattr(module, "execute_live", forbidden)
    import pytest
    with pytest.raises(module.ContractError, match="Paid generation is blocked"):
      module.MATRIXWan3.execute(
        operation={"operation": "Image to Video", "image": object()},
        tier="Standard", image_variant="Spicy", resolution="720p", duration=5, aspect_ratio="Auto",
        enable_audio=True, generate_audio=True, enable_prompt_expansion=False, seed_mode="Fixed", seed=1,
        edit_duration="Auto", allow_video_materialization=False, acknowledge_provider_trimming=False,
        intent_nonce="fixture-run", credential_scope="fixture-scope")


def test_optional_image_variant_defaults_for_headless_callers(monkeypatch):
    module = _load_module(monkeypatch)
    module.MATRIXWan3.hidden = SimpleNamespace(unique_id="native-node-42")
    monkeypatch.setattr(module, "resolve_key", lambda _scope: ("offline-test-key", "fixture"))
    monkeypatch.setattr(module, "execute_live", lambda **kwargs: kwargs["values"])
    result = module.MATRIXWan3.execute(
        operation={"operation": "Text to Video"}, tier="Standard",
        resolution="720p", duration=5, aspect_ratio="16:9", enable_audio=True,
        generate_audio=True, enable_prompt_expansion=False, seed_mode="Fixed", seed=1,
        edit_duration="Auto", allow_video_materialization=False, acknowledge_provider_trimming=False,
        intent_nonce="fixture-run", credential_scope="fixture-scope", prompt="A short clip", billing_activation="wavespeed_v1")
    assert result[0]["image_variant"] == "Regular"
    assert result[0]["intent_nonce"] != "fixture-run", "saved legacy nonce does not define a new queued run"


def test_fingerprint_uses_queue_node_and_list_index(monkeypatch):
    module = _load_module(monkeypatch)
    assert module.MATRIXWan3.fingerprint_inputs() == ("queue-1", "native-node-42", 0)
    monkeypatch.setattr(module, "_queue_context", lambda: SimpleNamespace(prompt_id="queue-2", node_id="native-node-42", list_index=1))
    assert module.MATRIXWan3.fingerprint_inputs() == ("queue-2", "native-node-42", 1)


def test_dynamic_schema_has_only_operation_specific_native_media_and_ordered_autogrow(monkeypatch):
    module = _load_module(monkeypatch)
    schema = module.MATRIXWan3.define_schema()
    op = next(item for item in schema.inputs if item.id == "operation")
    assert op.kind == "DYNAMIC_COMBO"
    options = {option.key: option.inputs for option in op.options["options"]}

    def fields(mode):
        return {field.id: field for field in options[mode]}

    assert fields("Text to Video") == {}
    assert {name: field.kind for name, field in fields("Image to Video").items()} == {
        "image": "IMAGE", "last_image": "IMAGE",
    }
    assert {name: field.kind for name, field in fields("Reference to Video").items()} == {
        "reference_images": "AUTOGROW", "reference_videos": "AUTOGROW", "reference_audios": "AUTOGROW",
    }
    assert {name: field.kind for name, field in fields("Edit Video").items()} == {
        "video": "VIDEO", "reference_images": "AUTOGROW", "reference_audios": "AUTOGROW",
    }
    assert {name: field.kind for name, field in fields("Extend Video").items()} == {
        "video": "VIDEO", "last_image": "IMAGE",
    }
    for mode in ("Reference to Video", "Edit Video"):
        for group_id, expected in (("reference_images", 10), ("reference_videos", 5), ("reference_audios", 5)):
            group = fields(mode).get(group_id)
            if group is None:
                assert group_id == "reference_videos" and mode == "Edit Video"
                continue
            assert len(group.options["template"].names) == expected
            assert group.options["template"].min == 0
    assert schema.hidden == ["UNIQUE_ID"]
    seed = next(item for item in schema.inputs if item.id == "seed")
    assert (seed.options["default"], seed.options["min"], seed.options["max"]) == (1, 0, 2_147_483_647)
    assert seed.options["control_after_generate"] is False, "Fixed must never inherit native seed-name randomization"


def test_autogrow_slot_mappings_are_flattened_in_numeric_order(monkeypatch):
    module = _load_module(monkeypatch)
    selected = {
        "operation": "Reference to Video",
        "reference_images": {"image_10": "tenth", "image_2": "second", "image_01": "first"},
        "reference_videos": {"video_02": "second video", "video_01": "first video"},
        "reference_audios": {"audio_1": "audio"},
    }
    media = module._operation_media(selected)
    assert media["reference_images"] == ["first", "second", "tenth"]
    assert media["reference_videos"] == ["first video", "second video"]
    assert media["reference_audios"] == ["audio"]


def test_live_identity_comes_from_queued_context(monkeypatch):
    module = _load_module(monkeypatch)
    module.MATRIXWan3.hidden = SimpleNamespace(unique_id="native-node-42")
    monkeypatch.setattr(module, "resolve_key", lambda _scope: ("offline-test-key", "fixture"))
    monkeypatch.setattr(module, "execute_live", lambda **kwargs: kwargs["node_id"])
    result = module.MATRIXWan3.execute(
        operation={"operation": "Text to Video"}, tier="Standard",
        image_variant="Regular", resolution="720p", duration=5, aspect_ratio="16:9",
        enable_audio=True, generate_audio=True, enable_prompt_expansion=False, seed_mode="Fixed", seed=1,
        edit_duration="Auto", allow_video_materialization=False, acknowledge_provider_trimming=False,
        intent_nonce="fixture-run", credential_scope="fixture-scope", prompt="A short clip", billing_activation="wavespeed_v1")
    assert result == ("fixture-scope",)


def test_missing_queue_context_blocks_before_key_lookup(monkeypatch):
    module = _load_module(monkeypatch)
    monkeypatch.setattr(module, "_queue_context", lambda: (_ for _ in ()).throw(module.ContractError("queue context unavailable")))
    monkeypatch.setattr(module, "resolve_key", lambda _scope: (_ for _ in ()).throw(AssertionError("key lookup")))
    import pytest
    with pytest.raises(module.ContractError, match="queue context unavailable"):
        module.MATRIXWan3.execute(
            operation={"operation": "Text to Video"}, tier="Standard", resolution="720p", duration=5,
            aspect_ratio="16:9", enable_audio=True, generate_audio=True, enable_prompt_expansion=False,
            seed_mode="Fixed", seed=1, edit_duration="Auto", allow_video_materialization=False,
            acknowledge_provider_trimming=False, intent_nonce="old", credential_scope="scope",
            prompt="A clip", billing_activation="wavespeed_v1")
