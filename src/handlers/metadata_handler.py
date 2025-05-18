from dotenv import load_dotenv
import os
import acoustid
import musicbrainzngs

load_dotenv()


# Add other formats if needed
from mutagen.easyid3 import EasyID3
from mutagen.flac import FLAC
from mutagen.mp4 import MP4

ACOUSTID_API_KEY = os.getenv("ACOUSTID_USER_API_KEY")
# MusicBrainz: Set a descriptive user agent for your app
musicbrainzngs.set_useragent("music-folder-organizer", "1.0", "cjeffords831@gmail.com")


def identify_song_fingerprint(filepath):
    try:
        results = acoustid.match(ACOUSTID_API_KEY, filepath)
        for score, recording_id, title, artist_name in results:
            if score > 0.7: # Confidence threshold
                print(f"Identified via AcoustID: {artist_name} - {title} (Recording ID: {recording_id})")
                # You can then use recording_id with MusicBrainz for more details
                try:
                    recording = musicbrainzngs.get_recording_by_id(recording_id,
                                                                   includes=["artists", "releases"])
                    # Extract detailed info here
                    # For example:
                    if recording.get('recording'):
                        mb_title = recording['recording'].get('title', title)
                        mb_artist = ""
                        if recording['recording'].get('artist-credit'):
                            mb_artist = recording['recording']['artist-credit'][0]['artist']['name']

                        # Try to find release and track number
                        track_num = None
                        album_title = None
                        if recording['recording'].get('release-list'):
                            # This part can get complex as a recording can be on many releases
                            # You might pick the first one or try to find the most relevant
                            release = recording['recording']['release-list'][0]
                            album_title = release.get('title')
                            if release.get('medium-list'):
                                for medium in release['medium-list']:
                                    if medium.get('track-list'):
                                        for track in medium['track-list']:
                                            if track.get('recording', {}).get('id') == recording_id:
                                                track_num = track.get('number')
                                                break
                                    if track_num: break
                        return {"artist": mb_artist or artist_name, "title": mb_title or title, "album": album_title, "tracknumber": track_num}
                except musicbrainzngs.WebServiceError as e:
                    print(f"MusicBrainz error for {recording_id}: {e}")
                return {"artist": artist_name, "title": title} # Fallback
        return None
    except acoustid.NoBackendError:
        print("Chromaprint utility (fpcalc) not found or not in PATH.")
        return None
    except Exception as e:
        print(f"AcoustID error for {filepath}: {e}")
        return None

def get_musicbrainz_details(artist_guess, title_guess, album_guess=None):
    try:
        # Construct a query. The more info you have, the better.
        query = f'artist:"{artist_guess}" recording:"{title_guess}"'
        if album_guess:
            query += f' release:"{album_guess}"'

        result = musicbrainzngs.search_recordings(query=query, limit=5) # Get a few results

        if result['recording-list']:
            # You might need logic to pick the best match from the list
            # For simplicity, taking the first one
            best_match = result['recording-list'][0]
            # print(f"MusicBrainz best match: {best_match}")

            corrected_title = best_match.get('title', title_guess)
            corrected_artist = title_guess # Default
            if best_match.get('artist-credit'):
                corrected_artist = best_match['artist-credit'][0]['artist']['name']

            # Getting album and track number is more involved as a recording can be on multiple releases
            album_title = album_guess
            track_number = None

            if best_match.get('release-list'):
                # Try to find a release that matches album_guess or just pick one
                # This logic can be significantly improved
                release_info = best_match['release-list'][0] # Simplistic choice
                album_title = release_info.get('title', album_title)
                if release_info.get('medium-list'):
                    for medium in release_info['medium-list']:
                        for track in medium.get('track-list', []):
                            # Check if this track in the release is our recording
                            if track.get('recording', {}).get('id') == best_match.get('id'):
                                track_number_str = track.get('number')
                                if track_number_str:
                                    track_number = track_number_str.zfill(2) # Pad with zero if needed
                                break
                        if track_number: break
            return {
                "artist": corrected_artist,
                "title": corrected_title,
                "album": album_title,
                "tracknumber": track_number
            }
        return None
    except musicbrainzngs.WebServiceError as e:
        print(f"MusicBrainz search error: {e}")
        return None
    except Exception as e:
        print(f"Error in get_musicbrainz_details: {e}")
        return None
