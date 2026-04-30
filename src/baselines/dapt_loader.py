"""DAPT2020 data loader with cleanup for Infinity/NaN handling."""

from pathlib import Path
import pandas as pd
import numpy as np


CACHE_DIR = Path("results/cache")
CACHE_FILE = CACHE_DIR / "dapt2020_clean.parquet"

DAPT_COLUMNS = [
    "Flow ID", "Src IP", "Src Port", "Dst IP", "Dst Port", "Protocol", "Timestamp",
    "Flow Duration", "Total Fwd Packet", "Total Bwd packets",
    "Total Length of Fwd Packet", "Total Length of Bwd Packet",
    "Fwd Packet Length Max", "Fwd Packet Length Min", "Fwd Packet Length Mean", "Fwd Packet Length Std",
    "Bwd Packet Length Max", "Bwd Packet Length Min", "Bwd Packet Length Mean", "Bwd Packet Length Std",
    "Flow Bytes/s", "Flow Packets/s",
    "Flow IAT Mean", "Flow IAT Std", "Flow IAT Max", "Flow IAT Min",
    "Fwd IAT Total", "Fwd IAT Mean", "Fwd IAT Std", "Fwd IAT Max", "Fwd IAT Min",
    "Bwd IAT Total", "Bwd IAT Mean", "Bwd IAT Std", "Bwd IAT Max", "Bwd IAT Min",
    "Fwd PSH Flags", "Bwd PSH Flags", "Fwd URG Flags", "Bwd URG Flags",
    "Fwd Header Length", "Bwd Header Length",
    "Fwd Packets/s", "Bwd Packets/s",
    "Packet Length Min", "Packet Length Max", "Packet Length Mean", "Packet Length Std", "Packet Length Variance",
    "FIN Flag Count", "SYN Flag Count", "RST Flag Count", "PSH Flag Count", "ACK Flag Count",
    "URG Flag Count", "CWR Flag Count", "ECE Flag Count",
    "Down/Up Ratio", "Average Packet Size",
    "Fwd Segment Size Avg", "Bwd Segment Size Avg",
    "Fwd Bytes/Bulk Avg", "Fwd Packet/Bulk Avg", "Fwd Bulk Rate Avg",
    "Bwd Bytes/Bulk Avg", "Bwd Packet/Bulk Avg", "Bwd Bulk Rate Avg",
    "Subflow Fwd Packets", "Subflow Fwd Bytes", "Subflow Bwd Packets", "Subflow Bwd Bytes",
    "FWD Init Win Bytes", "Bwd Init Win Bytes",
    "Fwd Act Data Pkts", "Fwd Seg Size Min",
    "Active Mean", "Active Std", "Active Max", "Active Min",
    "Idle Mean", "Idle Std", "Idle Max", "Idle Min",
    "Activity", "Stage",
]


def _clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Replace Infinity/NaN strings with 0, fill remaining NaN."""
    # Replace string Infinity values with 0
    df = df.replace(["Infinity", "-Infinity", "inf", "-inf"], 0)
    # Replace string NaN values with 0
    df = df.replace(["NaN", "nan"], 0)
    # Convert numeric columns that may have been cast to object type
    for col in df.columns:
        if df[col].dtype == object:
            try:
                df[col] = pd.to_numeric(df[col], errors="ignore")
            except (ValueError, TypeError):
                pass
    # Fill remaining NaN with 0
    df = df.fillna(0)
    return df


def load_dapt2020(data_dir: str, use_cache: bool = True) -> pd.DataFrame:
    """Load and clean all DAPT2020 CSV files.

    Args:
        data_dir: Path to DAPT2020 directory containing csv/ subdirectory.
        use_cache: If True, load from parquet cache if available.

    Returns:
        Cleaned DataFrame with feature columns + Activity + Stage + is_lateral_movement.
    """
    cache_file = Path(data_dir) / "results" / "cache" / "dapt2020_clean.parquet"
    # Fallback to default cache location
    if not cache_file.parent.exists():
        cache_file = CACHE_FILE

    if use_cache and cache_file.exists():
        return pd.read_parquet(cache_file)

    csv_dir = Path(data_dir) / "csv"
    if not csv_dir.exists():
        raise FileNotFoundError(f"DAPT2020 CSV directory not found: {csv_dir}")

    csv_files = sorted(csv_dir.glob("*.csv"))
    if not csv_files:
        raise FileNotFoundError(f"No CSV files found in {csv_dir}")

    dfs = []
    for f in csv_files:
        df = pd.read_csv(f, encoding="ISO-8859-1", low_memory=False)
        if df.columns[0] != "Flow ID":
            df.columns = DAPT_COLUMNS
        df["_source_file"] = f.name
        dfs.append(df)

    combined = pd.concat(dfs, ignore_index=True)

    # Clean Infinity/NaN strings
    combined = _clean_dataframe(combined)

    # Create binary lateral movement label
    combined["is_lateral_movement"] = (
        combined["Stage"]
        .astype(str)
        .str.lower()
        .str.contains("lateral movement")
        .astype(int)
    )

    # Save cache — convert mixed-type columns to string for parquet compat
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    for col in combined.columns:
        if combined[col].dtype == object:
            combined[col] = combined[col].astype(str)
    combined.to_parquet(cache_file, index=False)

    return combined


def get_numeric_features(df: pd.DataFrame) -> list[str]:
    """Return list of numeric CICFlowMeter feature column names."""
    # Exclude identifier and label columns
    exclude = {
        "Flow ID", "Src IP", "Src Port", "Dst IP", "Dst Port",
        "Protocol", "Timestamp", "Activity", "Stage",
        "is_lateral_movement", "_source_file",
    }
    numeric_cols = []
    for col in df.select_dtypes(include=[np.number]).columns:
        if col not in exclude:
            numeric_cols.append(col)
    return numeric_cols
