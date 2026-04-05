"""
Legacy shim module.

為了讓既有 import 不用改：
  from core.flag import run_anomaly_detector
"""

def run_anomaly_detector(*args, **kwargs):
    from core.flagging.flag import run_anomaly_detector as _run

    return _run(*args, **kwargs)
