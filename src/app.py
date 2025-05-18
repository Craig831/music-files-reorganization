import os
from dotenv import load_dotenv
import handlers.file_handler as filehandler
import handlers.metadata_handler as metadatahandler
import handlers.llm_handler as llmhandler

load_dotenv()

def main():
    test_run_file_limit = int(os.getenv("TEST_FILE_COUNT"))
    music_folder = os.getenv("MUSIC_PATH")
    dry_run = True # !!! SET TO False TO ACTUALLY RENAME/RETAG !!!
                   # ALWAYS test with dry_run=True first!

    all_audio_files = filehandler.find_audio_files(music_folder)
    print(f"Found {len(all_audio_files)} audio files.")

    audio_files_to_process = all_audio_files[:test_run_file_limit] if dry_run else all_audio_files

    if dry_run and len(all_audio_files) > test_run_file_limit:
        print(f"DRY RUN active: Processing only the first {len(audio_files_to_process)} files for this test run.")
    else:
        print(f"Processing {len(audio_files_to_process)} files.")

    for filepath in audio_files_to_process:
        print(f"\nProcessing: {filepath}")
        filename_only = os.path.basename(filepath)
        filename_no_ext = os.path.splitext(filename_only)[0]

        # 1. Try existing metadata
        existing_meta = filehandler.get_existing_metadata(filepath)
        print(f"  Existing Tags: {existing_meta}")

        # 2. Attempt identification
        identified_meta = None

        # Strategy:
        # a) If good existing tags, try to verify/complete with MusicBrainz
        if existing_meta.get('artist') and existing_meta.get('title'):
            print("  Attempting MusicBrainz lookup with existing tags...")
            verified_meta = metadatahandler.get_musicbrainz_details(existing_meta['artist'],
                                                    existing_meta['title'],
                                                    existing_meta.get('album'))
            if verified_meta:
                identified_meta = verified_meta
                print(f"  MusicBrainz (from tags): {identified_meta}")


        # b) If not enough from tags or verification failed, try fingerprinting
        if not identified_meta:
            print("  Attempting AcoustID fingerprinting...")
            fingerprint_meta = metadatahandler.identify_song_fingerprint(filepath)
            if fingerprint_meta:
                identified_meta = fingerprint_meta
                print(f"  AcoustID result: {identified_meta}")
                # Optionally, refine further with MusicBrainz using this new info
                # if fingerprint_meta.get('artist') and fingerprint_meta.get('title'):
                # refined_meta = get_musicbrainz_details(fingerprint_meta['artist'], fingerprint_meta['title'])
                # if refined_meta: identified_meta = refined_meta


        # c) If still no good match, try LLM on the filename
        if not identified_meta:
            print("  Attempting LLM query on filename...")
            llm_guess = llmhandler.query_llm_for_song_details(filename_no_ext)
            if llm_guess and llm_guess.get('artist') and llm_guess.get('title'):
                print(f"  LLM Suggestion: {llm_guess}")
                # VERY IMPORTANT: LLM output can be unreliable.
                # ALWAYS try to verify it with MusicBrainz.
                verified_llm_meta = metadatahandler.get_musicbrainz_details(llm_guess['artist'],
                                                            llm_guess['title'])
                if verified_llm_meta:
                    identified_meta = verified_llm_meta
                    # If LLM provided a track number and MusicBrainz didn't, consider keeping it.
                    if not identified_meta.get('tracknumber') and llm_guess.get('original_prefix_number'):
                        identified_meta['tracknumber'] = llm_guess['original_prefix_number']
                    print(f"  MusicBrainz (from LLM guess): {identified_meta}")
                else:
                    print("  LLM guess could not be reliably verified by MusicBrainz.")
            else:
                print("  LLM could not provide a useful suggestion or failed.")


        # 3. If we have corrected metadata, rename and retag
        if identified_meta:
            # Fill in missing pieces if possible (e.g., album from existing if not found)
            if not identified_meta.get('album') and existing_meta.get('album'):
                identified_meta['album'] = existing_meta['album']
            # If track number is missing, try to extract from original filename if it looks like a prefix
            if not identified_meta.get('tracknumber'):
                match = re.match(r"^\s*(\d+)\s*[-._ ]+\s*(.*)", filename_no_ext)
                if match:
                    potential_track_num = match.group(1)
                    identified_meta['tracknumber'] = potential_track_num
                    print(f"  Extracted potential track number '{potential_track_num}' from original filename.")


            print(f"  Final Proposed Metadata: {identified_meta}")
            new_filepath = filehandler.rename_track(filepath, identified_meta, dry_run=dry_run)
            if not dry_run and new_filepath: # If renamed, update tags on the new file
                filehandler.update_tags(new_filepath, identified_meta)
            elif not dry_run and not new_filepath: # If not renamed but metadata is good
                filehandler.update_tags(filepath, identified_meta) # Update tags on original file
            elif dry_run:
                print(f"  Dry run: Would update tags for: {filepath} with {identified_meta}")

        else:
            print(f"  Could not confidently identify/correct metadata for {filename_only}")

    print("\nProcessing complete.")

if __name__ == "__main__":
    main()


