import wave

import numpy as np
import pytest

from matrix_lab_nodes._core.wan3.demo import demo_frames
from matrix_lab_nodes._core.wan3.media import MediaError, prepare_audio, prepare_image, prepare_video
from matrix_lab_nodes._core.wan3 import runner


def test_demo_frames_are_deterministic_local_arrays():
    a = demo_frames({"prompt": "quiet harbor", "duration": 4})
    b = demo_frames({"prompt": "quiet harbor", "duration": 4})
    c = demo_frames({"prompt": "busy station", "duration": 4})
    assert a.shape == (8, 64, 64, 3)
    assert a.dtype == np.float32
    assert np.array_equal(a, b)
    assert not np.array_equal(a, c)


def test_image_preparation_preserves_dimensions_and_rejects_batches(tmp_path):
    image = np.zeros((1, 12, 20, 3), dtype=np.float32)
    prepared = prepare_image(image, slot="first", max_bytes=100_000)
    try:
        from PIL import Image
        with Image.open(prepared.path) as decoded:
            assert decoded.size == (20, 12)
            assert decoded.mode == "RGB"
        assert prepared.content_type == "image/png"
        assert prepared.size == prepared.path.stat().st_size
    finally:
        prepared.cleanup()

    with pytest.raises(MediaError, match="batches are not truncated"):
        prepare_image(np.zeros((2, 12, 20, 3), dtype=np.float32), slot="first")


def test_reference_image_batches_flatten_in_socket_then_frame_order_and_keep_sizes():
    from PIL import Image

    first = np.zeros((2, 7, 11, 3), dtype=np.float32)
    first[0, :, :, 0] = 1
    first[1, :, :, 1] = 1
    second = np.zeros((1, 13, 5, 3), dtype=np.float32)
    second[0, :, :, 2] = 1
    resources, prepared, digests = runner._prepare_media(
        {"reference_images": [first, second]}, allow_video_materialization=False,
        operation="Reference to Video", acknowledge_provider_trimming=False,
    )
    try:
        assert len(resources["reference_images"]) == 3
        assert len(digests["reference_images"]) == 3
        observed = []
        for asset in resources["reference_images"]:
            with Image.open(asset.path) as image:
                observed.append((image.size, image.getpixel((0, 0))))
        assert observed == [((11, 7), (255, 0, 0)), ((11, 7), (0, 255, 0)), ((5, 13), (0, 0, 255))]
    finally:
        for asset in prepared:
            asset.cleanup()


def test_reference_image_flattened_count_is_checked_before_any_encoding(monkeypatch):
    encoded = []
    monkeypatch.setattr(runner, "prepare_image", lambda *args, **kwargs: encoded.append(args))
    with pytest.raises(MediaError, match="after flattening"):
        runner._prepare_media(
            {"reference_images": [np.zeros((10, 1, 1, 3), dtype=np.float32), np.zeros((1, 1, 1, 3), dtype=np.float32)]},
            allow_video_materialization=False, operation="Reference to Video", acknowledge_provider_trimming=False,
        )
    assert encoded == []


@pytest.mark.parametrize("bad", [np.full((1, 2, 2, 3), np.nan), np.full((1, 2, 2, 3), 1.1)])
def test_image_preparation_refuses_nonfinite_or_out_of_range_pixels(bad):
    with pytest.raises(MediaError):
        prepare_image(bad, slot="reference")


def test_audio_wav_keeps_stereo_and_sample_rate(tmp_path):
    waveform = np.zeros((1, 2, 480), dtype=np.float32)
    audio = prepare_audio({"waveform": waveform, "sample_rate": 48_000}, slot="reference")
    try:
        with wave.open(str(audio.path), "rb") as reader:
            assert reader.getnchannels() == 2
            assert reader.getframerate() == 48_000
            assert reader.getnframes() == 480
        assert audio.duration == pytest.approx(0.01)
    finally:
        audio.cleanup()


def test_native_video_requires_explicit_materialization_consent_before_any_work():
    class Video:
        def save_to(self, path):
            raise AssertionError("save_to must not run before consent")

        def get_active_trim_window(self):
            return 0, 0

    with pytest.raises(MediaError, match="explicit video-materialization"):
        prepare_video(Video(), slot="source", allow_materialization=False)
