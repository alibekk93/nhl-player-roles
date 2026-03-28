import time
import requests
import pandas as pd
from bs4 import BeautifulSoup

# ── constants ────────────────────────────────────────────────────────────────

BASE_URL = "https://www.hockey-reference.com"
SEASONS = [2024, 2025, 2026]
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

# ── pipeline ─────────────────────────────────────────────────────────────────
def run_pipeline(output_path: str = "nhl_player_stats.csv") -> pd.DataFrame:
    all_dfs = []

    # 1. for each season, fetch teams, then fetch player stats for each team
    for season in SEASONS:
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

    # 2. combine and save
    final_df = pd.concat(all_dfs, ignore_index=True)

    # reorder columns so identifiers come first
    id_cols = ["player_id", "name", "team", "season", "pos", "games", "toi"]
    stat_cols = STATS_TO_KEEP
    final_df = final_df[id_cols + stat_cols]

    final_df.to_csv(output_path, index=False)
    print(f"\nSaved {len(final_df)} rows to {output_path}")

    return final_df

if __name__ == "__main__":
    df = run_pipeline()