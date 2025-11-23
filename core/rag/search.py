import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()
SERPER_KEY = os.getenv("SERPER_API_KEY")


def get_team_news(team_name, sport="football"):
    """
    Searches for critical news about a team in the last 7 days.
    Focuses on injuries, lineup changes, and manager statements.
    """
    url = "https://google.serper.dev/search"

    # We construct a specific query to get betting-relevant info
    query = f"{team_name} {sport} team news injuries lineup prediction last 3 days"

    payload = json.dumps({
        "q": query,
        "num": 4,  # Get top 4 results
        "tbs": "qdr:w"  # 'qdr:w' = Past Week (Critical for sports)
    })

    headers = {
        'X-API-KEY': SERPER_KEY,
        'Content-Type': 'application/json'
    }

    try:
        response = requests.post(url, headers=headers, data=payload)
        results = response.json()

        # Extract just the text snippets to save tokens
        snippets = []
        if 'organic' in results:
            for item in results['organic']:
                title = item.get('title', '')
                snippet = item.get('snippet', '')
                snippets.append(f"- {title}: {snippet}")

        return "\n".join(snippets)
    except Exception as e:
        print(f"Search Error: {e}")
        return "No recent news found."


# Test it
if __name__ == "__main__":
    print(get_team_news("Manchester City"))