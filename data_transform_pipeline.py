import argparse
import pandas as pd
import numpy as np

STATS_TO_KEEP = [
    "goals", "assists", "pen_min", "shots",
    "blocks", "hits", "takeaways", "giveaways"
]

def transform_pipeline(df: pd.DataFrame, min_toi: int = 400) -> pd.DataFrame:
    df = df.copy()

    # 1. filter by minimum TOI per team-season
    df["team_season"] = df["team"] + "_" + df["season"].astype(str)
    df = df[df["toi"] >= min_toi].reset_index(drop=True)

    # 2. per-60 scaling
    per60_cols = []
    for stat in STATS_TO_KEEP:
        col = f"{stat}_per60"
        df[col] = (df[stat] / df["toi"]) * 60
        per60_cols.append(col)

    # 3. % diff from team-season median, with zero-median guard
    pct_diff_cols = []
    for col in per60_cols:
        pct_col = f"{col}_pct_diff"
        medians = df.groupby("team_season")[col].transform("median")
        df[pct_col] = np.where(
            medians == 0,
            0,
            (df[col] - medians) / medians * 100
        )
        pct_diff_cols.append(pct_col)

    # 4. keep only what's needed for modeling
    id_cols = ["player_id", "name", "team", "season", "team_season", "pos", "games", "toi"]
    return df[id_cols + per60_cols + pct_diff_cols]


def main():
    parser = argparse.ArgumentParser(description="Preprocess NHL player stats.")
    parser.add_argument("--input", default="data_raw.csv", help="Path to raw stats CSV")
    parser.add_argument("--output", default="data_transformed.csv", help="Path to save transformed CSV")
    parser.add_argument("--min-toi", type=int, default=400, help="Minimum TOI filter (default: 400)")
    args = parser.parse_args()

    print(f"Loading {args.input}...")
    df = pd.read_csv(args.input)
    print(f"  {len(df)} rows loaded")

    print(f"Transforming (min TOI: {args.min_toi})...")
    transformed = transform_pipeline(df, min_toi=args.min_toi)
    print(f"  {len(transformed)} rows after TOI filter")

    transformed.to_csv(args.output, index=False)
    print(f"Saved to {args.output}")


if __name__ == "__main__":
    main()