import os
import anthropic
from dotenv import load_dotenv

# Load env variables
load_dotenv()

api_key = os.environ.get("ANTHROPIC_API_KEY")
if not api_key:
    print("Error: ANTHROPIC_API_KEY not found in environment.")
    exit(1)

client = anthropic.Anthropic(api_key=api_key)

candidate_models = [
    "claude-3-5-sonnet-20241022",
    "claude-3-5-sonnet-20240620",
    "claude-3-5-sonnet-latest",
    "claude-3-5-haiku-20241022",
    "claude-3-5-haiku-latest",
    "claude-3-haiku-20240307",
    "claude-sonnet-4-20250514",
    "claude-haiku-4-5-20251001",
]

for model in candidate_models:
    try:
        response = client.messages.create(
            model=model,
            max_tokens=10,
            messages=[{"role": "user", "content": "Hi"}],
        )
        print(f"✅ Success: {model}")
    except anthropic.NotFoundError as e:
        print(f"❌ NotFound (404): {model}")
    except Exception as e:
        print(f"⚠️ Other Error for {model}: {e}")
