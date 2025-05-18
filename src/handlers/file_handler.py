import os
import shutil
import re


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
    try:
        if filepath.lower().endswith('.mp3'):
            audio = EasyID3(filepath)
        elif filepath.lower().endswith('.flac'):
            audio = FLAC(filepath)
        elif filepath.lower().endswith('.m4a'):
            audio = MP4(filepath)
        else:
            return {} # Or handle other types

        metadata = {}
        if 'artist' in audio:
            metadata['artist'] = audio['artist'][0]
        if 'title' in audio:
            metadata['title'] = audio['title'][0]
        if 'album' in audio:
            metadata['album'] = audio['album'][0]
        if 'tracknumber' in audio:
            metadata['tracknumber'] = audio['tracknumber'][0].split('/')[0] # Get just the track number
        return metadata
    except Exception as e:
        print(f"Error reading metadata for {filepath}: {e}")
        return {}


def sanitize_filename(filename):
    # Remove invalid characters for filenames
    name = re.sub(r'[\\/*?:"<>|]', "", filename)
    # Replace other problematic characters (optional)
    name = name.replace("/", "-") # Example
    return name.strip()


def rename_track(current_filepath, corrected_metadata, dry_run=True):
    if not corrected_metadata or not corrected_metadata.get('artist') or not corrected_metadata.get('title'):
        print(f"Skipping rename for {current_filepath}, insufficient metadata.")
        return

    artist = sanitize_filename(corrected_metadata['artist'])
    title = sanitize_filename(corrected_metadata['title'])
    tracknum = corrected_metadata.get('tracknumber')
    album = corrected_metadata.get('album') # Optional

    _, ext = os.path.splitext(current_filepath)
    new_filename_parts = []

    if tracknum:
        new_filename_parts.append(str(tracknum).zfill(2)) # Pad to two digits

    new_filename_parts.append(artist)
    new_filename_parts.append(title)

    # Optional: Add album to filename
    # if album:
    # new_filename_parts.append(sanitize_filename(album))

    new_filename = " - ".join(new_filename_parts) + ext
    directory = os.path.dirname(current_filepath)
    new_filepath = os.path.join(directory, new_filename)

    if current_filepath == new_filepath:
        print(f"Filename already correct for: {current_filepath}")
        return

    print(f"Current: {current_filepath}")
    print(f"New:     {new_filepath}")

    if not dry_run:
        try:
            # Ensure the new filename isn't already taken by a *different* file
            if os.path.exists(new_filepath):
                print(f"WARNING: Target filename {new_filepath} already exists. Skipping rename.")
                # Or implement logic for appending a number, e.g., (1)
            else:
                shutil.move(current_filepath, new_filepath)
                print("Renamed successfully.")
        except Exception as e:
            print(f"Error renaming {current_filepath} to {new_filepath}: {e}")
    else:
        print("Dry run: No changes made.")
    return new_filepath # Return the new path for potential metadata update


def update_tags(filepath, corrected_metadata):
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
        elif filepath.lower().endswith('.flac'):
            audio = FLAC(filepath)
            if corrected_metadata.get('artist'): audio['ARTIST'] = corrected_metadata['artist']
            if corrected_metadata.get('title'): audio['TITLE'] = corrected_metadata['title']
            if corrected_metadata.get('album'): audio['ALBUM'] = corrected_metadata['album']
            if corrected_metadata.get('tracknumber'): audio['TRACKNUMBER'] = str(corrected_metadata['tracknumber'])
        elif filepath.lower().endswith('.m4a'):
            audio = MP4(filepath)
            # MP4 tags are often like '\xa9ART' (artist), '\xa9nam' (title), '\xa9alb' (album), 'trkn' (track number as a tuple)
            if corrected_metadata.get('artist'): audio['\xa9ART'] = corrected_metadata['artist']
            if corrected_metadata.get('title'): audio['\xa9nam'] = corrected_metadata['title']
            if corrected_metadata.get('album'): audio['\xa9alb'] = corrected_metadata['album']
            if corrected_metadata.get('tracknumber'):
                # May also need total tracks for the tuple (track, total_tracks)
                audio['trkn'] = [(int(corrected_metadata['tracknumber']), 0)]


        if audio:
            audio.save()
            print(f"Updated tags for: {filepath}")
    except Exception as e:
        print(f"Error updating tags for {filepath}: {e}")    