import os
import json
from openai import OpenAI
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
from core.database import engine, Match, MatchDetails, Team, Prediction, MatchOdds

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
Session = sessionmaker(bind=engine)
session = Session()

# Import Data Gatherers
from core.rag.gpt_search import get_team_news_gpt
from core.ingestion.football import (
    get_team_style_stats,
    get_head_to_head_stats,
    get_match_odds,
    get_team_form,
    get_fixture_injuries,
    get_fixture_predictions,
    get_team_last_match_date,
    get_league_context,
    get_manager_context,
    is_derby_match
)


def calculate_expected_value(ai_probability, bookmaker_odds):
    """
    Calculate Expected Value (EV) for a bet.
    EV = (Probability of Winning * Amount Won per Bet) - (Probability of Losing * Amount Lost per Bet)
    
    For a $100 bet:
    EV = (ai_prob * (odds * 100 - 100)) - ((1 - ai_prob) * 100)
    
    Positive EV = Good bet
    Negative EV = Bad bet
    """
    if not bookmaker_odds or bookmaker_odds <= 1.0:
        return None
    
    stake = 100
    potential_profit = (bookmaker_odds * stake) - stake
    expected_return = (ai_probability * potential_profit) - ((1 - ai_probability) * stake)
    
    return round(expected_return, 2)


def calculate_risk_rating(confidence, ev_home=None, ev_away=None, ev_draw=None, ai_risk=None):
    """
    Calculate risk rating on 1-10 scale.
    If AI provides a risk rating, use it as a baseline but sanity check it.
    """
    # Use AI's risk assessment if available
    if ai_risk is not None:
        base_risk = ai_risk
    else:
        # Fallback to confidence-based rating
        if confidence >= 0.8:
            base_risk = 2
        elif confidence >= 0.7:
            base_risk = 4
        elif confidence >= 0.6:
            base_risk = 6
        elif confidence >= 0.5:
            base_risk = 7
        else:
            base_risk = 9
    
    # Adjust for EV (Math check)
    positive_evs = sum([1 for ev in [ev_home, ev_away, ev_draw] if ev and ev > 0])
    
    if positive_evs == 0:
        # No positive EV = higher risk (betting against math)
        base_risk = min(10, base_risk + 2)
    elif positive_evs > 1:
        # Multiple positive EVs = market confusion = higher risk
        base_risk = min(10, base_risk + 1)
    
    return max(1, min(10, base_risk))


def generate_betting_advice(ev_home, ev_away, ev_draw, risk_rating, confidence):
    """
    Generate human-readable betting advice based on mathematical analysis.
    """
    # Find best EV
    evs = {
        'Home Win': ev_home or -999,
        'Draw': ev_draw or -999,
        'Away Win': ev_away or -999
    }
    
    best_outcome = max(evs, key=evs.get)
    best_ev = evs[best_outcome]
    
    if best_ev <= 0:
        return "💡 **AI Recommendation**: \n⚠️ **No Value Detected**: All outcomes have negative expected value. Bookmaker odds suggest the market is efficient. Not recommended to bet."
    
    if risk_rating <= 3 and best_ev > 5:
        return f"💡 **AI Recommendation**: \n✅ **Strong Bet**: {best_outcome} shows excellent value (EV: ${best_ev:.2f}). High confidence ({confidence:.0%}) with low risk. This is a mathematically sound bet."
    
    if risk_rating <= 5 and best_ev > 0:
        return f"💡 **AI Recommendation**: \n⚡ **Moderate Value**: {best_outcome} has positive expected value (EV: ${best_ev:.2f}), but moderate risk (Rating: {risk_rating}/10). Consider smaller stake."
    
    if best_ev > 0:
        return f"💡 **AI Recommendation**: \n⚠️ **High Risk Bet**: While {best_outcome} has positive EV (${best_ev:.2f}), the risk rating is {risk_rating}/10. Only bet if you can afford volatility."
    
    return "💡 **AI Recommendation**: \n❌ **Skip This Match**: No clear value identified. Consider waiting for better opportunities."


def predict_upcoming_matches():
    print("🤖 AI Sports Oracle - Betting Analysis Engine")
    print("=" * 60)

    # 1. Find Upcoming Matches
    upcoming_matches = session.query(Match).filter(Match.is_completed == False).all()

    if not upcoming_matches:
        print("No upcoming matches found in DB. Run ingestion first!")
        return

    for match in upcoming_matches:
        # Get Team Objects
        home_team = session.query(Team).filter_by(id=match.team_home_id).first()
        away_team = session.query(Team).filter_by(id=match.team_away_id).first()

        print(f"\n{'='*60}")
        print(f"🏟️  {home_team.name} vs {away_team.name}")
        print(f"📅 {match.date.strftime('%Y-%m-%d %H:%M')}")
        print(f"{'='*60}")

        # Check if prediction already exists
        existing_pred = session.query(Prediction).filter_by(match_id=match.id).first()
        if existing_pred:
            print(f"✅ Prediction already exists. Skipping.")
            continue

        # 2. Fetch Odds
        fixture_api_id = None
        if match.details:
            fixture_api_id = match.details.data.get('api_id')
        
        odds_data = None
        if fixture_api_id:
            print(f"📊 Fetching bookmaker odds...")
            odds_data = get_match_odds(fixture_api_id)
            
            if odds_data:
                print(f"   Home Win: {odds_data.get('home_win', 'N/A')}")
                print(f"   Draw: {odds_data.get('draw', 'N/A')}")
                print(f"   Away Win: {odds_data.get('away_win', 'N/A')}")
                
                # Save odds to database
                existing_odds = session.query(MatchOdds).filter_by(match_id=match.id).first()
                if not existing_odds:
                    match_odds = MatchOdds(
                        match_id=match.id,
                        home_win_odds=odds_data.get('home_win'),
                        draw_odds=odds_data.get('draw'),
                        away_win_odds=odds_data.get('away_win')
                    )
                    session.add(match_odds)
                    session.commit()
            else:
                print("   ⚠️ No odds available for this match")

        # 3. Gather Data
        print(f"🔍 Gathering tactical & contextual data...")
        # Basic Stats
        home_stats = get_team_style_stats(home_team.api_id)
        away_stats = get_team_style_stats(away_team.api_id)
        h2h_summary = get_head_to_head_stats(home_team.api_id, away_team.api_id)

        # GPT News Search
        home_news = get_team_news_gpt(home_team.name)
        away_news = get_team_news_gpt(away_team.name)

        # Contextual Data (Layer 5)
        home_context = get_league_context(home_team.api_id)
        away_context = get_league_context(away_team.api_id)
        home_manager = get_manager_context(home_team.api_id)
        away_manager = get_manager_context(away_team.api_id)

        derby_data = is_derby_match(home_team.api_id, away_team.api_id)
        derby_text = "Regular Match"
        if derby_data:
            derby_text = f"🔥 DERBY ALERT: {derby_data['name']} (Intensity: {derby_data['intensity']}/10). {derby_data['description']}"
        
        if fixture_api_id:
            injuries_report = get_fixture_injuries(fixture_api_id)
            api_predictions = get_fixture_predictions(fixture_api_id)
        
        # Calculate Fatigue
        h_rest = get_team_last_match_date(home_team.api_id, match.date)
        a_rest = get_team_last_match_date(away_team.api_id, match.date)
        
        home_rest_days = f"{h_rest} days" if h_rest is not None else "Unknown (Fresh)"
        away_rest_days = f"{a_rest} days" if a_rest is not None else "Unknown (Fresh)"

        # 4. Enhanced "Coach's Logic" Prompt
        system_prompt = """
        You are "The Coach" - an elite Sports Betting Analyst.
        
        ### THE COACH'S LOGIC (5-Layer Analysis):
        
        1. **Layer 1: Tactical Matchup**
           - Styles make fights. Who dominates possession? Who counters?
           
        2. **Layer 2: Underlying Metrics**
           - xG proxies, recent form, and H2H dominance.
           
        3. **Layer 3: Fatigue & Schedule**
           - Rest days are critical. <4 days rest = performance drop.
           
        4. **Layer 4: News & Injuries**
           - Confirmed absences and dressing room morale.
           
        5. **Layer 5: Psychology & Context (The Intangibles)**
           - **Motivation**: Is this a Title Race (High) vs Mid-table (Low) vs Relegation (Desperate)?
           - **Rivalry**: Derbies ignore form. Intensity is high. Cards are likely.
           - **Manager**: New Manager Bounce? Or a Coach under pressure?
        
        CRITICAL: Layer 5 often overrides Layer 1. A desperate team at home fighting relegation will outperform their stats.
        
        ### OUTPUT FORMAT (JSON):
        {
            "home_win_probability": 0.45,
            "draw_probability": 0.30,
            "away_win_probability": 0.25,
            "predicted_outcome": "Home",
            "confidence": 0.75,
            "risk_rating": 6,
            "reasoning": "Detailed analysis integrating all 5 layers..."
        }
        
        ### OUTPUT REQUIREMENTS:
        
        Return a JSON object:
        {
            "home_win_probability": 0.45,
            "draw_probability": 0.30,
            "away_win_probability": 0.25,
            "predicted_outcome": "Home" or "Draw" or "Away",
            "confidence": 0.70,  // 0.0 to 1.0 based on data consistency
            "risk_rating": 5,    // 1 (Safe) to 10 (Extreme Risk) based on volatility
            "reasoning": "Detailed analysis following the 4 Layers..."
        }
        
        CRITICAL: 
        - Probabilities MUST sum to 1.0.
        - Be realistic. Draws happen ~25-30% of the time.
        - If the match is too close to call, increase the Risk Rating.
        """

        user_prompt = f"""
        Match: {home_team.name} vs {away_team.name}
        Date: {match.date}
        
        ### PSYCHOLOGY & CONTEXT (LAYER 5) ###
        - Match Type: {derby_text}
        - {home_team.name} Stakes: {home_context.get('context')} (Rank {home_context.get('rank')})
        - {away_team.name} Stakes: {away_context.get('context')} (Rank {away_context.get('rank')})
        - {home_team.name} Manager: {home_manager}
        - {away_team.name} Manager: {away_manager}
        
        ### 1. TACTICAL DATA ###
        [HOME: {home_team.name}]
        - Style Stats: {home_stats}
        - Form: {home_form}
        - Rest Days: {home_rest_days}
        - News: {home_news}
        
        [AWAY: {away_team.name}]
        - Style Stats: {away_stats}
        - Form: {away_form}
        - Rest Days: {away_rest_days}
        - News: {away_news}
        
        ### 2. MATCHUP DATA ###
        [HEAD-TO-HEAD]
        {h2h_summary}
        
        [INJURIES]
        {injuries_report}
        
        [COMPARISON METRICS]
        {api_predictions}
        
        ### ASSIGNMENT ###
        Apply "The Coach's Logic". Analyze the 4 Layers.
        Provide probabilities, confidence, and a risk rating (1-10).
        """

        # 5. Call OpenAI
        try:
            print(f"🤖 Running AI analysis...")
            response = client.chat.completions.create(
                model="gpt-4o",
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            )

            result_text = response.choices[0].message.content
            ai_prediction = json.loads(result_text)

            # Extract probabilities
            prob_home = ai_prediction.get('home_win_probability', 0)
            prob_draw = ai_prediction.get('draw_probability', 0)
            prob_away = ai_prediction.get('away_win_probability', 0)
            confidence = ai_prediction.get('confidence', 0.5)
            ai_risk = ai_prediction.get('risk_rating', 5)
            reasoning = ai_prediction.get('reasoning', '')
            
            print(f"\n🎯 AI Prediction:")
            print(f"   Home Win: {prob_home:.1%}")
            print(f"   Draw: {prob_draw:.1%}")
            print(f"   Away Win: {prob_away:.1%}")
            print(f"   Confidence: {confidence:.1%}")
            print(f"   AI Risk Rating: {ai_risk}/10")

            # 6. Calculate Expected Values
            ev_home = None
            ev_draw = None
            ev_away = None
            
            if odds_data:
                print(f"\n💰 Expected Value Analysis:")
                ev_home = calculate_expected_value(prob_home, odds_data.get('home_win'))
                ev_draw = calculate_expected_value(prob_draw, odds_data.get('draw'))
                ev_away = calculate_expected_value(prob_away, odds_data.get('away_win'))
                
                print(f"   Home Win EV: ${ev_home:.2f}" if ev_home else "   Home Win EV: N/A")
                print(f"   Draw EV: ${ev_draw:.2f}" if ev_draw else "   Draw EV: N/A")
                print(f"   Away Win EV: ${ev_away:.2f}" if ev_away else "   Away Win EV: N/A")

            # 7. Calculate Risk Rating (Combine AI risk with Math risk)
            risk_rating = calculate_risk_rating(confidence, ev_home, ev_away, ev_draw, ai_risk)
            print(f"\n⚖️  Final Risk Rating: {risk_rating}/10")

            # 8. Generate Betting Advice
            betting_advice = generate_betting_advice(ev_home, ev_away, ev_draw, risk_rating, confidence)
            print(f"\n{betting_advice}")

            # 9. Determine predicted winner
            predicted_winner_id = None
            predicted_outcome = ai_prediction.get('predicted_outcome', 'Draw')
            
            if predicted_outcome == 'Home' or predicted_outcome == home_team.name:
                predicted_winner_id = match.team_home_id
            elif predicted_outcome == 'Away' or predicted_outcome == away_team.name:
                predicted_winner_id = match.team_away_id
            # else: Draw (predicted_winner_id remains None)
            
            # 10. Save Prediction
            new_pred = Prediction(
                match_id=match.id,
                predicted_winner_id=predicted_winner_id,
                confidence_score=confidence,
                reasoning=reasoning,
                home_win_probability=prob_home,
                away_win_probability=prob_away,
                draw_probability=prob_draw,
                risk_rating=risk_rating,
                betting_advice=betting_advice,
                expected_value_home=ev_home,
                expected_value_away=ev_away,
                expected_value_draw=ev_draw
            )
            session.add(new_pred)
            session.commit()
            print("✅ Prediction saved to DB.")


        except Exception as e:
            print(f"\n❌ Analysis Failed: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    predict_upcoming_matches()