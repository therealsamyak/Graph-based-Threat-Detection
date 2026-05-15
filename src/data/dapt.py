"""DAPT2020 flow loading for graph-based detection."""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pandas as pd


REFERENCE_CSV = "enp0s3-monday.pcap_Flow.csv"
DAPT_COLUMNS = [
    "Flow ID",
    "Src IP",
    "Src Port",
    "Dst IP",
    "Dst Port",
    "Protocol",
    "Timestamp",
    "Flow Duration",
    "Total Fwd Packet",
    "Total Bwd packets",
    "Total Length of Fwd Packet",
    "Total Length of Bwd Packet",
    "Activity",
    "Stage",
]


def _reference_columns(csv_dir: Path) -> list[str]:
    return pd.read_csv(csv_dir / REFERENCE_CSV, nrows=0).columns.tolist()


def _read_dapt_csv(path: Path, reference_cols: list[str]) -> pd.DataFrame:
    header = pd.read_csv(path, nrows=0).columns.tolist()
    read_kwargs = {"usecols": DAPT_COLUMNS}
    if header[-2:] == ["Activity", "Stage"]:
        return pd.read_csv(path, **read_kwargs)
    return pd.read_csv(path, names=reference_cols, header=None, **read_kwargs)


def iter_dapt_flows(dapt_dir: str) -> Iterator[dict]:
    """Yield DAPT2020 CICFlowMeter rows normalized to graph flow fields."""
    csv_dir = Path(dapt_dir) / "csv"
    reference_cols = _reference_columns(csv_dir)

    for csv_path in sorted(csv_dir.glob("*.csv")):
        df = _read_dapt_csv(csv_path, reference_cols)
        timestamps = pd.to_datetime(df["Timestamp"], format="%d/%m/%Y %I:%M:%S %p", errors="coerce").astype("int64") / 1_000_000_000
        timestamps = timestamps.where(timestamps > 0, 0.0)

        for i, row in df.iterrows():
            fwd_packets = pd.to_numeric(row["Total Fwd Packet"], errors="coerce")
            bwd_packets = pd.to_numeric(row["Total Bwd packets"], errors="coerce")
            fwd_bytes = pd.to_numeric(row["Total Length of Fwd Packet"], errors="coerce")
            bwd_bytes = pd.to_numeric(row["Total Length of Bwd Packet"], errors="coerce")

            yield {
                "src_comp": str(row["Src IP"]),
                "dst_comp": str(row["Dst IP"]),
                "src_port": row["Src Port"],
                "dst_port": row["Dst Port"],
                "protocol": row["Protocol"],
                "pkt_count": float(pd.Series([fwd_packets, bwd_packets]).fillna(0).sum()),
                "byte_count": float(pd.Series([fwd_bytes, bwd_bytes]).fillna(0).sum()),
                "duration": pd.to_numeric(row["Flow Duration"], errors="coerce"),
                "time": float(timestamps.iloc[i]),
                "activity": str(row["Activity"]),
                "stage": str(row["Stage"]),
            }
