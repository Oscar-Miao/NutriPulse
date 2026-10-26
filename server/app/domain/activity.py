from __future__ import annotations

from datetime import datetime, timezone


def _instant(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except ValueError:
        return None


def overlap_seconds(start_a: str | None, end_a: str | None,
                    start_b: str | None, end_b: str | None) -> float:
    a0, a1, b0, b1 = map(_instant, (start_a, end_a, start_b, end_b))
    if None in (a0, a1, b0, b1) or a1 <= a0 or b1 <= b0:
        return 0.0
    return max(0.0, (min(a1, b1) - max(a0, b0)).total_seconds())


def reconcile_activity(samples: list[dict], workouts: list[dict],
                       resolutions: dict[tuple[str, str], str] | None = None) -> dict:
    """Use actual intervals when complete; otherwise preserve coarse daily-max semantics.

    Unresolved overlap gives the device priority. KEEP_DEVICE excludes its
    conflicting manual session; KEEP_MANUAL wins only in overlapping seconds;
    MERGE_NON_OVERLAPPING keeps device overlap and uncovered manual seconds.
    """
    resolutions = resolutions or {}
    manual_total = sum(float(w["kcal"]) for w in workouts)
    device_total = sum(float(s["value"]) for s in samples)
    if not samples and not workouts:
        return {"kcal": 0.0, "device_kcal": 0.0, "manual_kcal": 0.0,
                "source": "none", "quality": "none"}
    device = []
    manual = []
    for sample in samples:
        start, end = _instant(sample.get("start_at")), _instant(sample.get("end_at"))
        if start is None or end is None or end <= start:
            break
        device.append((sample["id"], start, end,
                       float(sample["value"]) / (end - start).total_seconds()))
    else:
        for workout in workouts:
            start, end = _instant(workout.get("start_at")), _instant(workout.get("end_at"))
            if start is None or end is None or end <= start:
                break
            manual.append((workout["id"], start, end,
                           float(workout["kcal"]) / (end - start).total_seconds()))
        else:
            boundaries = sorted({point for _, start, end, _ in device + manual
                                 for point in (start, end)})
            from_device = from_manual = 0.0
            suppress = {workout_id for (sample_id, workout_id), choice in resolutions.items()
                        if choice == "KEEP_DEVICE"}
            for left, right in zip(boundaries, boundaries[1:]):
                seconds = (right - left).total_seconds()
                active_device = [item for item in device if item[1] < right and item[2] > left]
                active_manual = [item for item in manual if item[0] not in suppress and
                                 item[1] < right and item[2] > left]
                device_rate = max((item[3] for item in active_device), default=0.0)
                manual_rate = max((item[3] for item in active_manual), default=0.0)
                manual_wins = any(resolutions.get((sample[0], workout[0])) == "KEEP_MANUAL"
                                  for sample in active_device for workout in active_manual)
                if manual_wins or not active_device or device_rate <= 0:
                    from_manual += manual_rate * seconds
                else:
                    from_device += device_rate * seconds
            source = "mixed" if from_device and from_manual else "device" if from_device else \
                     "manual" if from_manual else "none"
            return {"kcal": from_device + from_manual,
                    "device_kcal": from_device, "manual_kcal": from_manual,
                    "source": source, "quality": "time_window"}
    source = "device" if device_total >= manual_total and device_total else \
             "manual" if manual_total else "none"
    return {"kcal": max(device_total, manual_total),
            "device_kcal": device_total, "manual_kcal": manual_total,
            "source": source, "quality": "daily_fallback"}
