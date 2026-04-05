"""
Legacy shim module.

為了讓既有 import 不用改：
  from core.stitch import run_stitching_logic, aligned_to_stitch_shape
"""

from core.stitching.stitch import (  # noqa: F401
    aligned_to_stitch_shape,
    merge_aligned_segments,
    run_stitching_logic,
)
