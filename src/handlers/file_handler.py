import os
import shutil
import re

from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3NoHeaderError
from mutagen.mp3 import HeaderNotFoundError


def find_audio_files(folder_path):
    audio_files = []
    try:
        for item_name in os.listdir(folder_path):
            item_path = os.path.join(folder_path, item_name)
            # check if it's a file i want to process
            if os.path.isfile(item_path) and item_name.lower().endswith(('.mp3')):
                audio_files.append(item_path)

        # Uncomment this if you want to search recursively
        # for root, _, files in os.walk(folder_path):
        #     for file in files:
        #         # Add more extensions as needed
        #         # if file.lower().endswith(('.mp3', '.flac', '.m4a', '.ogg')):
        #         if file.lower().endswith(('.mp3')):
        #             audio_files.append(os.path.join(root, file))

    except FileNotFoundError:
        print(f"Error: The folder '{folder_path}' was not found.")
        return [] # Return an empty list if folder doesn't exist
    except PermissionError:
        print(f"Error: Permission denied to access the folder '{folder_path}'.")
        return [] # Return an empty list if permission is denied        
    return audio_files


def get_existing_metadata(filepath):
    """
    Extracts existing metadata (artist, title, album, tracknumber, year) from an audio file.
    """    
    metadata = {}
    filename_log = os.path.basename(filepath)
    try:
        file_ext = os.path.splitext(filepath)[1].lower()
        audio = None
        if file_ext == '.mp3':
            try:
                audio = EasyID3(filepath)
            except ID3NoHeaderError:
                print(f"  [Tags] No ID3 header found for MP3: {filename_log}")
                return {}
            except HeaderNotFoundError:
                print(f"  [Tags] MP3 header not found for: {filename_log}")
                return {}
        # elif filepath.lower().endswith('.flac'):
        #     audio = FLAC(filepath)
        # elif filepath.lower().endswith('.m4a'):
        #     audio = MP4(filepath)
        else:
            print(f"  [Tags] Unsupported file type for metadata extraction: {filename_log}")
            return {} # Or handle other types

        if 'artist' in audio: metadata['artist'] = audio['artist'][0]
        if 'title' in audio: metadata['title'] = audio['title'][0]
        if 'album' in audio: metadata['album'] = audio['album'][0]
        if 'tracknumber' in audio: metadata['tracknumber'] = audio['tracknumber'][0].split('/')[0] # Get just the track number
        if 'date' in audio: metadata['year'] = str(audio['date'][0])[:4]
        elif 'originaldate' in audio: metadata['year'] = str(audio['originaldate'][0])[:4] # TDRC (ID3v2.4) vs TYER (ID3v2.3)
        
        return metadata
    except Exception as e:
        print(f"  [Tags] Error reading metadata for {filename_log}: {e} (type: {type(e).__name__})")
        return {}

def format_artist_for_directory(artist_name):
    """
    Checks if artist_name is in "Last, First" or "Last,First" format and reorders it.
    Returns "First Last" or the original name if not in that format.
    """
    if not artist_name:
        return "Unknown Artist" # Or whatever default you prefer

    # Regex to match "Lastname, Firstname" with optional space after comma
    # It captures "Lastname" and "Firstname"
    # Allows for multi-part last names or first names before/after the comma
    match = re.match(r"([^,]+),\s*([^,]+)", artist_name.strip())
    if match:
        last_name = match.group(1).strip()
        first_name = match.group(2).strip()
        # Check if both parts are non-empty to avoid weird reordering of ", Artist" or "Artist ,"
        if last_name and first_name:
            formatted_name = f"{first_name} {last_name}"
            print(f"    [Artist Format] Reordered '{artist_name}' to '{formatted_name}' for directory.")
            return formatted_name
    return artist_name # Return original if no match or parts are empty

def sanitize_filename_char(char, allow_apostrophe=False):
    """ Helper to decide if a character is kept or replaced. """
    if char.isalnum() or char in ' .-()[]': # Basic allowed chars
        return char
    if allow_apostrophe:
        if char == "'":
            return char
        if char in ['`', '´', '‘', '’']:
            return "'"
    return '_' # Replace other special characters with underscore

def sanitize_filename(name, allow_apostrophe_in_filename=False):
    """
    Sanitizes a string to be a valid filename component.
    Replaces most special characters with underscores.
    Apostrophes can be optionally preserved.
    """
    if not name:
        return "Unknown" # Default for empty names
    
    # Replace slashes first as they are path separators
    name = name.replace('/', '-').replace('\\', '-')
    
    # Preserve apostrophes if flag is true, otherwise they'll be caught by the generic rule
    sanitized_name = "".join(sanitize_filename_char(char, allow_apostrophe_in_filename) for char in name)
    
    # Replace multiple underscores/spaces with a single one and strip leading/trailing
    sanitized_name = re.sub(r'[_\s]{2,}', '_', sanitized_name).strip('._ ')
    return sanitized_name if sanitized_name else "Unknown"


def rename_and_move_track(current_filepath, corrected_metadata, root_music_folder, dry_run=True, allow_apostrophe_in_filename=False):
    """
    Renames the track and moves it into an Artist/Album directory structure.
    If that fails (and not dry_run), moves the original file to a 'reviewed' subfolder.
    Returns the new filepath of the successfully organized file, or None if the primary organization failed.
    """
    raw_artist = corrected_metadata.get('artist')
    raw_album = corrected_metadata.get('album')
    raw_title = corrected_metadata.get('title')
    current_filename_log = os.path.basename(current_filepath)

    # Define the 'reviewed' directory path
    reviewed_dir = os.path.join(root_music_folder, "reviewed")

    if not (raw_artist and raw_title and raw_album):
        print(f"  [Rename] Insufficient metadata (artist, title, or album missing) for {current_filename_log}. Skipping primary organization.")
        if not dry_run:
            try:
                os.makedirs(reviewed_dir, exist_ok=True)
                reviewed_filepath = os.path.join(reviewed_dir, current_filename_log)
                
                # Avoid overwriting in reviewed folder if file with same name already exists
                counter = 1
                original_reviewed_filepath = reviewed_filepath
                while os.path.exists(reviewed_filepath):
                    name, ext = os.path.splitext(current_filename_log)
                    reviewed_filepath = os.path.join(reviewed_dir, f"{name}_{counter}{ext}")
                    counter += 1
                if original_reviewed_filepath != reviewed_filepath:
                     print(f"    WARNING: File '{os.path.basename(original_reviewed_filepath)}' already in reviewed. Renaming to '{os.path.basename(reviewed_filepath)}'.")


                shutil.move(current_filepath, reviewed_filepath)
                print(f"    MOVED TO REVIEWED: '{current_filename_log}' moved to '{reviewed_filepath}' due to insufficient metadata.")
            except Exception as e_review:
                print(f"    ERROR moving '{current_filename_log}' to reviewed folder: {e_review}")
        else:
            print(f"    Dry run: Would move '{current_filename_log}' to '{reviewed_dir}' due to insufficient metadata.")
        return None # Primary organization failed

    # --- Proceed with primary organization ---
    formatted_artist_for_dir = format_artist_for_directory(raw_artist)
    s_artist_dir = sanitize_filename(formatted_artist_for_dir, allow_apostrophe_in_filename=False)
    s_album_dir = sanitize_filename(raw_album, allow_apostrophe_in_filename=False)

    # use the raw_title which may have an apostrophy if allow_apostrophe_in_filename is True
    s_title_file = sanitize_filename(raw_title, allow_apostrophe_in_filename=allow_apostrophe_in_filename)
    print(f"    DEBUG: Raw title for sanitize: '{raw_title}', Sanitized title for file: '{s_title_file}', Allow apostrophe: {allow_apostrophe_in_filename}")

    raw_tracknumber = corrected_metadata.get('tracknumber')
    tracknum_str = ""
    if raw_tracknumber is not None and str(raw_tracknumber).strip():
        try:
            tracknum_str = str(int(float(str(raw_tracknumber)))).zfill(2) 
        except ValueError:
            print(f"    Warning: Invalid track number format '{raw_tracknumber}'. Omitting from filename.")
            tracknum_str = ""

    _, ext = os.path.splitext(current_filepath)
    new_filename_parts = [part for part in [tracknum_str, s_title_file] if part and str(part).strip()] # Ensure parts are not empty/whitespace
    
    if not new_filename_parts: # If both tracknum and title are empty after processing
        new_track_filename = f"{sanitize_filename(current_filename_log, False)}{ext}" # Sanitize original name as fallback
        print(f"    Warning: Track number and title are empty. Using sanitized original filename: {new_track_filename}")
    else:
        new_track_filename = " - ".join(new_filename_parts) + ext

    target_artist_album_dir = os.path.join(root_music_folder, s_artist_dir, s_album_dir)
    new_filepath = os.path.join(target_artist_album_dir, new_track_filename)
    relative_new_path_log = os.path.join(s_artist_dir, s_album_dir, new_track_filename)

    if current_filepath == new_filepath:
        print(f"  [Rename] Filename and location already correct for: {current_filename_log}")
        return current_filepath # Still return path for potential tag update

    print(f"  [Rename] Current: {current_filepath}")
    print(f"  [Rename] Proposed New Path for primary organization: {new_filepath}")

    if not dry_run:
        try:
            os.makedirs(target_artist_album_dir, exist_ok=True)
            # print(f"    Ensured directory exists: {target_artist_album_dir}") # Can be verbose

            if os.path.exists(new_filepath):
                print(f"    WARNING: Target path {new_filepath} already exists (primary organization). Skipping.")
                # Fallback to moving to 'reviewed'
                try:
                    os.makedirs(reviewed_dir, exist_ok=True)
                    reviewed_filepath = os.path.join(reviewed_dir, current_filename_log)
                    
                    counter = 1
                    original_reviewed_filepath = reviewed_filepath
                    while os.path.exists(reviewed_filepath):
                        name, ext_rev = os.path.splitext(current_filename_log)
                        reviewed_filepath = os.path.join(reviewed_dir, f"{name}_{counter}{ext_rev}")
                        counter += 1
                    if original_reviewed_filepath != reviewed_filepath:
                         print(f"    WARNING: File '{os.path.basename(original_reviewed_filepath)}' already in reviewed. Renaming to '{os.path.basename(reviewed_filepath)}'.")

                    shutil.move(current_filepath, reviewed_filepath)
                    print(f"    MOVED TO REVIEWED: '{current_filename_log}' moved to '{reviewed_filepath}' because primary target existed.")
                except Exception as e_review_alt:
                    print(f"    ERROR moving '{current_filename_log}' to reviewed folder after primary target existed: {e_review_alt}")
                return None # Primary organization failed

            shutil.move(current_filepath, new_filepath)
            print(f"    SUCCESS: Moved '{current_filename_log}' to '{relative_new_path_log}'")
            return new_filepath # Success for primary organization
        except Exception as e_primary:
            print(f"    ERROR during primary rename/move of '{current_filename_log}' to '{relative_new_path_log}': {e_primary}")
            # Fallback to moving to 'reviewed'
            try:
                os.makedirs(reviewed_dir, exist_ok=True)
                reviewed_filepath = os.path.join(reviewed_dir, current_filename_log)
                
                counter = 1
                original_reviewed_filepath = reviewed_filepath
                while os.path.exists(reviewed_filepath):
                    name, ext_rev = os.path.splitext(current_filename_log)
                    reviewed_filepath = os.path.join(reviewed_dir, f"{name}_{counter}{ext_rev}")
                    counter += 1
                if original_reviewed_filepath != reviewed_filepath:
                     print(f"    WARNING: File '{os.path.basename(original_reviewed_filepath)}' already in reviewed. Renaming to '{os.path.basename(reviewed_filepath)}'.")

                shutil.move(current_filepath, reviewed_filepath)
                print(f"    MOVED TO REVIEWED: '{current_filename_log}' moved to '{reviewed_filepath}' after primary organization error.")
            except Exception as e_review_final:
                print(f"    CRITICAL ERROR: Failed primary organization AND failed to move '{current_filename_log}' to reviewed folder: {e_review_final}")
            return None # Primary organization failed
    else: # dry_run is True
        print(f"    Dry run: Would create directory '{target_artist_album_dir}' (if needed for primary organization).")
        print(f"    Dry run: Would move '{current_filename_log}' to '{relative_new_path_log}'.")
        # In dry run, we still return the proposed new_filepath for tag update simulation
        return new_filepath


def update_tags(filepath, corrected_metadata, dry_run=True):
    """
    Updates the metadata tags of the audio file.
    The artist tag should be stored in the standard format (e.g. "Cash, Johnny" or "Johnny Cash" as per original/MusicBrainz).
    The `format_artist_for_directory` is only for directory naming.
    """
    if not filepath or not os.path.exists(filepath):
        print(f"  [Tag Update] File not found for tagging: {filepath}. Skipping.")
        return

    filename_log = os.path.basename(filepath)

    # Use the artist name as it is in corrected_metadata for tagging, not the directory-formatted one.
    artist_for_tags = corrected_metadata.get('artist') 
    title_for_tags = corrected_metadata.get('title')
    album_for_tags = corrected_metadata.get('album')
    tracknum_for_tags = corrected_metadata.get('tracknumber')
    year_for_tags = corrected_metadata.get('year')

    print(f"  [Tag Update] Preparing to update tags for: {filename_log} with Artist='{artist_for_tags}', Title='{title_for_tags}', Album='{album_for_tags}' etc.")

    if dry_run:
        print(f"    Dry run: Would update tags for '{filename_log}'.")
        return

    try:
        audio = None
        file_ext = os.path.splitext(filepath)[1].lower()

        if file_ext == '.mp3':
            audio = EasyID3(filepath)
            if artist_for_tags: audio['artist'] = artist_for_tags
            if title_for_tags: audio['title'] = title_for_tags
            if album_for_tags: audio['album'] = album_for_tags
            if tracknum_for_tags: audio['tracknumber'] = str(tracknum_for_tags)
            if year_for_tags: audio['date'] = str(year_for_tags) # or originaldate
        
        if audio:
            audio.save()
            print(f"    SUCCESS: Tags updated for '{filename_log}'.")
        else:
            print(f"    No specific tag handling for {file_ext} in this version.")

    except Exception as e:
        print(f"    ERROR updating tags for {filename_log}: {e} (Type: {type(e).__name__})")

    """
    Updates the metadata tags of the audio file.
    The artist tag should be stored in the standard format (e.g. "Cash, Johnny" or "Johnny Cash" as per original/MusicBrainz).
    The `format_artist_for_directory` is only for directory naming.
    """
    if not filepath or not os.path.exists(filepath):
        print(f"  [Tag Update] File not found for tagging: {filepath}. Skipping.")
        return

    filename_log = os.path.basename(filepath)
    print(f"  [Tag Update] Preparing to update tags for: {filename_log} with {corrected_metadata}")

    if dry_run:
        print(f"    Dry run: Would update tags for '{filename_log}'.")
        return

    try:
        audio = None
        file_ext = os.path.splitext(filepath)[1].lower()

        if file_ext == '.mp3':
            audio = EasyID3(filepath)
            if corrected_metadata.get('artist'): audio['artist'] = corrected_metadata['artist']
            if corrected_metadata.get('title'): audio['title'] = corrected_metadata['title']
            if corrected_metadata.get('album'): audio['album'] = corrected_metadata['album']
            tn = corrected_metadata.get('tracknumber')
            # EasyID3 often stores total tracks too, e.g., "1/12".
            # If your corrected_metadata doesn't have total tracks, just save the number.
            if tn: audio['tracknumber'] = str(tn)
            if corrected_metadata.get('year'): audio['date'] = str(corrected_metadata['year'])

        elif file_ext == '.flac':
            audio = FLAC(filepath)
            # FLAC tags are case-sensitive and usually uppercase
            if corrected_metadata.get('artist'): audio['ARTIST'] = corrected_metadata['artist']
            if corrected_metadata.get('title'): audio['TITLE'] = corrected_metadata['title']
            if corrected_metadata.get('album'): audio['ALBUM'] = corrected_metadata['album']
            if corrected_metadata.get('tracknumber'): audio['TRACKNUMBER'] = str(corrected_metadata['tracknumber'])
            if corrected_metadata.get('year'): audio['DATE'] = str(corrected_metadata['year'])

        elif file_ext in ('.m4a', '.mp4'):
            audio = MP4(filepath)
            if corrected_metadata.get('artist'): audio['\xa9ART'] = corrected_metadata['artist']
            if corrected_metadata.get('title'): audio['\xa9nam'] = corrected_metadata['title']
            if corrected_metadata.get('album'): audio['\xa9alb'] = corrected_metadata['album']
            if corrected_metadata.get('tracknumber'):
                # MP4 track number can be a tuple (track, total_tracks).
                # If total_tracks isn't available, set it to 0.
                audio['trkn'] = [(int(corrected_metadata['tracknumber']), 0)]
            if corrected_metadata.get('year'): audio['\xa9day'] = str(corrected_metadata['year'])
        
        if audio:
            audio.save()
            print(f"    SUCCESS: Tags updated for '{filename_log}'.")
        else:
            print(f"    No specific tag handling for {file_ext} in this version.")

    except Exception as e:
        print(f"    ERROR updating tags for {filename_log}: {e} (Type: {type(e).__name__})")

    if not filepath or not os.path.exists(filepath): # Check if file still exists (it might have been renamed)
        print(f"File not found for tagging: {filepath}")
        return

    try:
        audio = None
        if filepath.lower().endswith('.mp3'):
            audio = EasyID3(filepath)
            if corrected_metadata.get('artist'): audio['artist'] = corrected_metadata['artist']
            if corrected_metadata.get('title'): audio['title'] = corrected_metadata['title']
            if corrected_metadata.get('album'): audio['album'] = corrected_metadata['album']
            if corrected_metadata.get('tracknumber'):
                # EasyID3 often stores total tracks too, e.g., "1/12"
                # You might need to fetch total tracks if you want to store it this way
                audio['tracknumber'] = str(corrected_metadata['tracknumber'])

        if audio:
            audio.save()
            print(f"Updated tags for: {filepath}")
    except Exception as e:
        print(f"Error updating tags for {filepath}: {e}")    