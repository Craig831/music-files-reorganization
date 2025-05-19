from dotenv import load_dotenv
import os
import re
from openai import OpenAI
import json

load_dotenv()
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI()


def clean_filename_for_llm(filename_no_ext):
    """Prepares a mangled filename for an LLM query."""
    name = re.sub(r"^\s*\d+[\s._-]*", "", filename_no_ext) # Remove numeric prefixes
    name = name.replace("_", " ").replace("-", " ") # Underscores/hyphens to spaces
    name = re.sub(r"\s+", " ", name).strip() # Consolidate spaces
    return name


def extract_json_from_llm_response(llm_output_str):
    """
    Extracts a JSON string from a larger string, potentially with Markdown fences.
    """
    if not llm_output_str:
        return None

    # Regex to find JSON within ```json ... ``` or just { ... } or [ ... ]
    # This looks for a string starting with { or [ and ending with } or ]
    # It tries to be robust to variations in markdown formatting.
    match = re.search(r"```json\s*(\{.*?\})\s*```|(\{.*?\})|(\[.*?\])", llm_output_str, re.DOTALL)
    
    json_str = None
    if match:
        # Prioritize the content within ```json ... ``` if present
        if match.group(1): 
            json_str = match.group(1)
        # Otherwise, take the first non-null group which should be a JSON object or array
        elif match.group(2):
            json_str = match.group(2)
        elif match.group(3):
            json_str = match.group(3)
            
    if json_str:
        return json_str.strip()
    else:
        # Fallback: if no fences, but the string itself might be JSON
        # This is less robust but can catch cases where LLM just returns raw JSON
        stripped_output = llm_output_str.strip()
        if (stripped_output.startswith('{') and stripped_output.endswith('}')) or \
           (stripped_output.startswith('[') and stripped_output.endswith(']')):
            return stripped_output
        return None

def query_llm_for_song_details(filename_no_ext):
    """
    Conceptual LLM query.
    """
    if not OPENAI_KEY:
        print("  [LLM] OpenAI API key not set. Skipping LLM query.")
        return None
    prompt = f"""
    Given the following potentially mangled song filename part, identify the correct artist, album and title.
    If it seems to have a track number prefix, please state it.
    If parts are truncated or have underscores replacing other characters like apostrophes or colons, please correct them.
    Provide the answer as a JSON object with keys "artist", "album", "title", and "original_prefix_number" (if any).
    You don't have to fill in all of the fields.  Return as many as you can.

    JSON:
    """
    try:
        # Example for OpenAI ChatCompletion
        response = client.chat.completions.create(
            model="gpt-4.1-mini", # Or a more advanced model
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"Filename part: \"{filename_no_ext}\""}
            ],
            temperature=0.3 # Lower temperature for more deterministic output
        )
        # Parse the JSON response from the LLM
        # This will require careful parsing and error handling
        content = response.choices[0].message.content
        print(f"LLM raw response: {content}")

        json_to_parse = extract_json_from_llm_response(content)

        if not json_to_parse:
            print(f"  [LLM] Could not extract a valid JSON structure from the LLM response.")
            return None

        try:
            # Now parse the cleaned JSON string
            parsed_data = json.loads(json_to_parse)
            # Basic validation: ensure it's a dictionary and has expected keys (optional but good)
            if not isinstance(parsed_data, dict):
                print(f"  [LLM] Parsed JSON is not a dictionary: {parsed_data}")
                return None
            # You could add checks for parsed_data.get('artist'), etc. here if desired
            return parsed_data
        except json.JSONDecodeError as e:
            print(f"  [LLM] JSONDecodeError after attempting to clean response: {e}")
            print(f"    Attempted to parse: '{json_to_parse}'")
            return None
        except Exception as e_generic: # Catch any other unexpected errors during parsing
            print(f"  [LLM] Unexpected error parsing cleaned JSON: {e_generic}")
            print(f"    Attempted to parse: '{json_to_parse}'")
            return None

    except Exception as e:
        print(f"LLM API error: {e}")
        return None
