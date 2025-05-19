import os
import re
import shutil
from dotenv import load_dotenv
import handlers.file_handler as filehandler
import handlers.metadata_handler as metadatahandler
import handlers.llm_handler as llmhandler
import time

load_dotenv()

def main():
    start_time = time.time()

    # --- Environment Variable Loading ---
    test_run_file_limit_str = os.getenv("TEST_FILE_COUNT")
    DEFAULT_TEST_LIMIT = 3
    try:
        test_run_file_limit = int(test_run_file_limit_str) if test_run_file_limit_str is not None else DEFAULT_TEST_LIMIT
        if test_run_file_limit <= 0:
            test_run_file_limit = DEFAULT_TEST_LIMIT
    except ValueError:
        test_run_file_limit = DEFAULT_TEST_LIMIT

    music_folder_raw = os.getenv("MUSIC_PATH") # This is the folder with the unorganized files
    if not music_folder_raw:
        print("Error: MUSIC_PATH environment variable is not set (folder with unorganized files). Please set it and try again.")
        return
    
    test_run_file_limit = 0


    # Define a root for organized music, can be same as music_folder_raw or different
    # For this example, let's assume we organize within a subfolder or a different specified root.
    # If you want to organize IN-PLACE within music_folder_raw, then organized_music_root = music_folder_raw
    organized_music_root = os.getenv("ORGANIZED_MUSIC_ROOT", music_folder_raw)
    if not os.path.isdir(organized_music_root):
        try:
            os.makedirs(organized_music_root, exist_ok=True)
            print(f"Created ORGANIZED_MUSIC_ROOT directory: {organized_music_root}")
        except Exception as e:
            print(f"Error: ORGANIZED_MUSIC_ROOT ('{organized_music_root}') does not exist and could not be created: {e}")
            return


    dry_run_str = os.getenv("DRY_RUN", "true").lower()
    dry_run = dry_run_str == "true" or dry_run_str == "1"
    
    allow_apostrophe_in_filename_str = os.getenv("ALLOW_APOSTROPHE_FILENAME", "false").lower()
    allow_apostrophe_in_filename = allow_apostrophe_in_filename_str == "true" or allow_apostrophe_in_filename_str == "1"


    # API Keys from environment (ensure these are set if functionality is used)
    ACOUSTID_API_KEY = os.getenv("ACOUSTID_API_KEY")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") # Example

    print(f"--- Song Normalizer ---")
    print(f"Unorganized Music Folder: {music_folder_raw}")
    print(f"Organized Music Root: {organized_music_root}")
    print(f"Dry Run: {dry_run}")
    print(f"Allow Apostrophe in Filenames: {allow_apostrophe_in_filename}")
    if dry_run:
        print(f"Test File Limit (for dry run): {test_run_file_limit}")


    all_found_audio_files = filehandler.find_audio_files(music_folder_raw)
    print(f"Found {len(all_found_audio_files)} audio files in '{music_folder_raw}' (top level only).")

    audio_files_to_process = all_found_audio_files[:test_run_file_limit] if test_run_file_limit > 0 else all_found_audio_files
    if dry_run:
        print(f"DRY RUN active: Nothing will be moved or renamed.")
    
    if len(all_found_audio_files) > test_run_file_limit:
        print(f"Processing only the first {len(audio_files_to_process)} files for this test run.")
    else:
        print(f"Processing {len(audio_files_to_process)} files.")

    processed_count = 0
    for filepath in audio_files_to_process:
        processed_count += 1
        print(f"\n--- Processing file {processed_count}/{len(audio_files_to_process)}: {os.path.basename(filepath)} ---")

        print("  Running direct fpcalc test...")
        fpcalc_test_passed = metadatahandler.test_fpcalc_with_json_output(filepath) # Call the test function
        
        existing_meta = filehandler.get_existing_metadata(filepath)
        print(f"  [Local Tags] Raw: {existing_meta}")

        identified_meta = None
        source_of_meta = "None"

        # Priority 1: Use existing tags if they are complete enough (artist, title, album)
        if existing_meta.get('artist') and existing_meta.get('title') and existing_meta.get('album'):
            print(f"  [Decision] Sufficient metadata found in local tags. Prioritizing.")
            identified_meta = existing_meta.copy() # Use a copy
            identified_meta['source_comment'] = "Local Tags" # Add source comment
            source_of_meta = "Local Tags"
        else:
            print(f"  [Decision] Local tags insufficient (Artist: {existing_meta.get('artist')}, Title: {existing_meta.get('title')}, Album: {existing_meta.get('album')}).")

        # Priority 2: If local tags were insufficient, try AcoustID if fpcalc test passed
        if not identified_meta and fpcalc_test_passed:
            print(f"  Attempting AcoustID fingerprinting...")
            if not ACOUSTID_API_KEY:
                print("    ACOUSTID_API_KEY not set. Skipping AcoustID.")
            else:
                fingerprint_meta = metadatahandler.identify_song_fingerprint(filepath)
                if fingerprint_meta and fingerprint_meta.get('artist') and fingerprint_meta.get('title') and fingerprint_meta.get('album'):
                    identified_meta = fingerprint_meta
                    source_of_meta = "AcoustID/MusicBrainz"
                    print(f"    [AcoustID Result]: Artist: {identified_meta.get('artist')}, Title: {identified_meta.get('title')}, Album: {identified_meta.get('album')}")
                else:
                    print(f"    [AcoustID] Failed to get sufficient info (Artist, Title, Album) via fingerprinting. Result: {fingerprint_meta}")
        
        # Priority 3: If still no meta, try LLM (and verify with MusicBrainz)
        if not identified_meta:
            print(f"  Attempting LLM query on filename...")
            if not OPENAI_API_KEY: # Check for OpenAI key specifically if using OpenAI
                print("    OPENAI_API_KEY not set. Skipping LLM.")
            else:
                filename_no_ext = os.path.splitext(os.path.basename(filepath))[0]
                cleaned_for_llm = llmhandler.clean_filename_for_llm(filename_no_ext)
                if cleaned_for_llm:
                    llm_guess = llmhandler.query_llm_for_song_details(cleaned_for_llm)
                    if llm_guess and llm_guess.get('artist') and llm_guess.get('title'): # Album is desirable but not strictly required from LLM
                        print(f"    [LLM Suggestion]: {llm_guess}")
                        # Verify LLM guess with MusicBrainz
                        verified_llm_meta = metadatahandler.get_musicbrainz_details(
                            llm_guess['artist'],
                            llm_guess['title'],
                            llm_guess.get('album') 
                        )
                        if verified_llm_meta and verified_llm_meta.get('artist') and verified_llm_meta.get('title') and verified_llm_meta.get('album'):
                            identified_meta = verified_llm_meta
                            # Augment with LLM's track number if MB didn't provide one
                            if not identified_meta.get('tracknumber') and llm_guess.get('original_prefix_number'):
                                identified_meta['tracknumber'] = str(llm_guess['original_prefix_number']).zfill(2)
                            source_of_meta = "LLM via MusicBrainz"
                            print(f"    [LLM Verified by MusicBrainz]: Artist: {identified_meta.get('artist')}, Title: {identified_meta.get('title')}, Album: {identified_meta.get('album')}")
                        else:
                            print(f"    [LLM] Suggestion could not be reliably verified by MusicBrainz to get (Artist, Title, Album). Verified: {verified_llm_meta}")
                    else:
                        print(f"    [LLM] Could not provide a useful suggestion (Artist, Title) or failed.")
                else:
                    print(f"    [LLM] Filename too generic or empty after cleaning for LLM query.")

        # --- Post-identification processing ---
        if identified_meta and identified_meta.get('artist') and identified_meta.get('title') and identified_meta.get('album'):
            print(f"  [Final Meta Choice] Using data from: {source_of_meta}")
            
            # Ensure tracknumber is reasonable if present
            if 'tracknumber' in identified_meta and identified_meta['tracknumber']:
                try:
                    # Attempt to make it an int and zfill, handles cases like "1" -> "01"
                    identified_meta['tracknumber'] = str(int(str(identified_meta['tracknumber']))).zfill(2)
                except ValueError:
                    print(f"    Warning: Invalid track number '{identified_meta['tracknumber']}'. Clearing it.")
                    identified_meta['tracknumber'] = None # Or ""
            
            # If track number is still missing, try to extract from original filename as a last resort
            if not identified_meta.get('tracknumber'):
                original_filename_no_ext = os.path.splitext(os.path.basename(filepath))[0]
                match = re.match(r"^\s*(\d+)\s*[-._ ]+\s*(.*)", original_filename_no_ext)
                if match:
                    potential_track_num = match.group(1).zfill(2)
                    identified_meta['tracknumber'] = potential_track_num
                    print(f"    Extracted track number '{potential_track_num}' from original filename as fallback.")

            print(f"  [Proposed Metadata For Action]: {identified_meta}")

            new_filepath_after_move = filehandler.rename_and_move_track(
                filepath, 
                identified_meta, 
                organized_music_root, 
                dry_run=dry_run,
                allow_apostrophe_in_filename=allow_apostrophe_in_filename
            )

            if new_filepath_after_move and (dry_run or os.path.exists(new_filepath_after_move)):
                filehandler.update_tags(new_filepath_after_move, identified_meta, dry_run=dry_run)
            elif not new_filepath_after_move and not dry_run:
                print(f"  Skipping tag update for {os.path.basename(filepath)} as its primary organization failed or it was moved to 'reviewed'.")
            # Optional: A warning if dry_run is false, new_filepath_after_move is set, but the file isn't there.
            elif new_filepath_after_move and not dry_run and not os.path.exists(new_filepath_after_move):
                print(f"  [Tag Update Warning] Proposed new path {new_filepath_after_move} does not exist. Skipping tag update.")

        else: # This 'else' corresponds to: if NOT (identified_meta and artist and title and album)
            print(f"  [Failure] Could not obtain sufficient metadata (Artist, Title, Album) for {os.path.basename(filepath)} from any source.")
            if identified_meta: print(f"    Partially identified meta was: {identified_meta}")
            
            # If all identification fails, move to 'reviewed' folder if not dry_run
            if not dry_run:
                reviewed_dir_fallback = os.path.join(organized_music_root, "reviewed")
                try:
                    os.makedirs(reviewed_dir_fallback, exist_ok=True)
                    original_filename = os.path.basename(filepath)
                    reviewed_filepath_fallback = os.path.join(reviewed_dir_fallback, original_filename)

                    counter = 1
                    original_reviewed_filepath_fb = reviewed_filepath_fallback
                    while os.path.exists(reviewed_filepath_fallback): # Avoid overwriting
                        name, ext = os.path.splitext(original_filename)
                        reviewed_filepath_fallback = os.path.join(reviewed_dir_fallback, f"{name}_{counter}{ext}")
                        counter += 1
                    if original_reviewed_filepath_fb != reviewed_filepath_fallback:
                         print(f"    WARNING: File '{os.path.basename(original_reviewed_filepath_fb)}' already in reviewed. Renaming to '{os.path.basename(reviewed_filepath_fallback)}'.")
                    
                    shutil.move(filepath, reviewed_filepath_fallback)
                    print(f"    MOVED TO REVIEWED: '{original_filename}' moved to '{reviewed_filepath_fallback}' due to failure in all metadata identification stages.")
                except Exception as e_review_ident_fail:
                    print(f"    ERROR moving '{os.path.basename(filepath)}' to reviewed folder after all identification failed: {e_review_ident_fail}")
            else: # dry_run is True
                print(f"    Dry run: Would move '{os.path.basename(filepath)}' to 'reviewed' folder due to failure in all metadata identification stages.")


    end_time = time.time()
    elapsed_time = end_time - start_time
    minutes, seconds = divmod(elapsed_time, 60)

    print(f"\n--- Processing complete for {len(audio_files_to_process)} files in {int(minutes)} and {seconds:.2f} seconds. ---")
    # ... (final summary print statements) ...

if __name__ == "__main__":
    # Ensure environment variables for API keys and paths are set before running.
    # Example:
    # export MUSIC_PATH="/path/to/unorganized_music"
    # export ORGANIZED_MUSIC_ROOT="/path/to/organized_music_library" # Can be same as MUSIC_PATH
    # export ACOUSTID_API_KEY="your_acoustid_key"
    # export OPENAI_API_KEY="your_openai_key"
    # export DRY_RUN="true" # or "false"
    # export TEST_FILE_COUNT="5"
    # export ALLOW_APOSTROPHE_FILENAME="true" # or "false"
    # export MB_APP_NAME="MyCoolMusicSorter"
    # export MB_APP_VERSION="1.0"
    # export MB_APP_CONTACT="me@example.com"
    main()


