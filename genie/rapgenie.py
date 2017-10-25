import requests

GENIUS_URL = 'https://genius.com/'
API_GENIUS_URL = 'https://api.genius.com/'

API_SONG_BASE_URL = API_GENIUS_URL + 'songs/'
API_ARTISTS_BASE_URL = API_GENIUS_URL + 'artists/'
API_SEARCH_BASE_URL = API_GENIUS_URL + 'search?q='

class RapGenie:

    def __init__(self, client_access_token):
        self.client_access_token = client_access_token

    def song_from_url(self, song_url):
        song = Song(self)
        song.url = song_url
        return song

    def song_from_id(self, song_id):
        song = Song(self)
        song.song_id = str(song_id)
        return song

    def artist_from_url(self, artist_url):
        artist = Artist(self)
        artist.url = artist_url
        return artist

    def artist_from_id(self, artist_id):
        artist = Artist(self)
        artist.artist_id = str(artist_id)
        return artist

    def search(self, query):
        response =  self.api_access(API_SEARCH_BASE_URL + query)['response']['hits']
        for song in response:
            song_obj = self.song_from_id(song['result']['id'])
            song_obj.title = song['result']['title']
            yield song_obj

    # Access the specific API url and return its JSON result
    def api_access(self, url):
        response = requests.get(url, headers = {'Authorization': 'Bearer ' + self.client_access_token, 'User-Agent': 'Mozilla/5.0'})
        return response.json()
