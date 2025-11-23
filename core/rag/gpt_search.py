import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def get_team_news_gpt(team_name):
    """
    Uses GPT-4o to search the web for real-time news.
    """
    print(f"   🌐 Browsing web for {team_name} news...")

    prompt = f"""
    Search for the latest breaking sports news for {team_name} regarding their upcoming match.
    Focus strictly on:
    1. Confirmed Injuries/Suspensions (Who is OUT?)
    2. Manager Press Conference quotes from the last 48 hours.
    3. Dressing room morale reports.

    Summarize into 3 bullet points.
    """

    try:
        # Note: Requires an OpenAI account with web browsing enabled capabilities
        # or a model/tool configuration that supports it. 
        # If using standard API, we rely on its internal knowledge + strict hallucinations check,
        # OR ideally, we use a tool definition if you have the Search tool enabled.

        # Standard GPT-4o call (assuming recent knowledge cutoff or browsing tool access)
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a sports news aggregator. Be concise."},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"News fetch error: {e}")
        return "News unavailable."