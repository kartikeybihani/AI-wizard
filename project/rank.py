from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rank scored accounts by tier")
    parser.add_argument("--input", default="data/scored.csv")
    parser.add_argument("--output", default="data/final_ranked.csv")
    parser.add_argument("--review-output", default="data/review_bucket.csv")
    parser.add_argument("--min-followers", type=int, default=5000)
    parser.add_argument("--max-accounts", type=int, default=100)
    parser.add_argument("--top-per-tier", type=int, default=0)
    return parser.parse_args()


def tier_from_followers(followers: int) -> str:
    if followers >= 1_500_000:
        return "major"
    if followers >= 500_000:
        return "macro"
    if followers >= 50_000:
        return "mid"
    if followers >= 5_000:
        return "micro"
    return "nano"


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    review_output_path = Path(args.review_output)

    if not input_path.exists():
        raise FileNotFoundError(f"input file not found: {input_path}")

    df = pd.read_csv(input_path)
    if df.empty:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(output_path, index=False)
        review_output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(review_output_path, index=False)
        print(f"[rank] input was empty, wrote empty output -> {output_path}")
        return

    df["followers"] = pd.to_numeric(df.get("followers"), errors="coerce").fillna(0).astype(int)
    df["final_score"] = pd.to_numeric(df.get("final_score"), errors="coerce").fillna(0.0)
    df["tier"] = df["followers"].apply(tier_from_followers)

    if args.min_followers > 0:
        df = df[df["followers"] >= args.min_followers].copy()

    if "needs_review" in df.columns:
        df["needs_review"] = (
            df["needs_review"]
            .astype(str)
            .str.strip()
            .str.lower()
            .isin(["true", "1", "yes", "y"])
        )
    else:
        df["needs_review"] = False

    if "confidence_score" in df.columns:
        df["confidence_score"] = pd.to_numeric(df["confidence_score"], errors="coerce").fillna(0.0)
    else:
        df["confidence_score"] = 0.0

    if "review_reason" not in df.columns:
        df["review_reason"] = ""

    tier_order_map = {"micro": 0, "mid": 1, "macro": 2, "major": 3, "nano": 4}
    df["tier_order"] = df["tier"].map(tier_order_map).fillna(9).astype(int)

    df = df.sort_values(["tier_order", "final_score"], ascending=[True, False]).reset_index(drop=True)
    df["tier_rank"] = df.groupby("tier").cumcount() + 1

    overall = df.sort_values("final_score", ascending=False).reset_index(drop=True)
    overall["overall_rank"] = overall.index + 1
    df = df.merge(overall[["username", "overall_rank"]], on="username", how="left")

    review_df = (
        df[df["needs_review"]]
        .sort_values(["final_score", "confidence_score"], ascending=[False, True])
        .reset_index(drop=True)
    )

    if args.top_per_tier > 0:
        df = df[df["tier_rank"] <= args.top_per_tier].copy()

    if args.max_accounts > 0 and len(df) > args.max_accounts:
        selected = df.sort_values("final_score", ascending=False).head(args.max_accounts)
        df = selected.sort_values(["tier_order", "final_score"], ascending=[True, False]).copy()

    df = df.drop(columns=["tier_order"], errors="ignore")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    review_output_path.parent.mkdir(parents=True, exist_ok=True)
    review_df.to_csv(review_output_path, index=False)
    print(f"[rank] wrote {len(df)} ranked accounts -> {output_path}")
    print(f"[rank] wrote {len(review_df)} review accounts -> {review_output_path}")


if __name__ == "__main__":
    main()
