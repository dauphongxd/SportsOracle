import os
import requests
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
from core.database import SessionLocal as Session, Match, Bet, MatchDetails
from core.database import Wallet
from core.database import Wallet, Match, Bet

load_dotenv()

HEADERS = {
    'x-rapidapi-key': os.getenv("FOOTBALL_API_KEY"),
    'x-rapidapi-host': "v3.football.api-sports.io"
}


def fetch_match_result(fixture_api_id):
    """
    Fetch the final result of a match from the API.
    Returns: {
        'home_score': 2,
        'away_score': 1,
        'status': 'FT',  # Match finished
        'winner': 'home' | 'away' | 'draw'
    }
    """
    url = f"https://v3.football.api-sports.io/fixtures?id={fixture_api_id}"
    try:
        resp = requests.get(url, headers=HEADERS)
        data = resp.json()
        
        if not data['response']:
            return None
        
        fixture = data['response'][0]
        status = fixture['fixture']['status']['short']
        
        # Check if match is finished (FT, AET, PEN)
        if status not in ['FT', 'AET', 'PEN']:
            return None
        
        home_score = fixture['goals']['home']
        away_score = fixture['goals']['away']
        
        # Determine winner
        if home_score > away_score:
            winner = 'home'
        elif away_score > home_score:
            winner = 'away'
        else:
            winner = 'draw'
        
        return {
            'home_score': home_score,
            'away_score': away_score,
            'status': status,
            'winner': winner
        }
    
    except Exception as e:
        print(f"Error fetching match result: {e}")
        return None


def resolve_bets():
    """
    Checks matches that started > 2 hours ago.
    Fetches results.
    Resolves bets & Updates Wallet.
    """
    # Use UTC now to match standard API times
    now_utc = datetime.utcnow()
    print(f"\n🔄 Running Auto-Resolution Task: {now_utc}")

    session = Session()

    try:
        # 1. Find matches that started at least 2 hours ago (UTC) and are NOT completed
        cutoff_time = now_utc - timedelta(hours=2)

        matches_to_check = session.query(Match).filter(
            Match.is_completed == False,
            Match.date <= cutoff_time
        ).all()

        if not matches_to_check:
            print("   ✅ No pending matches to resolve.")
            return

        # Get Wallet (Safety check: Create if missing)
        wallet = session.query(Wallet).first()
        if not wallet:
            wallet = Wallet(balance=10000.0)
            session.add(wallet)

        for match in matches_to_check:
            print(f"   🔎 Checking Match ID {match.id} (Date: {match.date})...")

            if not match.details: continue
            fixture_api_id = match.details.data.get('api_id')

            # Fetch result from API
            result = fetch_match_result(fixture_api_id)

            # If API returns None (Error) or match isn't FT/AET/PEN, skip it
            if not result:
                print(f"      ⏳ Match not finished yet. Waiting...")
                continue

            # Match is finished! Update DB
            match.is_completed = True
            match.final_score_home = result['home_score']
            match.final_score_away = result['away_score']
            winner = result['winner']  # 'home', 'away', 'draw'

            # Find bets for this match
            pending_bets = session.query(Bet).filter(
                Bet.match_id == match.id,
                Bet.status == 'PENDING'
            ).all()

            if pending_bets:
                print(f"      💰 Resolving {len(pending_bets)} bets for this match...")

            for bet in pending_bets:
                is_win = False

                if bet.bet_type == 'HOME_WIN' and winner == 'home':
                    is_win = True
                elif bet.bet_type == 'AWAY_WIN' and winner == 'away':
                    is_win = True
                elif bet.bet_type == 'DRAW' and winner == 'draw':
                    is_win = True

                if is_win:
                    payout = bet.potential_return
                    wallet.balance += payout
                    bet.status = 'WON'
                    bet.actual_result = f"{result['home_score']}-{result['away_score']}"
                    print(f"         🎉 Bet {bet.id} WON! +${payout:.2f}")
                else:
                    bet.status = 'LOST'
                    bet.actual_result = f"{result['home_score']}-{result['away_score']}"
                    print(f"         ❌ Bet {bet.id} LOST.")

                bet.resolved_at = datetime.utcnow()

            # Commit after every match to save progress
            session.commit()

        print(f"   ✅ Resolution Cycle Complete. Wallet Balance: ${wallet.balance:.2f}")

    except Exception as e:
        print(f"❌ Error in resolution: {e}")
        session.rollback()
    finally:
        session.close()


def start_scheduler():
    """
    Start the background scheduler for auto-resolution.
    Runs every hour to check for matches to resolve.
    """
    scheduler = BackgroundScheduler()
    
    # Run resolution check every hour
    scheduler.add_job(
        resolve_bets,
        'interval',
        hours=1,
        id='auto_resolve_bets',
        name='Auto-resolve bets for finished matches',
        replace_existing=True
    )
    
    # Also run immediately on startup (for testing)
    scheduler.add_job(
        resolve_bets,
        'date',
        run_date=datetime.now() + timedelta(seconds=5),
        id='startup_resolve',
        name='Initial resolution check'
    )
    
    scheduler.start()
    print("✅ Scheduler started - Auto-resolution active")
    
    return scheduler


if __name__ == "__main__":
    # Test the resolution function directly
    print("Testing auto-resolution function...")
    resolve_bets()