from core.stitch import merge_aligned_segments


def _seg(seg_id, start, end, speaker, text):
    return {
        "id": seg_id,
        "start": start,
        "end": end,
        "speaker": speaker,
        "text": text,
    }


def test_merge_same_speaker_within_gap():
    aligned = [
        _seg("s1", 0.0, 1.0, "A", "你好"),
        _seg("s2", 2.4, 3.0, "A", "世界"),
    ]

    merged = merge_aligned_segments(aligned, max_gap_sec=1.5)

    assert len(merged) == 1
    assert merged[0]["start"] == 0.0
    assert merged[0]["end"] == 3.0
    assert merged[0]["speaker"] == "A"
    assert merged[0]["text"] == "你好世界"
    assert merged[0]["source_ids"] == ["s1", "s2"]


def test_not_merge_when_gap_exceeds_threshold():
    aligned = [
        _seg("s1", 0.0, 1.0, "A", "甲"),
        _seg("s2", 2.6, 3.0, "A", "乙"),
    ]

    merged = merge_aligned_segments(aligned, max_gap_sec=1.5)

    assert len(merged) == 2
    assert merged[0]["source_ids"] == ["s1"]
    assert merged[1]["source_ids"] == ["s2"]


def test_not_merge_when_speaker_changes():
    aligned = [
        _seg("s1", 0.0, 1.0, "A", "早"),
        _seg("s2", 1.1, 2.0, "B", "安"),
    ]

    merged = merge_aligned_segments(aligned, max_gap_sec=1.5)

    assert len(merged) == 2
    assert merged[0]["speaker"] == "A"
    assert merged[1]["speaker"] == "B"


def test_merge_when_overlap_gap_is_negative():
    aligned = [
        _seg("s1", 0.0, 2.0, "A", "前"),
        _seg("s2", 1.8, 3.0, "A", "後"),
    ]

    merged = merge_aligned_segments(aligned, max_gap_sec=1.5)

    assert len(merged) == 1
    assert merged[0]["text"] == "前後"
    assert merged[0]["source_ids"] == ["s1", "s2"]


def test_source_ids_and_text_have_full_retention():
    aligned = [
        _seg("a1", 0.0, 1.0, "A", "這"),
        _seg("a2", 1.2, 2.0, "A", "是"),
        _seg("b1", 3.8, 4.3, "B", "測"),
        _seg("b2", 4.4, 4.9, "B", "試"),
    ]

    merged = merge_aligned_segments(aligned, max_gap_sec=1.5)

    flattened_ids = [sid for row in merged for sid in row["source_ids"]]
    input_ids = [str(row["id"]) for row in aligned]
    assert flattened_ids == input_ids

    input_text = "".join(row.get("text") or "" for row in aligned)
    merged_text = "".join(row.get("text") or "" for row in merged)
    assert merged_text == input_text


def test_custom_max_gap_changes_behavior():
    aligned = [
        _seg("s1", 0.0, 1.0, "A", "哈"),
        _seg("s2", 2.0, 3.0, "A", "囉"),
    ]

    merged_default = merge_aligned_segments(aligned, max_gap_sec=1.5)
    merged_strict = merge_aligned_segments(aligned, max_gap_sec=0.5)

    assert len(merged_default) == 1
    assert len(merged_strict) == 2
