from app.k8s_monitor_service import (
    FLINK_WATERMARK_DELAY_MS,
    _coerce_watermark_timestamp,
    _extract_watermark_candidates,
    _watermark_value_out,
)


def test_extract_watermark_candidates_from_flink_payload():
    payload = [
        {"subtask": 0, "value": "1782293122906"},
        {"subtask": 1, "watermark": "-"},
        {"subtask": 2, "lowWatermark": -1},
    ]

    assert _extract_watermark_candidates(payload) == ["1782293122906", "-", -1]


def test_coerce_watermark_timestamp_ignores_abnormal_values():
    assert _coerce_watermark_timestamp("-") is None
    assert _coerce_watermark_timestamp("-1") is None
    assert _coerce_watermark_timestamp(None) is None
    assert _coerce_watermark_timestamp("1,782,293,122,906") == 1782293122906
    assert _coerce_watermark_timestamp(1782293122) == 1782293122000
    assert _coerce_watermark_timestamp(9223372036854775807) is None


def test_watermark_delay_uses_two_hour_threshold():
    now_ms = 1782299999999
    delayed = _watermark_value_out("raw", now_ms - FLINK_WATERMARK_DELAY_MS - 1, now_ms)
    normal = _watermark_value_out("raw", now_ms - FLINK_WATERMARK_DELAY_MS, now_ms)
    future = _watermark_value_out("raw", now_ms + 1000, now_ms)

    assert delayed["delayed"] is True
    assert normal["delayed"] is False
    assert future["lag_ms"] == 0
    assert future["delayed"] is False
