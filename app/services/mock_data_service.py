from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple

from .calc_utils import calculate_tdi

SEED_START_TIME = datetime(2026, 3, 15, 9, 0, 0)

SEED_ROWS: List[Tuple[float, float, str]] = [
    (79.8, 80.0, "监控判断设备温度与预测值基本一致，运行状态平稳。"),
    (80.1, 80.0, "监控判断温度轻微上浮，但仍处于正常波动范围。"),
    (79.9, 80.0, "监控判断当前温差收敛，暂无异常征兆。"),
    (80.4, 80.0, "监控判断温度小幅波动，设备负载表现正常。"),
    (80.6, 80.0, "监控判断实际温度略高于预测值，趋势仍可接受。"),
    (80.2, 80.0, "监控判断设备温度稳定，运行状态连续正常。"),
    (79.7, 80.0, "监控判断温度低幅波动，未发现异常扩散迹象。"),
    (80.5, 80.0, "监控判断当前读数平稳，建议继续常规监测。"),
    (80.8, 80.0, "监控判断温差略有抬升，但尚未触发异常阈值。"),
    (81.0, 80.0, "监控判断温度轻微走高，建议保持持续观察。"),
]


def build_seed_records() -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for index, (actual, predicted, analysis) in enumerate(SEED_ROWS, start=1):
        recorded_at = SEED_START_TIME + timedelta(seconds=(index - 1) * 10)
        records.append(
            {
                "sequence": index,
                "recorded_at": recorded_at.strftime("%Y-%m-%d %H:%M:%S"),
                "t_actual": actual,
                "t_predicted": predicted,
                "tdi_value": round(calculate_tdi(actual, predicted), 6),
                "status": "RUNNING",
                "extra_metrics": {
                    "current": round(18.0 + index * 0.1, 2),
                    "vibration": round(0.48 + index * 0.02, 2),
                    "pressure": round(1.22 - index * 0.01, 2),
                },
                "scout_analysis": analysis,
                "source": "seed",
            }
        )
    return records


def append_runtime_record(
    records: List[Dict[str, Any]],
    payload: Dict[str, Any],
    scout_analysis: str,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    next_sequence = int(records[-1]["sequence"]) + 1 if records else 1
    if records:
        last_time = datetime.strptime(records[-1]["recorded_at"], "%Y-%m-%d %H:%M:%S")
    else:
        last_time = SEED_START_TIME - timedelta(seconds=10)
    recorded_at = (last_time + timedelta(seconds=10)).strftime("%Y-%m-%d %H:%M:%S")

    actual = float(payload.get("t_actual", 0.0))
    predicted = float(payload.get("t_predicted", 0.0))
    record = {
        "sequence": next_sequence,
        "recorded_at": recorded_at,
        "t_actual": actual,
        "t_predicted": predicted,
        "tdi_value": round(calculate_tdi(actual, predicted), 6),
        "status": payload.get("status", "RUNNING"),
        "extra_metrics": payload.get("extra_metrics", {}),
        "scout_analysis": scout_analysis,
        "source": "runtime",
    }
    return [*records, record], record
