"""Person detector (T6, ADR-0017): NanoDet-Plus 416 with onnxruntime, on the CPU.

The camera delivers 416x234 BGRx frames (GStreamer does the scaling); here they are
padded to 416x416, normalized, and the model's output is decoded for the person class
only. No OpenCV. Frames live only in memory and are never kept.
"""

import numpy as np

from body.camera import FRAME_H, FRAME_W  # what the camera pipeline delivers

SIDE = 416  # model input
TOP = (SIDE - FRAME_H) // 2  # letterbox padding above the frame
STRIDES = (8, 16, 32)
REG_MAX = 7
PERSON = 0  # COCO class id
# Output names of opencv_zoo's object_detection_nanodet_2022nov.onnx: class scores for
# strides 8/16/32, then box distributions for the same strides.
OUTPUTS = ("792", "814", "836", "795", "817", "839")
MEAN = np.array([103.53, 116.28, 123.675], np.float32)
STD = np.array([57.375, 57.12, 58.395], np.float32)


def anchor_points() -> list[np.ndarray]:
    points = []
    for stride in STRIDES:
        n = SIDE // stride
        ys, xs = np.mgrid[0:n, 0:n]
        points.append(np.column_stack([xs.ravel(), ys.ravel()]) * stride + 0.5 * (stride - 1))
    return points


def nms(boxes: np.ndarray, scores: np.ndarray, iou: float) -> list[int]:
    """Greedy non-maximum suppression on [x1, y1, x2, y2] boxes."""
    area = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
    order, keep = scores.argsort()[::-1], []
    while order.size:
        i, order = int(order[0]), order[1:]
        keep.append(i)
        w = np.minimum(boxes[i, 2], boxes[order, 2]) - np.maximum(boxes[i, 0], boxes[order, 0])
        h = np.minimum(boxes[i, 3], boxes[order, 3]) - np.maximum(boxes[i, 1], boxes[order, 1])
        inter = np.clip(w, 0, None) * np.clip(h, 0, None)
        order = order[inter / (area[i] + area[order] - inter + 1e-9) < iou]
    return keep


def decode(outputs: list[np.ndarray], points: list[np.ndarray], *, threshold: float,
           iou: float = 0.6) -> list[tuple[float, float, float, float, float]]:  # fmt: skip
    """People as (score, x, y, w, h) normalized to the 416x234 frame, best first."""
    boxes, scores = [], []
    for k, (stride, pts) in enumerate(zip(STRIDES, points, strict=True)):
        cls, reg = outputs[k][0], outputs[k + len(STRIDES)][0]
        score = cls[:, PERSON]
        mask = score >= threshold
        if not mask.any():
            continue
        dist = reg[mask].reshape(-1, REG_MAX + 1)
        e = np.exp(dist - dist.max(axis=1, keepdims=True))
        d = ((e / e.sum(axis=1, keepdims=True)) @ np.arange(REG_MAX + 1)).reshape(-1, 4) * stride
        p = pts[mask]
        boxes.append(np.column_stack([p[:, 0] - d[:, 0], p[:, 1] - d[:, 1],
                                      p[:, 0] + d[:, 2], p[:, 1] + d[:, 3]]))  # fmt: skip
        scores.append(score[mask])
    if not boxes:
        return []
    b, s = np.concatenate(boxes), np.concatenate(scores)
    people = []
    for i in nms(b, s, iou):
        x1, x2 = np.clip(b[i, [0, 2]], 0, FRAME_W) / FRAME_W
        y1, y2 = np.clip(b[i, [1, 3]] - TOP, 0, FRAME_H) / FRAME_H
        if x2 > x1 and y2 > y1:  # boxes entirely in the padding are not people
            people.append((float(s[i]), float(x1), float(y1), float(x2 - x1), float(y2 - y1)))
    return people


def preprocess(frame: bytes | bytearray | memoryview, canvas: np.ndarray) -> np.ndarray:
    """A 416x234 BGRx frame into the model's 1x3x416x416 float input (reuses `canvas`)."""
    bgr = np.frombuffer(frame, np.uint8).reshape(FRAME_H, FRAME_W, 4)[:, :, :3]
    canvas[TOP : TOP + FRAME_H] = (bgr - MEAN) / STD
    return np.ascontiguousarray(canvas.transpose(2, 0, 1)[None])


def blank_canvas() -> np.ndarray:
    """Model-space padding: zero after normalization is the dataset mean."""
    return np.zeros((SIDE, SIDE, 3), np.float32)


class PersonDetector:
    def __init__(self, model_path: str, *, threshold: float = 0.35, threads: int = 2):
        import onnxruntime as ort  # only the body needs it

        options = ort.SessionOptions()
        options.intra_op_num_threads, options.inter_op_num_threads = threads, 1
        options.log_severity_level = 3  # the model's harmless initializer warnings
        self._session = ort.InferenceSession(model_path, options,
                                             providers=["CPUExecutionProvider"])  # fmt: skip
        names = {o.name for o in self._session.get_outputs()}
        if not set(OUTPUTS) <= names:
            raise ValueError(f"{model_path} is not the expected NanoDet-Plus 416 model")
        self._input = self._session.get_inputs()[0].name
        self._points = anchor_points()
        self._canvas = blank_canvas()
        self.threshold = threshold

    def detect(self, frame: bytes | bytearray | memoryview):
        blob = preprocess(frame, self._canvas)
        outputs = self._session.run(list(OUTPUTS), {self._input: blob})
        return decode(outputs, self._points, threshold=self.threshold)
