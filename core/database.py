import os
from datetime import datetime, timedelta
from sqlalchemy import create_engine, Column, Integer, String, DateTime, JSON, ForeignKey, Boolean, Float, Text
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
DB_URL = os.getenv("DB_URL", "sqlite:///./data/sports.db")

# Setup SQLAlchemy
Base = declarative_base()
engine = create_engine(DB_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# --- MODELS ---

class Sport(Base):
    __tablename__ = "sports"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True)
    api_identifier = Column(String, nullable=True)
    
    matches = relationship("Match", back_populates="sport")


class Team(Base):
    __tablename__ = "teams"
    id = Column(Integer, primary_key=True, index=True)
    api_id = Column(Integer, unique=True, nullable=True)
    sport_id = Column(Integer, ForeignKey("sports.id"))
    name = Column(String, index=True)
    logo_url = Column(String, nullable=True)
    stats_cache = Column(JSON, nullable=True)
    
    sport = relationship("Sport")


class Match(Base):
    __tablename__ = "matches"
    id = Column(Integer, primary_key=True, index=True)
    sport_id = Column(Integer, ForeignKey("sports.id"))
    date = Column(DateTime, index=True)
    tournament = Column(String)
    team_home_id = Column(Integer, ForeignKey("teams.id"))
    team_away_id = Column(Integer, ForeignKey("teams.id"))
    
    # Auto-resolution support
    scheduled_end_time = Column(DateTime, nullable=True)
    
    # Match results
    is_completed = Column(Boolean, default=False)
    final_score_home = Column(Integer, nullable=True)
    final_score_away = Column(Integer, nullable=True)
    
    # Relationships
    sport = relationship("Sport", back_populates="matches")
    team_home = relationship("Team", foreign_keys=[team_home_id])
    team_away = relationship("Team", foreign_keys=[team_away_id])
    details = relationship("MatchDetails", back_populates="match", uselist=False)
    predictions = relationship("Prediction", back_populates="match")
    odds = relationship("MatchOdds", back_populates="match", uselist=False)
    bets = relationship("Bet", back_populates="match")


class MatchDetails(Base):
    __tablename__ = "match_details"
    id = Column(Integer, primary_key=True, index=True)
    match_id = Column(Integer, ForeignKey("matches.id"))
    data = Column(JSON)
    
    match = relationship("Match", back_populates="details")


class Prediction(Base):
    __tablename__ = "predictions"
    id = Column(Integer, primary_key=True, index=True)
    match_id = Column(Integer, ForeignKey("matches.id"))
    predicted_winner_id = Column(Integer, ForeignKey("teams.id"), nullable=True)
    confidence_score = Column(Float)
    reasoning = Column(Text)

    # Betting enhancements
    home_win_probability = Column(Float, default=0.0)
    away_win_probability = Column(Float, default=0.0)
    draw_probability = Column(Float, default=0.0)
    risk_rating = Column(Integer, default=5)
    betting_advice = Column(Text, nullable=True)

    # EV Fields
    expected_value_home = Column(Float, nullable=True)
    expected_value_away = Column(Float, nullable=True)
    expected_value_draw = Column(Float, nullable=True)

    # --- PHASE 1 (Context) ---
    home_manager = Column(String, nullable=True)
    away_manager = Column(String, nullable=True)
    home_context = Column(String, nullable=True)
    away_context = Column(String, nullable=True)
    derby_alert = Column(String, nullable=True)

    # --- PHASE 3 (Tactics) ---
    home_formation = Column(String, nullable=True)
    away_formation = Column(String, nullable=True)

    # --- PHASE 4 (Deep Stats - JSON for flexibility) ---
    home_deep_stats = Column(JSON, nullable=True)
    away_deep_stats = Column(JSON, nullable=True)

    # --- PHASE 5 (Key Players) ---
    home_key_players = Column(String, nullable=True)
    away_key_players = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    match = relationship("Match", back_populates="predictions")
    predicted_winner = relationship("Team")


class MatchOdds(Base):
    __tablename__ = "match_odds"
    id = Column(Integer, primary_key=True, index=True)
    match_id = Column(Integer, ForeignKey("matches.id"), unique=True)
    
    home_win_odds = Column(Float, nullable=True)
    away_win_odds = Column(Float, nullable=True)
    draw_odds = Column(Float, nullable=True)
    bookmaker = Column(String, default="Average")
    fetched_at = Column(DateTime, default=datetime.utcnow)
    
    match = relationship("Match", back_populates="odds")


class Bet(Base):
    __tablename__ = "bets"
    id = Column(Integer, primary_key=True, index=True)
    match_id = Column(Integer, ForeignKey("matches.id"))
    prediction_id = Column(Integer, ForeignKey("predictions.id"), nullable=True)
    
    bet_type = Column(String)  # 'HOME_WIN', 'AWAY_WIN', 'DRAW'
    stake_amount = Column(Float, default=100.0)
    odds = Column(Float)
    potential_return = Column(Float)
    
    status = Column(String, default="PENDING")  # PENDING, WON, LOST, VOID
    placed_at = Column(DateTime, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)
    actual_result = Column(String, nullable=True)
    
    match = relationship("Match", back_populates="bets")
    prediction = relationship("Prediction")


# Legacy model for backward compatibility
class VirtualBet(Base):
    __tablename__ = "virtual_bets"
    id = Column(Integer, primary_key=True, index=True)
    match_id = Column(Integer, ForeignKey("matches.id"))
    team_target_id = Column(Integer, ForeignKey("teams.id"), nullable=True)
    prediction_type = Column(String)
    predicted_score = Column(String)
    stake_amount = Column(Float, default=100.0)
    confidence = Column(Float)
    reasoning = Column(String)
    status = Column(String, default="PENDING")
    payout = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    match = relationship("Match")
    team_target = relationship("Team")

class Wallet(Base):
    __tablename__ = "wallet"
    id = Column(Integer, primary_key=True, index=True)
    balance = Column(Float, default=10000.0)
    updated_at = Column(DateTime, default=datetime.utcnow)


def init_db():
    """Creates the database tables."""
    if not os.path.exists("./data"):
        os.makedirs("./data")
    Base.metadata.create_all(bind=engine)

    # Initialize Wallet with $10,000 if not exists
    session = SessionLocal()
    if not session.query(Wallet).first():
        print("💰 Creating initial wallet with $10,000...")
        wallet = Wallet(balance=10000.0)
        session.add(wallet)
        session.commit()
    session.close()

    print("✅ Database tables created in ./data/sports.db")


if __name__ == "__main__":
    print("Creating database tables...")
    init_db()
    
    # Quick test
    session = SessionLocal()
    
    # Add a sport if not exists
    football = session.query(Sport).filter_by(name='Football').first()
    if not football:
        football = Sport(name='Football', api_identifier='football')
        session.add(football)
        session.commit()
        print(f"✅ Created sport: {football.name}")
    
    session.close()
    print("✅ Database ready!")