from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from core.database import engine, Match, Team, Prediction, MatchOdds, Bet, MatchDetails
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os
import json
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)
Session = sessionmaker(bind=engine)

# --- UPDATED IMPORTS ---
from core.rag.gpt_search import get_team_news_gpt
from core.ingestion.football import (
    get_team_style_stats, get_head_to_head_stats, get_match_odds,
    find_match_between_teams, get_team_form, get_fixture_injuries,
    get_fixture_predictions, get_team_last_match_date,
    get_league_context, get_manager_context, is_derby_match,
    get_tactical_formation, get_deep_team_stats, get_key_players
)
from core.analysis.predictor import calculate_expected_value, calculate_risk_rating, generate_betting_advice
from openai import OpenAI
from core.database import Wallet
from core.scheduler import start_scheduler

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


@app.route('/my-bets')
def my_bets_page():
    return render_template('bets.html')

@app.route('/api/predict', methods=['POST'])
def predict_match():
    data = request.json
    home_name = data.get('home_team')
    away_name = data.get('away_team')

    if not home_name or not away_name:
        return jsonify({"error": "Both home_team and away_team are required"}), 400

    session = Session()

    try:
        # 1. MATCH SETUP
        match, msg = find_match_between_teams(home_name, away_name)
        if not match:
            return jsonify({"error": msg}), 404

        match_id = match.id
        match = session.query(Match).get(match_id)
        home_team = session.query(Team).get(match.team_home_id)
        away_team = session.query(Team).get(match.team_away_id)

        # 2. CHECK CACHE
        existing_pred = session.query(Prediction).filter_by(match_id=match.id).first()
        if existing_pred:
            match_odds = session.query(MatchOdds).filter_by(match_id=match.id).first()
            odds_data = None
            if match_odds:
                odds_data = {
                    "home_win": match_odds.home_win_odds,
                    "draw": match_odds.draw_odds,
                    "away_win": match_odds.away_win_odds
                }

            return jsonify({
                "match_id": match.id,
                "home_team": home_team.name, "away_team": away_team.name,
                "date": match.date.strftime("%Y-%m-%d %H:%M"),
                "home_win_probability": existing_pred.home_win_probability,
                "draw_probability": existing_pred.draw_probability,
                "away_win_probability": existing_pred.away_win_probability,
                "confidence": existing_pred.confidence_score,
                "reasoning": existing_pred.reasoning,
                "risk_rating": existing_pred.risk_rating,
                "betting_advice": existing_pred.betting_advice,
                "odds": odds_data,
                "home_manager": existing_pred.home_manager,
                "away_manager": existing_pred.away_manager,
                "home_context": existing_pred.home_context,
                "away_context": existing_pred.away_context,
                "derby_alert": existing_pred.derby_alert,
                "home_formation": existing_pred.home_formation,
                "away_formation": existing_pred.away_formation,
                "home_key_players": existing_pred.home_key_players,
                "away_key_players": existing_pred.away_key_players,
                "home_deep_stats": existing_pred.home_deep_stats,
                "away_deep_stats": existing_pred.away_deep_stats,
                "cached": True
            })

        # 3. LIVE DATA GATHERING
        print("⚡ Starting 5-Phase Analysis...")

        fixture_api_id = None
        if match.details:
            fixture_api_id = match.details.data.get('api_id')

        # [Odds]
        odds_data = None
        if fixture_api_id:
            odds_data = get_match_odds(fixture_api_id)
            if odds_data:
                existing_odds = session.query(MatchOdds).filter_by(match_id=match.id).first()
                if not existing_odds:
                    match_odds = MatchOdds(match_id=match.id, home_win_odds=odds_data.get('home_win'),
                                           draw_odds=odds_data.get('draw'), away_win_odds=odds_data.get('away_win'))
                    session.add(match_odds)
                    session.commit()

        # [Stats & News]
        home_stats = get_team_style_stats(home_team.api_id)
        away_stats = get_team_style_stats(away_team.api_id)
        h2h_summary = get_head_to_head_stats(home_team.api_id, away_team.api_id)
        home_news = get_team_news_gpt(home_team.name)
        away_news = get_team_news_gpt(away_team.name)

        # [Rest Days]
        h_rest = get_team_last_match_date(home_team.api_id, match.date)
        a_rest = get_team_last_match_date(away_team.api_id, match.date)
        home_rest_days = f"{h_rest} days" if h_rest is not None else "Unknown"
        away_rest_days = f"{a_rest} days" if a_rest is not None else "Unknown"

        # [Context]
        home_context = get_league_context(home_team.api_id)
        away_context = get_league_context(away_team.api_id)
        home_manager = get_manager_context(home_team.api_id)
        away_manager = get_manager_context(away_team.api_id)
        derby_data = is_derby_match(home_team.api_id, away_team.api_id)
        derby_text = f"🔥 DERBY: {derby_data['name']} (Intensity {derby_data['intensity']}/10)" if derby_data else "Standard Match"

        # [Formations]
        home_formation = "Unknown"
        away_formation = "Unknown"
        injuries_report = "None"
        if fixture_api_id:
            home_formation = get_tactical_formation(fixture_api_id, home_team.api_id)
            away_formation = get_tactical_formation(fixture_api_id, away_team.api_id)
            injuries_report = get_fixture_injuries(fixture_api_id)

        # [Deep Stats]
        home_deep = get_deep_team_stats(home_team.api_id)
        away_deep = get_deep_team_stats(away_team.api_id)

        # [Key Players]
        home_players = get_key_players(home_team.api_id)
        away_players = get_key_players(away_team.api_id)

        # 4. AI PROMPT CONSTRUCTION (FIXED: Added JSON instruction)
        system_prompt = """You are "The Coach" - an elite Sports Betting Analyst.

        ### YOUR GOAL
        Analyze the match using the 5-Layer Logic and provide a detailed reasoning breakdown.

        ### THE 5-LAYER LOGIC
        1. **Tactical Matchup**: Analyze Formations (e.g. 4-3-3 vs 3-5-2). Who dominates midfield?
        2. **Key Duels**: Look at Key Players (Top Scorer vs Defense).
        3. **Discipline & Volatility**: Check Deep Stats (Red Cards). High aggression + Derby = Chaos.
        4. **Context**: Motivation (Title vs Relegation) & Manager Pressure.
        5. **Value Analysis**: Compare your calculated probability vs the implied odds.

        ### OUTPUT FORMAT (JSON)
        Return a JSON object. 
        CRITICAL: The "reasoning" field must be a long, formatted string using Markdown to separate the layers.

        Example JSON Structure:
        {
            "home_win_probability": 0.45,
            "draw_probability": 0.30,
            "away_win_probability": 0.25,
            "predicted_outcome": "Home",
            "confidence": 0.75,
            "risk_rating": 6,
            "reasoning": "### 1. Tactical Matchup\n[Detailed analysis of formations...]\n\n### 2. Key Duels & Stats\n[Analysis of players and cards...]\n\n### 3. Context & Psychology\n[Analysis of motivation...]\n\n### 4. The Verdict\n[Final summary of why Home wins...]"
        }
        """

        user_prompt = f"""Match: {home_team.name} vs {away_team.name}
Date: {match.date}

### 1. TACTICS & LINEUPS
[HOME] Formation: {home_formation} | Key Players: {home_players}
[AWAY] Formation: {away_formation} | Key Players: {away_players}

### 2. DEEP METRICS (Discipline & Consistency)
[HOME] Yellows: {home_deep.get('total_yellow_cards', 0)} | Reds: {home_deep.get('total_red_cards', 0)} | Clean Sheets: {home_deep.get('clean_sheets', 0)}
[AWAY] Yellows: {away_deep.get('total_yellow_cards', 0)} | Reds: {away_deep.get('total_red_cards', 0)} | Clean Sheets: {away_deep.get('clean_sheets', 0)}

### 3. CONTEXT & PSYCHOLOGY
Type: {derby_text}
Home Stakes: {home_context.get('context')} | Manager: {home_manager}
Away Stakes: {away_context.get('context')} | Manager: {away_manager}

### 4. STANDARD DATA
Rest: {home_team.name} ({home_rest_days}), {away_team.name} ({away_rest_days})
Injuries: {injuries_report}
News: {home_news} | {away_news}
H2H: {h2h_summary}

Predict the outcome with probabilities, confidence, and risk."""

        # 5. EXECUTE AI
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )

        ai_prediction = json.loads(response.choices[0].message.content)

        # 6. CALCULATE VALUE & SAVE
        prob_home = ai_prediction.get('home_win_probability', 0)
        prob_draw = ai_prediction.get('draw_probability', 0)
        prob_away = ai_prediction.get('away_win_probability', 0)
        confidence = ai_prediction.get('confidence', 0.5)
        ai_risk = ai_prediction.get('risk_rating', 5)
        reasoning = ai_prediction.get('reasoning', '')

        ev_home = ev_draw = ev_away = None
        if odds_data:
            ev_home = calculate_expected_value(prob_home, odds_data.get('home_win'))
            ev_draw = calculate_expected_value(prob_draw, odds_data.get('draw'))
            ev_away = calculate_expected_value(prob_away, odds_data.get('away_win'))

        risk_rating = calculate_risk_rating(confidence, ev_home, ev_away, ev_draw, ai_risk)
        betting_advice = generate_betting_advice(ev_home, ev_away, ev_draw, risk_rating, confidence)

        predicted_winner_id = None
        p_outcome = ai_prediction.get('predicted_outcome', 'Draw')
        if p_outcome == 'Home' or p_outcome == home_team.name:
            predicted_winner_id = match.team_home_id
        elif p_outcome == 'Away' or p_outcome == away_team.name:
            predicted_winner_id = match.team_away_id

        new_pred = Prediction(
            match_id=match.id, predicted_winner_id=predicted_winner_id,
            confidence_score=confidence, reasoning=reasoning,
            home_win_probability=prob_home, away_win_probability=prob_away,
            draw_probability=prob_draw, risk_rating=risk_rating,
            betting_advice=betting_advice, expected_value_home=ev_home,
            expected_value_away=ev_away, expected_value_draw=ev_draw,

            # --- SAVING ALL PHASES ---
            home_manager=home_manager, away_manager=away_manager,
            home_context=home_context.get('context'), away_context=away_context.get('context'),
            derby_alert=derby_text if derby_data else None,
            home_formation=home_formation, away_formation=away_formation,
            home_deep_stats=home_deep, away_deep_stats=away_deep,
            home_key_players=home_players, away_key_players=away_players
        )
        session.add(new_pred)
        session.commit()

        return jsonify({
            "match_id": match.id, "home_team": home_team.name, "away_team": away_team.name,
            "home_logo": home_team.logo_url, "away_logo": away_team.logo_url,
            "date": match.date.strftime("%Y-%m-%d %H:%M"),
            "home_win_probability": prob_home, "draw_probability": prob_draw,
            "away_win_probability": prob_away, "confidence": confidence,
            "reasoning": reasoning, "risk_rating": risk_rating,
            "betting_advice": betting_advice, "ev_home": ev_home, "ev_draw": ev_draw, "ev_away": ev_away,
            "odds": odds_data,
            "home_manager": home_manager, "away_manager": away_manager,
            "home_context": home_context.get('context'), "away_context": away_context.get('context'),
            "derby_alert": derby_text if derby_data else None,
            "home_formation": home_formation, "away_formation": away_formation,
            "home_key_players": home_players, "away_key_players": away_players,
            "home_deep_stats": home_deep, "away_deep_stats": away_deep,
            "cached": False
        })

    except Exception as e:
        session.rollback()
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    finally:
        session.close()


@app.route('/api/bets', methods=['GET'])
def get_bets():
    session = Session()
    bets = session.query(Bet).order_by(Bet.placed_at.desc()).all()
    data = []
    for bet in bets:
        match = session.query(Match).get(bet.match_id)
        home_team = session.query(Team).get(match.team_home_id)
        away_team = session.query(Team).get(match.team_away_id)
        data.append({
            "id": bet.id, "match": f"{home_team.name} vs {away_team.name}",
            "match_date": match.date.strftime("%Y-%m-%d %H:%M"),
            "bet_type": bet.bet_type, "stake": bet.stake_amount,
            "odds": bet.odds, "potential_return": bet.potential_return,
            "status": bet.status, "placed_at": bet.placed_at.strftime("%Y-%m-%d %H:%M"),
            "resolved_at": bet.resolved_at.strftime("%Y-%m-%d %H:%M") if bet.resolved_at else None,
            "actual_result": bet.actual_result
        })
    session.close()
    return jsonify(data)


@app.route('/api/bets', methods=['POST'])
def place_bet():
    data = request.json
    session = Session()
    try:
        match_id = data.get('match_id')
        bet_type = data.get('bet_type')
        stake = float(data.get('stake_amount', 100))
        odds = data.get('odds')

        # 1. Check Wallet
        wallet = session.query(Wallet).first()
        if not wallet:
            wallet = Wallet(balance=10000.0)
            session.add(wallet)

        if wallet.balance < stake:
            return jsonify({"error": f"Insufficient funds. Balance: ${wallet.balance:.2f}"}), 400

        # 2. Deduct Stake
        wallet.balance -= stake

        # 3. Create Bet
        potential_return = stake * odds
        new_bet = Bet(
            match_id=match_id,
            bet_type=bet_type,
            stake_amount=stake,
            odds=odds,
            potential_return=potential_return,
            status="PENDING",
            placed_at=datetime.utcnow()
        )
        session.add(new_bet)
        session.commit()

        return jsonify({
            "message": "Bet placed!",
            "new_balance": wallet.balance
        })
    except Exception as e:
        session.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        session.close()

@app.route('/api/wallet', methods=['GET'])
def get_wallet():
    session = Session()
    wallet = session.query(Wallet).first()
    if not wallet:
        wallet = Wallet()
        session.add(wallet)
        session.commit()
    balance = wallet.balance
    session.close()
    return jsonify({"balance": balance})


@app.route('/api/predictions', methods=['GET'])
def get_predictions():
    session = Session()
    predictions = session.query(Prediction).all()
    data = []
    for p in predictions:
        match = session.query(Match).get(p.match_id)
        home_team = session.query(Team).get(match.team_home_id)
        away_team = session.query(Team).get(match.team_away_id)
        winner_name = "Draw"
        if p.predicted_winner_id:
            winner_team = session.query(Team).get(p.predicted_winner_id)
            winner_name = winner_team.name

        # Fetch odds
        match_odds = session.query(MatchOdds).filter_by(match_id=match.id).first()
        odds_data = None
        if match_odds:
            odds_data = {
                "home_win": match_odds.home_win_odds,
                "draw": match_odds.draw_odds,
                "away_win": match_odds.away_win_odds
            }

        data.append({
            "id": p.id,
            "match_id": match.id,
            "match": f"{home_team.name} vs {away_team.name}",
            "date": match.date.strftime("%Y-%m-%d"),
            "winner": winner_name,
            "confidence": p.confidence_score,
            "reasoning": p.reasoning,
            "draw_probability": p.draw_probability,
            "risk_rating": p.risk_rating,
            "betting_advice": p.betting_advice,
            "home_team": home_team.name,
            "away_team": away_team.name,
            "home_logo": home_team.logo_url,
            "away_logo": away_team.logo_url,
            "home_win_probability": p.home_win_probability,
            "away_win_probability": p.away_win_probability,
            "odds": odds_data,

            # --- ADDING THE MISSING PERSISTED DATA ---
            "home_manager": p.home_manager,
            "away_manager": p.away_manager,
            "home_context": p.home_context,
            "away_context": p.away_context,
            "derby_alert": p.derby_alert,
            "home_formation": p.home_formation,
            "away_formation": p.away_formation,
            "home_key_players": p.home_key_players,
            "away_key_players": p.away_key_players,
            "home_deep_stats": p.home_deep_stats,
            "away_deep_stats": p.away_deep_stats
        })
    session.close()
    return jsonify(data)


@app.route('/api/teams/search', methods=['GET'])
def search_teams():
    query = request.args.get('q', '')
    session = Session()
    teams = session.query(Team).filter(Team.name.ilike(f'%{query}%')).limit(10).all()
    data = [{"id": t.id, "api_id": t.api_id, "name": t.name, "logo_url": t.logo_url} for t in teams]
    session.close()
    return jsonify(data)


@app.route('/')
def home():
    return render_template('index.html')


if __name__ == "__main__":
    app.run(debug=True, port=5000, use_reloader=False)