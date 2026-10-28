"""Quality proxies, not accuracy. Optical z uses aligned, rectified RGB depth."""
import math
import numpy as np


def depth_estimate(mask, depth, encoding, k, max_m=20.0):
    if depth.shape != mask.shape:
        raise ValueError('Depth must already be registered to RGB at the same resolution')
    if encoding == '16UC1':
        depth = depth.astype(np.float64) * .001
    elif encoding == '32FC1':
        depth = depth.astype(np.float64)
    else:
        raise ValueError('Expected REP-118 16UC1 millimetres or 32FC1 metres')
    good = mask.astype(bool) & np.isfinite(depth) & (depth > 0) & (depth < max_m)
    if np.count_nonzero(good) < 5:
        return None
    y, x = np.nonzero(good)
    z = float(np.median(depth[good]))
    fx, fy, cx, cy = float(k[0]), float(k[4]), float(k[2]), float(k[5])
    if not all(math.isfinite(v) for v in (fx,fy,cx,cy)) or fx <= 0 or fy <= 0:
        raise ValueError('Invalid camera calibration')
    # Median backprojected samples avoids projecting the centre into a depth hole.
    points = np.column_stack(((x-cx)*depth[good]/fx, (y-cy)*depth[good]/fy, depth[good]))
    point = np.median(points, axis=0)
    return {'z_m': z, 'range_m': float(np.linalg.norm(point)), 'point': point.tolist(),
            'mad_m': float(np.median(np.abs(depth[good]-z))),
            'valid_fraction': float(good.sum()/max(1, mask.astype(bool).sum()))}


class QualityTracker:
    def __init__(self):
        self.previous = {}

    def update(self, key, stamp_ns, mask, detected, depth_m=None):
        prior = self.previous.get(key)
        result = {'mask_iou_proxy': None, 'source_rate_hz': None,
                  'loss_event': False, 'reacquisition_event': False,
                  'depth_delta_m': None, 'time_reset': False}
        if prior:
            old_stamp, old_mask, old_detected, old_depth = prior
            dt = (stamp_ns-old_stamp)*1e-9
            if dt > 0:
                result['source_rate_hz'] = 1/dt
                result['loss_event'] = old_detected and not detected
                result['reacquisition_event'] = not old_detected and detected
                if detected and old_detected and old_mask.shape == mask.shape:
                    union = np.logical_or(mask, old_mask).sum()
                    result['mask_iou_proxy'] = float(np.logical_and(mask, old_mask).sum()/union) if union else None
                if depth_m is not None and old_depth is not None:
                    result['depth_delta_m'] = abs(depth_m-old_depth)
            else:
                result['time_reset'] = True
        self.previous[key] = (stamp_ns, mask.copy().astype(bool), bool(detected), depth_m)
        return result
