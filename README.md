# Sports Oracle

Sports Oracle is an advanced AI-powered sports prediction platform designed to analyze football (soccer) matches with professional depth. It combines statistical data, live odds, team news, and contextual factors to generate high-confidence match predictions and betting advice.

## 🚀 Features

*   **AI-Driven Analysis**: Utilizes GPT-4o to analyze matches through a "5-Layer Logic" system:
    1.  **Tactical Matchup**: Formation analysis and midfield dominance.
    2.  **Key Duels**: Head-to-head player comparisons.
    3.  **Discipline & Volatility**: Referee stats, card history, and aggression levels.
    4.  **Context & Psychology**: Motivation (title race vs. relegation), managerial pressure, and derby intensity.
    5.  **The Verdict**: A final synthesis of all factors.
*   **Real-Time Data**: Integrates live data for:
    *   Match Odds
    *   Team Form & H2H Stats
    *   Injuries & Suspensions
    *   Predicted Lineups & Formations
*   **Betting Intelligence**:
    *   **Expected Value (EV) Calculation**: Identifies value bets where the probability exceeds the implied odds.
    *   **Risk Rating**: Assigns a risk score (1-10) to every prediction.
    *   **Virtual Wallet**: A simulated betting environment to test strategies without real financial risk.
*   **News Integration**: Fetches real-time team news to catch late-breaking developments affecting match outcomes.

## 🛠️ Tech Stack

*   **Backend**: Python, Flask
*   **Database**: SQLAlchemy (ORM)
*   **AI Engine**: OpenAI GPT-4o
*   **Data Sources**: API-Football (Stats/Odds), Web Search (News)
*   **Frontend**: HTML/CSS/JavaScript

## 📦 Installation

1.  **Clone the repository**
    ```bash
    git clone https://github.com/yourusername/sports_oracle.git
    cd sports_oracle
    ```

2.  **Create a virtual environment**
    ```bash
    python -m venv .venv
    # Windows
    .venv\Scripts\activate
    # Mac/Linux
    source .venv/bin/activate
    ```

3.  **Install dependencies**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Environment Configuration**
    Create a `.env` file in the root directory and add your API keys:
    ```env
    OPENAI_API_KEY=your_openai_api_key
    # Add other necessary keys (e.g., API-Football Key)
    ```

## 🚦 Usage

1.  **Start the application**
    ```bash
    python web/app.py
    ```

2.  **Access the dashboard**
    Open your browser and navigate to `http://localhost:5000`.

3.  **Make a Prediction**
    *   Select a Home Team and Away Team.
    *   Click "Predict" to generate a detailed analysis.
    *   View the AI's reasoning, probabilities, and betting advice.

## 🔮 Roadmap & TODO

*   [ ] Improve mobile responsiveness for the web interface.
*   [ ] Add user authentication for personalized bet tracking.
*   [ ] Implement historical backtesting to validate AI accuracy.
*   [ ] **Expand support into other sports (Basketball, Tennis, NFL).**

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📄 License

[MIT License](LICENSE)
