import argparse
import time
import requests
import pandas as pd
from bs4 import BeautifulSoup

# ── constants ────────────────────────────────────────────────────────────────

BASE_URL = "https://www.hockey-reference.com"
DELAY = 4  # seconds between requests — be polite to hockey-reference

STATS_TO_KEEP = [
    "goals", "assists", "pen_min", "shots",
    "blocks", "hits", "takeaways", "giveaways"
]

# ── helpers ──────────────────────────────────────────────────────────────────

def fetch_html(url: str) -> str:
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.text


def parse_active_teams(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")

    teams = []
    for table_id in ("standings_EAS", "standings_WES"):
        table = soup.find("table", {"id": table_id})
        if not table:
            continue

        for row in table.select("tr.full_table"):
            name_cell = row.find(["th", "td"], {"data-stat": "team_name"})
            if not name_cell:
                continue

            anchor = name_cell.find("a", href=True)
            if not anchor:
                continue

            full_name = anchor.text.strip().rstrip("*")
            abbreviation = anchor["href"].split("/")[2]

            teams.append({"full_name": full_name, "abbreviation": abbreviation})

    return teams


def parse_player_stats(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", {"id": "player_stats"})
    if table is None:
        return []

    players = []
    for row in table.select("tbody tr"):
        pos = row.find("td", {"data-stat": "pos"})
        if not pos or pos.text.strip() == "G":
            continue

        name_cell = row.find("td", {"data-stat": "name_display"})
        player_id = name_cell.get("data-append-csv", "").strip()
        name = name_cell.text.strip()

        games_cell = row.find("td", {"data-stat": "games"})
        games = int(games_cell.text.strip() or 0)

        toi_cell = row.find("td", {"data-stat": "time_on_ice"})
        toi = float(toi_cell.get("csk", 0) or 0)

        stats = {
            "player_id": player_id,
            "name": name,
            "pos": pos.text.strip(),
            "games": games,
            "toi": toi
        }
        for stat in STATS_TO_KEEP:
            cell = row.find("td", {"data-stat": stat})
            stats[stat] = int(cell.text.strip() or 0) if cell else 0

        players.append(stats)

    return players


def resolve_seasons(seasons: list[int], season_range: list[int] | None) -> list[int]:
    """Combine --seasons and --season-range into a single sorted, deduplicated list."""
    result = set(seasons)
    if season_range:
        if len(season_range) != 2:
            raise ValueError("--season-range requires exactly 2 values: START END")
        start, end = season_range
        if start > end:
            raise ValueError(f"--season-range START must be <= END, got {start} {end}")
        result.update(range(start, end + 1))
    return sorted(result)


# ── pipeline ─────────────────────────────────────────────────────────────────

def run_pipeline(
    seasons: list[int],
    output_path: str = "data_raw.csv",
    input_path: str | None = None,
) -> pd.DataFrame:

    # load existing data, drop seasons that will be overwritten
    if input_path:
        try:
            existing_df = pd.read_csv(input_path)
            retained_df = existing_df[~existing_df["season"].isin(seasons)]
            dropped = existing_df["season"].isin(seasons).sum()
            print(f"Loaded {len(existing_df)} rows from {input_path}")
            print(f"  Dropping {dropped} rows for seasons {seasons} (will be re-fetched)")
        except FileNotFoundError:
            print(f"Input file {input_path} not found — starting fresh")
            retained_df = pd.DataFrame()
    else:
        retained_df = pd.DataFrame()

    all_dfs = [retained_df] if not retained_df.empty else []

    for season in seasons:
        print(f"\nFetching teams for {season}...")
        season_html = fetch_html(f"{BASE_URL}/leagues/NHL_{season}.html")
        teams = parse_active_teams(season_html)
        print(f"  Found {len(teams)} teams")
        time.sleep(DELAY)

        for team in teams:
            abbr = team["abbreviation"]
            url = f"{BASE_URL}/teams/{abbr}/{season}.html"
            print(f"  Fetching {abbr} {season}...", end=" ")

            try:
                html = fetch_html(url)
                players = parse_player_stats(html)

                if players:
                    df = pd.DataFrame(players)
                    df["team"] = abbr
                    df["season"] = season
                    all_dfs.append(df)
                    print(f"{len(players)} skaters")
                else:
                    print("no skaters found")

            except requests.HTTPError as e:
                print(f"HTTP error: {e}")

            time.sleep(DELAY)

    final_df = pd.concat(all_dfs, ignore_index=True)

    id_cols = ["player_id", "name", "team", "season", "pos", "games", "toi"]
    final_df = final_df[id_cols + STATS_TO_KEEP]

    final_df.to_csv(output_path, index=False)
    print(f"\nSaved {len(final_df)} rows to {output_path}")

    return final_df


def main():
    parser = argparse.ArgumentParser(
        description="Scrape NHL player stats from hockey-reference.com.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "--seasons", nargs="+", type=int, default=[],
        help="Individual season years to scrape (e.g. --seasons 2024 2026)"
    )
    parser.add_argument(
        "--season-range", nargs=2, type=int, metavar=("START", "END"),
        help="Inclusive range of seasons (e.g. --season-range 2024 2026)"
    )
    parser.add_argument(
        "--output", default="data_raw.csv",
        help="Path to save output CSV (default: data_raw.csv)"
    )
    parser.add_argument(
        "--input", default=None,
        help="Path to existing CSV to update. Seasons being fetched will be overwritten."
    )
    args = parser.parse_args()

    try:
        seasons = resolve_seasons(args.seasons, args.season_range)
    except ValueError as e:
        parser.error(str(e))

    if not seasons:
        parser.error("Provide at least one season via --seasons or --season-range")

    print(f"Seasons: {seasons}")
    print(f"Input:   {args.input or 'none (fresh run)'}")
    print(f"Output:  {args.output}")

    run_pipeline(seasons=seasons, output_path=args.output, input_path=args.input)


if __name__ == "__main__":
    main()