"""
Search Tool
Web search using external API.
"""
import os

import dotenv
import requests
from langchain.tools import tool

# Load env for API keys
dotenv.load_dotenv()

api_key = os.getenv("WEB_SEARCH_API_KEY")
url = os.getenv("WEB_SEARCH_API_URL")


@tool(description="This tool that integrations search api can search Various real-time text information"
                  " on Internet and will return the web link."
                  "if the returned content is not detailed enough, you can use the read_webpage tool to"
                  "get more detailed information.")
def search_from_internet(query: str) -> dict:
    """Search for information on the internet."""
    
    payload = {
        "search_query": query,
        "search_engine": "search_pro_quark",
        "search_intent": False,
        "count": 5,
        "search_domain_filter": "<string>",
        "search_recency_filter": "noLimit",
        "content_size": "medium",
        "request_id": "<string>",
        "user_id": "<string>"
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=30
        )
        return response.json()
    except Exception as e:
        return {"error": str(e)}