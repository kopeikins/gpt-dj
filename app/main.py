import os
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles

from clients.spotify_client import SpotifyClient
from models.api import TracksResponse, TrackTitleList, TrackURIList

bearer_scheme = HTTPBearer()


def ensure_token_passed(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    if credentials.scheme != "Bearer" or not credentials.credentials:
        raise HTTPException(
            status_code=401, detail="Invalid or missing access token")
    return credentials.credentials


def get_spotify_client(access_token: str = Depends(ensure_token_passed)):
    return SpotifyClient(access_token)


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get('/favicon.ico', include_in_schema=False)
async def favicon():
    return FileResponse("static/favicon.ico")


@app.get("/.well-known/ai-plugin.json")
def read_plugin_config():
    if os.environ.get('GPTDJ_ENV') == 'prod':
        return FileResponse("static/ai-plugin.json")
    else:
        return FileResponse("static/ai-plugin-dev.json")


@app.get("/")
def read_root():
    return {"Hello": "World"}


@app.get("/playlists/{playlist_id}/tracks", response_model=TracksResponse)
def get_tracks_from_playlist(playlist_id: str, spotify: Annotated[str, Depends(get_spotify_client)]):
    tracks = spotify.get_songs_from_playlist(playlist_id)

    return tracks


@app.get("/playlist")
def find_playlist_by_name(name: str, spotify: Annotated[str, Depends(get_spotify_client)]):
    user_id = spotify.get_my_user_id()
    playlist = spotify.find_playlist(name, user_id)
    if playlist:
        return {'playlist_id': playlist['id']}
    else:
        return {'playlist_id': None}


@app.post("/playlists")
def create_playlist(name: str, public: str, spotify: Annotated[str, Depends(get_spotify_client)]):
    user_id = spotify.get_my_user_id()
    # Try to find playlist with the same name
    playlist = spotify.find_playlist(name, user_id)
    if not playlist:
        print("Creating playlist")
        playlist_id = spotify.create_playlist(user_id, name, public)
    else:
        print(f"Playlist '{name}' already exists: id={playlist['id']}")
        playlist_id = playlist['id']

    return {"playlist_id": playlist_id}


@app.post("/playlists/{playlist_id}/tracks")
def add_tracks(playlist_id: str, track_list: TrackTitleList, spotify: Annotated[str, Depends(get_spotify_client)]):
    tracks_uris = []
    for title in track_list.titles:
        tracks = spotify.search_track(title, limit=10)
        if len(tracks) > 0:
            tracks_uris.append(tracks[0]['uri'])
        else:
            print(f'No tracks found for {title}')

    spotify.add_songs_to_playlist(playlist_id, tracks_uris)
    return {'playlist_id': playlist_id, 'song_uris': tracks_uris}


# For some reason ChatGPT never does DELETE request, so using POST here.
@app.post("/playlists/{playlist_id}/tracks/delete")
def delete_tracks(playlist_id: str, track_uris: TrackURIList, spotify: Annotated[str, Depends(get_spotify_client)]):
    spotify.remove_songs_from_playlist(playlist_id, track_uris.track_uris)
    return {'playlist_id': playlist_id, 'removed_track_uris': track_uris.track_uris}
