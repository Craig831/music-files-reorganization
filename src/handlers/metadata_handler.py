from dotenv import load_dotenv
import os
import re
import json
import acoustid
import chromaprint
import musicbrainzngs
import subprocess
import shutil

load_dotenv()

ACOUSTID_API_KEY = os.getenv("ACOUSTID_APP_API_KEY")
# MusicBrainz: Set a descriptive user agent for your app
# musicbrainzngs.set_useragent("music-folder-organizer", "1.0", "cjeffords831@gmail.com")

# MusicBrainz User Agent Setup (Important for MusicBrainz API)
mb_app = os.getenv("MB_APP_NAME", "MySongNormalizer")
mb_version = os.getenv("MB_APP_VERSION", "0.3")
mb_contact = os.getenv("MB_APP_CONTACT", "your-email@example.com") # PLEASE CHANGE THIS


def get_fingerprint_duration_directly(audio_filepath):
    """
    Uses a direct subprocess call to fpcalc -json to get duration and fingerprint.
    Returns (duration (float), fingerprint_string (str)) or (None, None) on failure.
    """
    fpcalc_path = shutil.which('fpcalc')
    if not fpcalc_path:
        print("  [Direct fpcalc] CRITICAL: 'fpcalc' command not found in PATH.")
        return None, None

    command = [fpcalc_path, "-json", audio_filepath]
    # print(f"  [Direct fpcalc] Executing: {' '.join(command)}") # Verbose
    try:
        process = subprocess.run(command, capture_output=True, text=True, check=False, timeout=30)
        if process.returncode == 0:
            try:
                fpcalc_data = json.loads(process.stdout)
                # Ensure keys exist and duration is a number, fingerprint is a non-empty string
                duration_val = fpcalc_data.get("duration")
                fp_str = fpcalc_data.get("fingerprint")

                if isinstance(duration_val, (int, float)) and fp_str and isinstance(fp_str, str):
                    print(f"  [Direct fpcalc] SUCCESS: Duration: {int(duration_val)}, Fingerprint (first 30): {fp_str[:30]}")
                    return int(duration_val), fp_str
                else:
                    print(f"  [Direct fpcalc] ERROR: fpcalc -json output JSON missing/invalid 'fingerprint' or 'duration'.")
                    print(f"    Duration type: {type(duration_val)}, FP type: {type(fp_str)}")
                    print(f"    STDOUT: {process.stdout.strip()}")
                    return None, None
            except json.JSONDecodeError as e:
                print(f"  [Direct fpcalc] ERROR: fpcalc -json STDOUT not valid JSON. Error: {e}")
                print(f"    STDOUT: {process.stdout.strip()}")
                return None, None
        else:
            print(f"  [Direct fpcalc] ERROR: fpcalc -json exited with code {process.returncode}.")
            if process.stderr.strip(): print(f"    STDERR: {process.stderr.strip()}")
            return None, None
    except subprocess.TimeoutExpired:
        print(f"  [Direct fpcalc] ERROR: fpcalc command timed out.")
        return None, None
    except Exception as e:
        print(f"  [Direct fpcalc] ERROR: An unexpected error occurred: {e}")
        return None, None



def identify_song_fingerprint(filepath):
    if not ACOUSTID_API_KEY:
        print("  [AcoustID] API key not available. Skipping fingerprinting.")
        return None
    
    filename_log = os.path.basename(filepath)
    # print(f"  [AcoustID] Processing file: {filename_log} (pyacoustid version: {getattr(acoustid, '__version__', 'N/A')})")
    print(f"  [AcoustID] Processing file: {filename_log}")


    # Step 1: Get duration and fingerprint using our direct fpcalc call
    # This is the part we know works from your tests.
    duration, fp_string = get_fingerprint_duration_directly(filepath)
    #duration, fingerprint = acoustid.fingerprint_file(filepath, force_fpcalc=True) # force_fpcalc might be an option

    if fp_string is None or duration is None: # duration can be 0.0, so check for None explicitly
        print(f"  [AcoustID] Failed to get fingerprint/duration directly for {filename_log} via custom fpcalc call. AcoustID lookup cannot proceed.")
        return None

    # Ensure types are correct for acoustid.lookup
    # fp_string should be str, duration should be float or int.
    if not isinstance(fp_string, str) or not isinstance(duration, (float, int)):
        print(f"  [AcoustID] ERROR: Type mismatch for fingerprint or duration. FP type: {type(fp_string)}, Duration type: {type(duration)}. Cannot proceed.")
        return None

    # Step 2: Use the obtained duration and fingerprint with acoustid.lookup
    print(f"    Attempting acoustid.lookup (API key: {'***' + ACOUSTID_API_KEY[-4:] if ACOUSTID_API_KEY and len(ACOUSTID_API_KEY) > 4 else 'InvalidKey'}, duration: {duration}, fp (first 30): {fp_string[:30]}...).")
    
    try:
        # This call should ONLY perform the web lookup.
        results = list(acoustid.lookup(
            ACOUSTID_API_KEY, 
            fp_string, # Use the fingerprint string from our direct call
            duration,  # Use the duration from our direct call
            # parse=True, # Tells pyacoustid to parse the JSON response into objects
            meta="recordings releases releasegroups" # Request comprehensive metadata
        ))
        
        # Filter results to ensure they are objects with a 'score' attribute
        # This guards against 'str' objects or other unexpected items in the list.
        valid_results = [r for r in results if hasattr(r, 'score') and not isinstance(r, str)]

        if not valid_results:
            print(f"  [AcoustID] No valid matches (or only non-object results) found in AcoustID database for {filename_log} via acoustid.lookup().")
            if results: # Log if there were raw results but none were valid
                print(f"    Raw results received: {results}")
            return None


        # Find the best result (highest score)
        best_result = max(results, key=lambda r: r.score)
        if best_result.score < 0.5: # Confidence threshold
            print(f"  [AcoustID] Best match score ({best_result.score:.2f}) for {filename_log} via acoustid.lookup() is too low.")
            return None

        print(f"  [AcoustID] Matched {filename_log} via acoustid.lookup() with score {best_result.score:.2f}")
        
        # Extract metadata from best_result
        title = getattr(best_result, 'title', "Unknown Title")
        artist = getattr(best_result, 'artist_credit_phrase', None) or \
                 (getattr(best_result.artists[0], 'name', "Unknown Artist") if hasattr(best_result, 'artists') and best_result.artists else "Unknown Artist")
        
        album, track_num_str, year = None, None, None
        mb_recording_id = getattr(best_result, 'id', None)

        if hasattr(best_result, 'releases') and best_result.releases:
            # Logic to pick the "best" release can be complex. Taking the first one.
            release = best_result.releases[0] 
            album = getattr(release, 'title', None)
            if hasattr(release, 'date') and release.date and hasattr(release.date, 'year') and release.date.year:
                year = str(release.date.year)
            
            # Find track number on this release
            if mb_recording_id and hasattr(release, 'media') and release.media:
                 for medium_item in release.media:
                    if hasattr(medium_item, 'tracks') and medium_item.tracks:
                        for track_item in medium_item.tracks:
                            if hasattr(track_item, 'id') and track_item.id == mb_recording_id and hasattr(track_item, 'position'):
                                track_num_str = str(track_item.position) # .zfill(2) applied later
                                break
                    if track_num_str: break
        
        return {"artist": artist, "title": title, "album": album, "tracknumber": track_num_str, "year": year, "mb_recording_id": mb_recording_id, "source_comment": f"AcoustID Lookup (Score: {best_result.score:.2f})"}

    except acoustid.NoBackendError:
        print("  [AcoustID Error] fpcalc tool not found. Please install chromaprint-tools.")
    except chromaprint.FingerprintError:
        print("Could not compute fingerprint.")
    except acoustid.FingerprintGenerationError as fge_lookup: # This should NOT happen here
        print(f"    FAILURE: acoustid.lookup() UNEXPECTEDLY raised FingerprintGenerationError: {fge_lookup} for {filename_log}.")
        print(f"             This is highly unusual as fingerprint was already generated.")
    except acoustid.FingerprintSubmissionError as e:
        print(f"  [AcoustID FingerprintSubmissionError] {e}")
    except acoustid.WebServiceError as wse: # Errors from the web service call itself
        print(f"    FAILURE: acoustid.lookup() raised WebServiceError: {wse} for {filename_log}.")
    except Exception as e_lookup: # Other unexpected errors during lookup or parsing results
        print(f"    FAILURE: acoustid.lookup() raised an unexpected error: {e_lookup} (Type: {type(e_lookup).__name__}) for {filename_log}.")
    return None

def get_musicbrainz_details(artist_guess, title_guess, album_guess=None):
    """
    Queries MusicBrainz for song details.
    (Conceptual - ensure your full implementation is robust)
    """
    if mb_contact == "your-email@example.com":
        print("Warning: Please update MB_APP_CONTACT environment variable with your actual email or website.")
    musicbrainzngs.set_useragent(mb_app, mb_version, mb_contact)

    try:
        # Construct a query. The more info you have, the better.
        query_parts = {}
        if artist_guess: query_parts['artist'] = artist_guess
        if title_guess: query_parts['recording'] = title_guess # 'recording' is often better than 'track' for title
        if album_guess: query_parts['release'] = album_guess # 'release' for album title

        if not query_parts: return None

        result = musicbrainzngs.search_recordings(limit=5, **query_parts) # Get a few results

        if result.get('recording-list'):
            best_match = result['recording-list'][0] # Simplistic: take the first one
            
            title = best_match.get('title', title_guess)
            artist = artist_guess
            if best_match.get('artist-credit'):
                artist = best_match['artist-credit-phrase'] or best_match['artist-credit'][0]['artist']['name']

            album = album_guess
            track_number = None
            year = None
            mb_recording_id = best_match.get('id')

            if best_match.get('release-list'):
                release_info = best_match['release-list'][0] # Simplistic choice
                album = release_info.get('title', album)
                if release_info.get('date'):
                    year_match = re.match(r"(\d{4})", release_info['date'])
                    if year_match: year = year_match.group(1)
                
                for medium in release_info.get('medium-list', []):
                    for track in medium.get('track-list', []):
                        if track.get('recording', {}).get('id') == mb_recording_id:
                            track_number = str(track.get('number')).zfill(2)
                            break
                    if track_number: break
            
            return {
                "artist": artist,
                "title": title,
                "album": album,
                "tracknumber": track_number,
                "year": year,
                "mb_recording_id": mb_recording_id,
                "source_comment": "MusicBrainz Search"
            }
        return None
    except musicbrainzngs.WebServiceError as e:
        print(f"  [MusicBrainz Search Error] {e}")
    except Exception as e:
        print(f"  [Error in get_musicbrainz_details] {e} (Type: {type(e).__name__})")
    return None


def test_fpcalc_with_json_output(audio_filepath):
    """
    Tests fpcalc execution with the -json flag, which is typically used by pyacoustid.
    Prints detailed output for diagnostics.
    """
    fpcalc_path = shutil.which('fpcalc')
    if not fpcalc_path:
        print("  [fpcalc Test -json] CRITICAL: 'fpcalc' command not found in Python's PATH.")
        print("    Ensure chromaprint-tools is installed and fpcalc is in a directory listed in your PATH environment variable for the Python process.")
        return False

    print(f"  [fpcalc Test -json] Found 'fpcalc' at: {fpcalc_path}")
    print(f"  [fpcalc Test -json] Testing with file: {audio_filepath} using the -json flag.")

    command = [fpcalc_path, "-json", audio_filepath] # Key change: added -json

    try:
        process = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False, # Don't raise an exception for non-zero exit codes
            timeout=30   # Timeout for safety
        )

        print(f"  [fpcalc Test -json] Exit Code: {process.returncode}")
        # Always print STDOUT and STDERR to see what fpcalc actually outputted
        print(f"  [fpcalc Test -json] STDOUT:\n{process.stdout[:30].strip()}")
        if process.stderr.strip(): # Only print stderr if it's not empty
            print(f"  [fpcalc Test -json] STDERR:\n{process.stderr.strip()}")

        if process.returncode == 0:
            # If exit code is 0, try to parse STDOUT as JSON
            try:
                fpcalc_data = json.loads(process.stdout)
                if "fingerprint" in fpcalc_data and "duration" in fpcalc_data:
                    print("  [fpcalc Test -json] SUCCESS: fpcalc -json executed and returned valid JSON with fingerprint and duration.")
                    # You could print fpcalc_data['fingerprint'] and fpcalc_data['duration'] here if needed
                    return True
                else:
                    print("  [fpcalc Test -json] PARTIAL SUCCESS: fpcalc -json ran (exit code 0) but output JSON is missing 'fingerprint' or 'duration'.")
                    return False
            except json.JSONDecodeError as e:
                print(f"  [fpcalc Test -json] FAILURE: fpcalc -json ran (exit code 0) but STDOUT was not valid JSON. Error: {e}")
                return False
        else:
            # fpcalc exited with an error
            print(f"  [fpcalc Test -json] FAILURE: fpcalc -json exited with error code {process.returncode}.")
            if "could not decode audio file" in process.stderr.lower() or \
               "format not recognized" in process.stderr.lower() or \
               "error decoding" in process.stderr.lower(): # Added common decoding error phrases
                print("    The STDERR from fpcalc suggests it failed to decode the audio file when using the -json flag.")
            elif "error while loading shared libraries" in process.stderr.lower() or \
                 "cannot open shared object file" in process.stderr.lower():
                print("    The STDERR suggests a shared library issue (e.g., for FFmpeg decoders).")
            return False

    except FileNotFoundError:
        print(f"  [fpcalc Test -json] CRITICAL: Command '{fpcalc_path}' (fpcalc) not found during execution attempt.")
        return False
    except subprocess.TimeoutExpired:
        print("  [fpcalc Test -json] FAILURE: fpcalc -json command timed out.")
        return False
    except Exception as e:
        print(f"  [fpcalc Test -json] FAILURE: An unexpected error occurred: {e}")
        return False
