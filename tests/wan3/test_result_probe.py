import av
import numpy as np

from matrix_lab_nodes._core.wan3.runner import _probe_video


def test_result_probe_accepts_video_with_decodable_audio(tmp_path):
    path = tmp_path / "with-audio.mp4"
    with av.open(str(path), "w") as container:
        video = container.add_stream("libx264", rate=2)
        video.width, video.height, video.pix_fmt = 64, 64, "yuv420p"
        audio = container.add_stream("aac", rate=44100)
        audio.layout = "stereo"
        for _ in range(2):
            frame = av.VideoFrame.from_ndarray(np.zeros((64, 64, 3), dtype=np.uint8), format="rgb24")
            for packet in video.encode(frame):
                container.mux(packet)
        for packet in video.encode():
            container.mux(packet)
        frame = av.AudioFrame.from_ndarray(np.zeros((2, 44100), dtype=np.float32), format="fltp", layout="stereo")
        frame.sample_rate = 44100
        for packet in audio.encode(frame):
            container.mux(packet)
        for packet in audio.encode():
            container.mux(packet)
    assert len(_probe_video(path)) == 64
