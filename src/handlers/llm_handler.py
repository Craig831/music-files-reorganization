from dotenv import load_dotenv
import os
import openai # or from google.generativeai import GenerativeModel

load_dotenv()

# Configure your LLM client (e.g., OpenAI)
openai.api_key = os.getenv("OPENAI_API_KEY")

def query_llm_for_song_details(filename_part):
    # For OpenAI
    prompt = f"""
    Given the following potentially mangled song filename part, try to identify the correct artist and title.
    If it seems to have a track number prefix, please state it.
    If parts are truncated or have underscores for spaces, please correct them.
    Provide the answer as a JSON object with keys "artist", "title", and "original_prefix_number" (if any).
    If unsure, return null for the fields.

    Filename part: "{filename_part}"

    JSON:
    """
    try:
        # Example for OpenAI ChatCompletion
        response = openai.ChatCompletion.create(
            model="gpt-4.1-mini", # Or a more advanced model
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3 # Lower temperature for more deterministic output
        )
        # Parse the JSON response from the LLM
        # This will require careful parsing and error handling
        content = response.choices[0].message.content
        print(f"LLM raw response: {content}")
        # You'll need to parse the JSON string from content.
        # Be prepared for the LLM not always returning perfect JSON.
        import json
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            print(f"LLM did not return valid JSON: {content}")
            # You might try to extract info with regex or further LLM calls here
            return None

    except Exception as e:
        print(f"LLM API error: {e}")
        return None

# Example of how you might use it with a filename
# filename = "03_The_Artst_-_Sng_Nme_Inc"
# filename_without_ext = os.path.splitext(os.path.basename(filename))[0]
# llm_guess = query_llm_for_song_details(filename_without_ext)
# if llm_guess and llm_guess.get("artist") and llm_guess.get("title"):
#     print(f"LLM Suggestion: {llm_guess['artist']} - {llm_guess['title']}")
    # You could then try to verify this with MusicBrainz