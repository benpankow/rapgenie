from bs4 import BeautifulSoup
from bs4 import Comment
import requests
import re
import string

CLIENT_ACCESS_TOKEN = 'yVydbD3rqBJNqJPRTDhqmWqm9Qc0YlpVpTmk0wnvaH1ptzq2YwyP_EWHEdfRgTI3'

GENIUS_URL = 'https://genius.com/'
API_GENIUS_URL = 'https://api.genius.com/'

API_SONG_BASE_URL = API_GENIUS_URL + 'songs/'
API_ARTISTS_BASE_URL = API_GENIUS_URL + 'artists/'

# Searches for a number of terms in a given string
# Returns a tuple with the first element the index of the first locate
# term, the second element the term itself
def _min_search(target_string, search_terms):
    lowest = -1
    best = None
    for term in search_terms:
        index = target_string.find(term)
        if index != -1 and (index < lowest or lowest == -1):
            lowest = index
            best = term
    return (lowest, best)

# Fetch song lyrics and metadata
def get_song_data(song):
    html_response = None
    json_response = None

    # Fetch song page, extract song id from page
    if song.url:
        html_response = _bs_spoof(song.url)
        id_base = html_response('meta', {'name' : 'newrelic-resource-path'})[0]['content']
        song_id = id_base[id_base.rfind('/') + 1:]
        song.song_id = song_id
        # Fetch API info
        json_response = _api_access(API_SONG_BASE_URL + song.song_id)

    # Fetch song API info, extract song url from page
    elif song.song_id:
        json_response = _api_access(API_SONG_BASE_URL + song.song_id)
        song.url = json_response['response']['song']['url']
        # Fetch song page
        html_response = _bs_spoof(song.url)

    if html_response != None and json_response != None:
        # Store song metadata (TODO: More)
        song.has_data = True
        song.title = json_response['response']['song']['title']
        song.artist = Artist.from_id(json_response['response']['song']['primary_artist']['id'])
        song.artist.name = json_response['response']['song']['primary_artist']['name']

        # Store song lyrics, in plaintext and html
        lyrics_html = html_response('div', {'class' : 'lyrics'})[0]
        song.lyrics = lyrics_html.text.strip()

        for tag in lyrics_html.findAll('a'):
            tag.replaceWithChildren()
        for tag in lyrics_html.findAll('p'):
            tag.replaceWithChildren()
        for tag in lyrics_html.findAll('div'):
            tag.replaceWithChildren()
        for elem in lyrics_html.children:
            if isinstance(elem, Comment):
                elem.extract()

        song.html_lyrics = str(lyrics_html)
# TODO
def process_song_fragments(song):
    song.has_fragments = True
    sections = []

    main_artist = song.artist.name
    other_artists = {}

    current_section = Section('Verse 1', main_artist)

    current_artist = main_artist

    current = song.html_lyrics

    current_tags = []

    to_look_for = ['[', '<i>', '</i>', '<b>', '</b>', '<em>', '</em>']

    #found = current.find('[')
    found_index, found_type = _min_search(current, to_look_for)

    while found_type:
        fragment = current[:found_index]
        fragment_text = BeautifulSoup(fragment, 'lxml').text
        if len(fragment_text.strip()) > 0:
            fragment_obj = Fragment(current_artist, fragment_text)
            if len(current_section.fragments) > 0 and current_section.fragments[-1].artist == fragment_obj.artist:
                current_section.fragments[-1].text += fragment_text
            else:
                current_section.fragments.append(fragment_obj)

        if (found_type == '['):
            if len(current_section.fragments) > 0:
                sections.append(current_section)

            current = current[found_index+1:]
            found2 = current.find(']')

            tag = current[:found2]
            end_name_index = tag.find(':')
            if end_name_index == -1:
                end_name_index = found2
            tag_name = tag[:end_name_index]

            artists_string = tag[end_name_index + 1:].strip()
            artists_string = artists_string.replace('&amp;', ',').replace('+', ',').replace(' and ', ',')

            tag_artists = [x.strip() for x in artists_string.split(',')]

            if len(tag_artists) == 0 or len(tag_artists[0]) == 0:
                for section in sections:
                    if section.name == tag_name:
                        tag_artists = section.artists

            main_artist = tag_artists[0]

            if len(main_artist) < 1:
                main_artist = song.artist.name

            current_artist = main_artist
            other_artists = {}

            look_for_parens = False

            for artist in tag_artists:
                artist_bs = BeautifulSoup(artist, 'lxml')
                if artist_bs.html and artist_bs.html.body:
                    tags = artist_bs.html.body.findAll(['b', 'i', 'em'])
                    artist_name = artist_bs.text
                    has_parens = False
                    if artist_name[0] == '(' and artist_name[-1] == ')':
                        artist_name = artist_name[1:-1]
                        has_parens = True
                        look_for_parens = True
                    if (tags and len(tags) > 0) or has_parens:
                        name = [tag.name for tag in tags]
                        if has_parens:
                            name += '('
                        name.sort()
                        other_artists[''.join(name)] = artist_name
                    else:
                        main_artist = artist_name
            if look_for_parens:
                to_look_for = ['[', '<i>', '</i>', '<b>', '</b>', '<em>', '</em>', '(', ')']
            else:
                to_look_for = ['[', '<i>', '</i>', '<b>', '</b>', '<em>', '</em>']
            current_section = Section(tag_name, [main_artist] + other_artists.values())

            current = current[found2 + 1:]
            found_index, found_type = _min_search(current, to_look_for)
        else:
            current = current[found_index + len(found_type):]
            processed_tag = found_type.replace('/', '').replace(')', '(')
            if '<' in processed_tag:
                processed_tag = processed_tag[1:-1]
            if (found_type.find('/') != -1 or found_type == ')'):
                current_tags.remove(processed_tag)
            else:
                current_tags.append(processed_tag)

            current_tags.sort()

            if len(current_tags) == 0:
                current_artist = main_artist
            elif ''.join(current_tags) in other_artists:
                current_artist = other_artists[''.join(current_tags)]
            else:
                for artist in other_artists:
                    print '> ', artist
                current_artist = 'Other'
            found_index, found_type = _min_search(current, to_look_for)

    fragment = current.strip()
    fragment_text = BeautifulSoup(fragment, 'lxml').text
    if len(fragment_text.strip()) > 0:
        fragment_obj = Fragment(current_artist, fragment_text)
        if len(current_section.fragments) > 0 and current_section.fragments[-1].artist == fragment_obj.artist:
            current_section.fragments[-1].text += fragment_text
        else:
            current_section.fragments.append(fragment_obj)

    if len(current_section.fragments) > 0:
        sections.append(current_section)

    song.sections = sections

# Load a given webpage's html contents into a BeautifulSoup object
def _bs_spoof(url):
    response = requests.get(url, headers = {'User-Agent': 'Mozilla/5.0'})
    return BeautifulSoup(response.text, 'lxml')

# Access the specific API url and return its JSON result
def _api_access(url):
    response = requests.get(url, headers = {'Authorization': 'Bearer ' + CLIENT_ACCESS_TOKEN, 'User-Agent': 'Mozilla/5.0'})
    return response.json()

# A fragment is a line or series of lines associated with an artist
# Contains an artist string (TODO object) and a small amount of text
class Fragment:
    def __init__(self, artist, text):
        self.artist = artist
        self.text = text

# A section is a portion of a song, such as an intro, hook, or verse
# A section has a title, a list of artists, and a series of enclosed fragments
class Section:
    def __init__(self, name, artists):
        self.artists = artists
        self.name = name
        self.fragments = []

# Unfinished, an artist class will eventually hold more info about an artist
# TODO
class Artist:
    @staticmethod
    def from_url(url):
        artist = Artist()
        artist.url = url
        return artist

    @staticmethod
    def from_id(artist_id):
        artist = Artist()
        artist.artist_id = str(artist_id)
        return artist

    def __init__(self):
        self.url = None
        self.artist_id = None
        self.has_data = False
        self.name = None

    def __str__(self):
        if self.has_data:
            return self.name + ' (' + self.url + ')'
        elif self.url:
            if self.name:
                return 'Unrequested artist ' + self.name + ' with URL ' + self.url
            return 'Unrequested artist with URL ' + self.url
        else:
            if self.name:
                return 'Unrequested artist ' + self.name + ' with ID ' + self.artist_id
            return 'Unrequested artist with ID ' + self.artist_id

# An instance of a song
# Can be created by ID or url, but does not contain information until data is
# requested from the api using song_obj.request()
class Song:
    @staticmethod
    def from_url(url):
        song = Song()
        song.url = url
        return song

    @staticmethod
    def from_id(song_id):
        song = Song()
        song.song_id = str(song_id)
        return song

    def __init__(self):
        self.url = None
        self.song_id = None
        self.has_data = False
        self.has_fragments = False
        self.sections = None

    def request(self):
        if not self.has_data:
            get_song_data(self)
        return self

    def parse(self):
        if not self.has_fragments:
            process_song_fragments(self)
        return self

    def __str__(self):
        if self.has_data:
            return self.title + ' (' + self.url + ')'
        elif self.url:
            return 'Unrequested song with URL ' + self.url
        else:
            return 'Unrequested song with ID ' + self.song_id


new_god_flow = Song.from_url('https://genius.com/A-ap-mob-frat-rules-lyrics')
new_god_flow.request().parse()

output = ''
for section in new_god_flow.sections:
    for fragment in section.fragments:
        output += fragment.artist + '\n' + fragment.text.replace('\n', ' ') + '\n\n'

with open('test.txt', 'w+') as f:
    f.write(output.encode('utf-8'))

'''
songs = [
    'https://genius.com/Brockhampton-heat-lyrics',
    'https://genius.com/Brockhampton-gold-lyrics',
    'https://genius.com/Brockhampton-star-lyrics',
    'https://genius.com/Brockhampton-boys-lyrics',
    'https://genius.com/Brockhampton-2pac-lyrics',
    'https://genius.com/Brockhampton-fake-lyrics',
    'https://genius.com/Brockhampton-bank-lyrics',
    'https://genius.com/Brockhampton-trip-lyrics',
    'https://genius.com/Brockhampton-swim-lyrics',
    'https://genius.com/Brockhampton-bump-lyrics',
    'https://genius.com/Brockhampton-cash-lyrics',
    'https://genius.com/Brockhampton-milk-lyrics',
    'https://genius.com/Brockhampton-face-lyrics',
    'https://genius.com/Brockhampton-waste-lyrics'
]

output = ''
artists = {}
for song_url in songs:
    song_obj = Song.from_url(song_url)
    song_obj.request().parse()

    for section in song_obj.sections:
        for fragment in section.fragments:
            if not fragment.artist.lower() in artists:
                artists[fragment.artist.lower()] = []
            artists[fragment.artist.lower()].append(fragment.text)

translate_table = dict((ord(char), None) for char in string.punctuation)

for artist in artists:
    output += artist + ':\n'
    a_str = ''
    for s in artists[artist]:
        output += s.strip() + '\n'
        a_str += s.strip()
    output += '\n\n'
    a_str = a_str.replace('-', ' ').lower().translate(translate_table)
    print artist, len(a_str.split())


with open('test.txt', 'w+') as f:
    f.write(output.encode('utf-8'))
'''