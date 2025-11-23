import os
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
from sqlalchemy.orm import sessionmaker
from core.database import engine, Match, Team, MatchDetails

load_dotenv()

API_KEY = os.getenv("FOOTBALL_API_KEY")
HEADERS = {"x-apisports-key": API_KEY}
Session = sessionmaker(bind=engine)


def get_match_odds(fixture_api_id):
    """
    Fetches pre-match odds for a specific fixture.
    Defaulting to bookmaker 8 (Bet365).
    """
    if not fixture_api_id:
        return None

    url = f"https://v3.football.api-sports.io/odds?fixture={fixture_api_id}&bookmaker=8"

    try:
        resp = requests.get(url, headers=HEADERS)
        data = resp.json()

        if not data['response']:
            return None

        if not data['response'][0]['bookmakers']:
            return None

        odds_data = data['response'][0]['bookmakers'][0]['bets'][0]['values']

        result = {}
        for odd in odds_data:
            if odd['value'] == 'Home':
                result['home_win'] = float(odd['odd'])
            elif odd['value'] == 'Draw':
                result['draw'] = float(odd['odd'])
            elif odd['value'] == 'Away':
                result['away_win'] = float(odd['odd'])

        return result

    except Exception as e:
        print(f"Error fetching odds: {e}")
        return None


def get_or_create_team(team_data, sport_id):
    """
    Ensures team exists in DB with API ID.
    """
    session = Session()
    existing = session.query(Team).filter_by(api_id=team_data['id']).first()

    if existing:
        session.close()
        return existing.id

    new_team = Team(
        sport_id=sport_id,
        name=team_data['name'],
        api_id=team_data['id'],
        logo_url=team_data.get('logo')
    )
    session.add(new_team)
    session.commit()
    session.refresh(new_team)
    team_id = new_team.id
    session.close()
    return team_id


def get_team_form(team_api_id):
    """
    Fetches 2025 Premier League Stats: Rank, Form (W-L-D), Goals.
    """
    if not team_api_id:
        return "No API ID available."

    url = f"https://v3.football.api-sports.io/standings?league=39&season=2025&team={team_api_id}"
    try:
        resp = requests.get(url, headers=HEADERS)
        data = resp.json()

        if not data['response']:
            return "Form data unavailable."

        stats = data['response'][0]['league']['standings'][0][0]
        return (f"Rank #{stats['rank']} | Form: {stats['form']} | "
                f"Goals: {stats['all']['goals']['for']} scored, {stats['all']['goals']['against']} conceded.")
    except Exception as e:
        return f"Error fetching form: {e}"


def get_fixture_injuries(fixture_api_id):
    """
    Fetches official injury list for a match.
    """
    if not fixture_api_id:
        return "No Match ID available."

    url = f"https://v3.football.api-sports.io/injuries?fixture={fixture_api_id}"
    try:
        resp = requests.get(url, headers=HEADERS)
        data = resp.json()

        if not data['response']:
            return "No official injuries reported."

        report = []
        count = 0
        for item in data['response']:
            if count >= 10:  # Max 10 total lines
                break
            report.append(f"- {item['team']['name']}: {item['player']['name']} ({item['player']['reason']})")
            count += 1

        if len(data['response']) > 10:
            report.append(f"... and {len(data['response']) - 10} others.")

        return "\n".join(report)
    except Exception as e:
        return f"Error fetching injuries: {e}"


def get_fixture_predictions(fixture_api_id):
    """
    Fetches API predictions to use as a proxy for xG/comparison stats.
    """
    if not fixture_api_id:
        return "No Match ID available."

    url = f"https://v3.football.api-sports.io/predictions?fixture={fixture_api_id}"
    try:
        resp = requests.get(url, headers=HEADERS)
        data = resp.json()

        if not data['response']:
            return "No API comparison data available."

        pred = data['response'][0]
        comparison = pred.get('comparison', {})

        summary = []
        for key, value in comparison.items():
            if isinstance(value, dict):
                summary.append(f"- {key.capitalize()}: Home {value.get('home')} vs Away {value.get('away')}")

        return "\n".join(summary)
    except Exception as e:
        return f"Error fetching predictions: {e}"


def get_team_last_match_date(team_api_id, current_match_date):
    """
    Finds the date of the last match played by the team BEFORE the current match.
    """
    if not team_api_id:
        return None

    url = f"https://v3.football.api-sports.io/fixtures?team={team_api_id}&last=5&status=FT"
    try:
        resp = requests.get(url, headers=HEADERS)
        data = resp.json()

        if not data['response']:
            return None

        matches = sorted(data['response'], key=lambda x: x['fixture']['date'], reverse=True)

        current_dt = current_match_date
        if isinstance(current_dt, str):
            current_dt = datetime.fromisoformat(current_dt)

        for m in matches:
            match_dt = datetime.fromisoformat(m['fixture']['date'])
            if match_dt.date() < current_dt.date():
                delta = current_dt.date() - match_dt.date()
                return delta.days
        return None
    except Exception as e:
        print(f"Error fetching last match: {e}")
        return None


def get_team_api_id_by_name(team_name):
    """Helper to search API for a team ID."""
    url = f"https://v3.football.api-sports.io/teams?name={team_name}"
    resp = requests.get(url, headers=HEADERS)
    data = resp.json()
    if data['response']:
        return data['response'][0]['team']['id']
    return None


def find_match_between_teams(home_name, away_name):
    """
    Searches for a match between two teams using H2H API.
    Handles session detachment to avoid DetachedInstanceError.
    """
    print(f"🔎 Searching matchup: {home_name} vs {away_name}")

    home_api_id = get_team_api_id_by_name(home_name)
    away_api_id = get_team_api_id_by_name(away_name)

    if not home_api_id: return None, f"Could not find team: {home_name}"
    if not away_api_id: return None, f"Could not find team: {away_name}"

    print(f"   ✅ Found IDs: {home_name} ({home_api_id}) vs {away_name} ({away_api_id})")

    url = f"https://v3.football.api-sports.io/fixtures/headtohead?h2h={home_api_id}-{away_api_id}&next=5"
    resp = requests.get(url, headers=HEADERS)
    data = resp.json()

    if data.get('response'):
        f = data['response'][0]
        match_date = datetime.fromisoformat(f['fixture']['date'])
        scheduled_end = match_date + timedelta(hours=2)
        db_home_id = get_or_create_team(f['teams']['home'], 1)
        db_away_id = get_or_create_team(f['teams']['away'], 1)

        session = Session()
        existing = session.query(Match).filter_by(date=match_date, team_home_id=db_home_id).first()

        if existing:
            # FIX: Access the ID to load it before detaching
            _ = existing.id
            session.expunge(existing)
            session.close()
            return existing, "Match found in DB."

        new_match = Match(
            sport_id=1, date=match_date, tournament=f['league']['name'],
            team_home_id=db_home_id, team_away_id=db_away_id,
            scheduled_end_time=scheduled_end, is_completed=False
        )
        session.add(new_match)
        session.commit()
        session.refresh(new_match)

        match_details = MatchDetails(match_id=new_match.id, data={"api_id": f['fixture']['id']})
        session.add(match_details)
        session.commit()

        # FIX: Access ID and expunge
        _ = new_match.id
        session.expunge(new_match)
        session.close()
        return new_match, "Match found."

    print(f"   ⚠️ H2H returned 0 matches.")
    return None, f"No upcoming match found between {home_name} and {away_name}."


def get_team_style_stats(team_api_id):
    """
    Fetches last 5 matches AND their advanced statistics.
    """
    if not team_api_id:
        return {}

    url = f"https://v3.football.api-sports.io/fixtures?team={team_api_id}&last=5"
    try:
        resp = requests.get(url, headers=HEADERS)
        data = resp.json()

        if not data['response']:
            return {}

        total_poss = 0
        total_shots_og = 0
        total_pass_acc = 0
        goals_for = 0
        goals_against = 0
        clean_sheets = 0
        count = 0
        stats_count = 0

        print(f"   📊 Fetching advanced stats for {team_api_id}...")

        for f in data['response']:
            fixture_id = f['fixture']['id']
            goals_for += f['goals']['home'] if f['teams']['home']['id'] == team_api_id else f['goals']['away']
            goals_against += f['goals']['away'] if f['teams']['home']['id'] == team_api_id else f['goals']['home']

            if (f['teams']['home']['id'] == team_api_id and f['goals']['away'] == 0) or \
                    (f['teams']['away']['id'] == team_api_id and f['goals']['home'] == 0):
                clean_sheets += 1
            count += 1

            try:
                stats_url = f"https://v3.football.api-sports.io/fixtures/statistics?fixture={fixture_id}&team={team_api_id}"
                s_resp = requests.get(stats_url, headers=HEADERS)
                s_data = s_resp.json()

                if s_data['response']:
                    stats = s_data['response'][0]['statistics']
                    poss = next((item['value'] for item in stats if item['type'] == 'Ball Possession'), "0%")
                    shots = next((item['value'] for item in stats if item['type'] == 'Shots on Goal'), 0)
                    passes = next((item['value'] for item in stats if item['type'] == 'Passes %'), "0%")

                    if isinstance(poss, str): poss = float(poss.replace('%', ''))
                    if isinstance(passes, str): passes = float(passes.replace('%', ''))
                    if shots is None: shots = 0

                    total_poss += poss
                    total_shots_og += shots
                    total_pass_acc += passes
                    stats_count += 1
            except Exception:
                pass

        return {
            "goals_scored_last_5": goals_for,
            "goals_conceded_last_5": goals_against,
            "clean_sheets": clean_sheets,
            "avg_goals_per_game": round(goals_for / count, 2) if count else 0,
            "avg_possession": round(total_poss / stats_count, 1) if stats_count else 0,
            "avg_shots_on_goal": round(total_shots_og / stats_count, 1) if stats_count else 0,
            "avg_pass_accuracy": round(total_pass_acc / stats_count, 1) if stats_count else 0
        }
    except Exception as e:
        print(f"Error fetching style stats: {e}")
        return {}


def get_head_to_head_stats(home_api_id, away_api_id):
    """
    Fetches last 5 H2H matches.
    """
    url = f"https://v3.football.api-sports.io/fixtures/headtohead?h2h={home_api_id}-{away_api_id}&last=5"
    try:
        resp = requests.get(url, headers=HEADERS)
        data = resp.json()

        if not data['response']:
            return "No recent H2H history."

        h2h_summary = []
        home_wins = 0
        away_wins = 0
        draws = 0

        for f in data['response']:
            date = f['fixture']['date'].split('T')[0]
            score = f"{f['goals']['home']}-{f['goals']['away']}"
            winner = "Draw"
            if f['teams']['home']['winner']:
                winner = f['teams']['home']['name']
            elif f['teams']['away']['winner']:
                winner = f['teams']['away']['name']

            h2h_summary.append(f"{date}: {f['teams']['home']['name']} {score} {f['teams']['away']['name']} ({winner})")

            if f['teams']['home']['id'] == home_api_id and f['teams']['home']['winner']:
                home_wins += 1
            elif f['teams']['away']['id'] == away_api_id and f['teams']['away']['winner']:
                away_wins += 1
            elif not f['teams']['home']['winner'] and not f['teams']['away']['winner']:
                draws += 1

        summary_text = f"Last 5 Meetings: Home Wins {home_wins}, Away Wins {away_wins}, Draws {draws}.\n"
        summary_text += "\n".join(h2h_summary)
        return summary_text
    except Exception as e:
        print(f"Error fetching H2H: {e}")
        return "Error fetching H2H history."


def get_league_context(team_api_id):
    """Phase 1: League Stakes"""
    url = f"https://v3.football.api-sports.io/standings?league=39&season=2025&team={team_api_id}"
    try:
        resp = requests.get(url, headers=HEADERS)
        data = resp.json()
        if not data['response']: return {"context": "Unknown", "rank": "?"}
        stats = data['response'][0]['league']['standings'][0][0]
        rank = stats['rank']
        context = "Mid-table"
        if rank <= 4:
            context = "Title/UCL Race"
        elif rank >= 17:
            context = "Relegation Battle"
        return {"rank": rank, "context": context}
    except:
        return {"rank": "?", "context": "Unknown"}


def is_derby_match(home_id, away_id):
    """Phase 1: Derby Check"""
    import json
    try:
        file_path = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'rivalries.json')
        if not os.path.exists(file_path): return None
        with open(file_path, 'r') as f:
            rivalries = json.load(f)
        for _, derbies in rivalries.items():
            for derby in derbies:
                if home_id in derby['teams'] and away_id in derby['teams']:
                    return derby
        return None
    except:
        return None


def get_manager_context(team_api_id):
    """Phase 1: Manager"""
    url = f"https://v3.football.api-sports.io/coachs?team={team_api_id}"
    try:
        resp = requests.get(url, headers=HEADERS)
        data = resp.json()
        if not data['response']: return "Unknown"
        name = data['response'][0]['name']
        return f"{name}"
    except:
        return "Unknown"


def get_tactical_formation(fixture_api_id, team_api_id):
    """Phase 3: Formations"""
    if not fixture_api_id: return "Unknown"
    # Try official first
    try:
        url = f"https://v3.football.api-sports.io/fixtures/lineups?fixture={fixture_api_id}"
        resp = requests.get(url, headers=HEADERS)
        data = resp.json()
        if data.get('response'):
            for t in data['response']:
                if t['team']['id'] == team_api_id: return f"{t['formation']} (Confirmed)"
    except:
        pass

    # Fallback to preferred
    try:
        url = f"https://v3.football.api-sports.io/teams/statistics?season=2025&team={team_api_id}&league=39"
        resp = requests.get(url, headers=HEADERS)
        data = resp.json()
        if data.get('response'):
            preferred = max(data['response']['lineups'], key=lambda x: x['played'])
            return f"{preferred['formation']} (Preferred)"
    except:
        pass
    return "Unknown"


def get_deep_team_stats(team_api_id):
    """Phase 4: Deep Stats"""
    if not team_api_id: return {}
    url = f"https://v3.football.api-sports.io/teams/statistics?season=2025&team={team_api_id}&league=39"
    try:
        resp = requests.get(url, headers=HEADERS)
        data = resp.json()
        if not data.get('response'): return {}
        stats = data['response']
        yellows = sum([x['total'] or 0 for x in stats['cards']['yellow'].values()])
        reds = sum([x['total'] or 0 for x in stats['cards']['red'].values()])
        return {
            "clean_sheets": stats['clean_sheet']['total'],
            "failed_to_score": stats['failed_to_score']['total'],
            "penalties_scored": stats['penalty']['scored']['total'],
            "total_yellow_cards": yellows,
            "total_red_cards": reds
        }
    except:
        return {}


def get_key_players(team_api_id):
    """Phase 5: Key Players"""
    if not team_api_id: return "Unknown"
    try:
        url = f"https://v3.football.api-sports.io/players/topscorers?season=2025&team={team_api_id}&league=39"
        r = requests.get(url, headers=HEADERS).json()
        if r.get('response'):
            p = r['response'][0]['player']['name']
            g = r['response'][0]['statistics'][0]['goals']['total']
            return f"{p} ({g} goals)"
    except:
        pass
    return "Unknown"