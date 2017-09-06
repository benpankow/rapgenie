from bs4 import BeautifulSoup
from bs4 import Comment
import requests
import re
import string
from rapgenie_secret import CLIENT_ACCESS_TOKEN
import difflib

GENIUS_URL = 'https://genius.com/'
API_GENIUS_URL = 'https://api.genius.com/'

API_SONG_BASE_URL = API_GENIUS_URL + 'songs/'
API_ARTISTS_BASE_URL = API_GENIUS_URL + 'artists/'
API_SEARCH_BASE_URL = API_GENIUS_URL + 'search?q='

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

# Fetch song lyrics
def get_song_lyrics(song):
    if song.url:
        html_response = _bs_spoof(song.url)
        if not song.song_id:
            id_base = html_response('meta', {'name' : 'newrelic-resource-path'})[0]['content']
            song_id = id_base[id_base.rfind('/') + 1:]
            song.song_id = song_id

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

# Fetch song lyrics and metadata
def get_song_data(song):
    #html_response = None
    json_response = None

    # Fetch song API info, extract song url from page
    #elif song.song_id:
    json_response = song.genie.api_access(API_SONG_BASE_URL + song.song_id)
    song.url = json_response['response']['song']['url']
    # Fetch song page
    #html_response = _bs_spoof(song.url)

#    if html_response != None and json_response != None:
    # Store song metadata (TODO: More)
    song.has_data = True

    json_data = json_response['response']['song']
    song.title = json_data['title']
    song.release_date = json_data['release_date']
    song.artist = song.genie.artist_from_id(json_data['primary_artist']['id'])
    song.artist.name = json_data['primary_artist']['name']
    song.featured_artists = []

    for featured_artist in json_data['featured_artists']:
        featured_artist_obj = song.genie.artist_from_id(featured_artist['id'])
        featured_artist_obj.name = featured_artist['name']
        song.featured_artists.append(featured_artist_obj)

    song.credits = {}

    for additional_credits in json_data['custom_performances']:
        label = additional_credits['label']
        song.credits[label] = []
        for credited_artist in additional_credits['artists']:
            credited_artist_obj = song.genie.artist_from_id(credited_artist['id'])
            credited_artist_obj.name = credited_artist['name']
            song.credits[label].append(credited_artist_obj)

# Parses song's lyrics, and splits them into sections and fragments tied to
# specific artists
def process_song_fragments(song):
    song.has_fragments = True

    lyrics_left = song.html_lyrics

    sections = []
    section_artists = {}

    current_section = Section('Intro', song.artist)
    current_artist = song.artist
    current_fragment_tags = []
    tags_to_look_for_base = ['[', '<i>', '</i>', '<b>', '</b>', '<em>', '</em>', '<strong>', '</strong>']
    tags_to_look_for = tags_to_look_for_base[:]

    # Search for section header or HTML tag
    found_index, found_type = _min_search(lyrics_left, tags_to_look_for)

    # Potential artists who may deliver lyrics in the song
    potential_artists = song.featured_artists + [song.artist]
    if 'Additional Vocals' in song.credits:
        potential_artists += song.credits['Additional Vocals']

    while found_type:
        # Create fragment of text up to the found tag / header
        fragment = lyrics_left[:found_index]
        fragment_text = BeautifulSoup(fragment, 'lxml').text
        if len(fragment_text.strip()) > 0:
            fragment_obj = Fragment(current_artist, fragment_text)
            # Append fragment to the last if their artists match
            if len(current_section.fragments) > 0 and current_section.fragments[-1].artist == fragment_obj.artist:
                current_section.fragments[-1].text += fragment_text
            else:
                current_section.fragments.append(fragment_obj)

        # If a non-section-header square bracket is found (ie a [?] for an unknown lyric)
        if found_type == '[' and lyrics_left[found_index - 1] != '\n':
            lyrics_left = lyrics_left[found_index+1:]
            end_bracket_index = lyrics_left.find(']')
            lyrics_left = lyrics_left[end_bracket_index + 1:]
            found_index, found_type = _min_search(lyrics_left, tags_to_look_for)

        # When a section header
        if (found_type == '['):
            if len(current_section.fragments) > 0:
                sections.append(current_section)

            lyrics_left = lyrics_left[found_index+1:]
            end_bracket_index = lyrics_left.find(']')

            tag = lyrics_left[:end_bracket_index]
            end_name_index = tag.find(':')
            if end_name_index == -1:
                end_name_index = end_bracket_index
            tag_name = tag[:end_name_index]

            # Get the list of artists present in the song section
            artists_string = tag[end_name_index + 1:].strip()
            artists_string = artists_string.replace('&amp;', ',').replace('+', ',').replace(' and ', ',')

            tag_artists = [x.strip() for x in artists_string.split(',')]

            if len(tag_artists) == 0 or len(tag_artists[0]) == 0:
                for section in sections:
                    if section.name == tag_name:
                        tag_artists = section.artists

            section_artists = {}
            look_for_parens = False

            for artist in tag_artists:
                artist_bs = BeautifulSoup(artist, 'lxml')
                if artist_bs.html and artist_bs.html.body:
                    # Locate HTML tags around an artist's name, to signify what
                    # their lyrics will be tagged with
                    tags = artist_bs.html.body.findAll(['b', 'i', 'em', 'strong'])
                    artist_name = artist_bs.text
                    has_parens = False

                    # See if an artist's name is surrounded by parenthesis
                    if artist_name[0] == '(' and artist_name[-1] == ')':
                        artist_name = artist_name[1:-1]
                        has_parens = True
                        look_for_parens = True
                    name = [tag.name for tag in tags]
                    if has_parens:
                        name += '('
                    name.sort()

                    artist_obj = None
                    max_ratio = 0

                    for featured_artist in potential_artists:
                        ratio = difflib.SequenceMatcher(None, featured_artist.name, artist_name).ratio()
                        if ratio > .8 and ratio > max_ratio:
                            artist_obj = featured_artist
                            max_ratio = ratio

                    section_artists[''.join(name)] = artist_obj

            if not '' in section_artists:
                section_artists[''] = song.artist

            current_artist = section_artists['']

            # If an artist in this section is identified by parenthesis, make
            # sure to search for them in the lyrics, otherwise treat them as
            # ordinary text
            tags_to_look_for = tags_to_look_for_base[:]
            if look_for_parens:
                tags_to_look_for += ['(', ')']
            current_section = Section(tag_name, [section_artists['']] + section_artists.values())

            lyrics_left = lyrics_left[end_bracket_index + 1:]
            found_index, found_type = _min_search(lyrics_left, tags_to_look_for)
        else:
            lyrics_left = lyrics_left[found_index + len(found_type):]
            processed_tag = found_type.replace('/', '').replace(')', '(')
            if '<' in processed_tag:
                processed_tag = processed_tag[1:-1]
            if (found_type.find('/') != -1 or found_type == ')'):
                current_fragment_tags.remove(processed_tag)
            else:
                current_fragment_tags.append(processed_tag)

            current_fragment_tags.sort()

            if ''.join(current_fragment_tags) in section_artists:
                current_artist = section_artists[''.join(current_fragment_tags)]
            else:
                current_artist = None
            found_index, found_type = _min_search(lyrics_left, tags_to_look_for)

    fragment = lyrics_left.strip()
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
    def __init__(self, genie):
        self.url = None
        self.artist_id = None
        self.has_data = False
        self.name = None
        self.genie = genie

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
# requested from the api using song_obj.request_api()
class Song:
    def __init__(self, genie):
        self.url = None
        self.song_id = None
        self.has_data = False
        self.has_lyrics = False
        self.has_fragments = False
        self.sections = None
        self.featured_artists = None
        self.artist = None
        self.credits = None
        self.genie = genie

    def request_api(self):
        if not self.song_id and self.url:
            self.request_lyrics()
        if not self.has_data:
            get_song_data(self)
        return self

    def request_lyrics(self):
        if not self.url:
            self.request_api()
        if not self.has_lyrics:
            get_song_lyrics(self)
        return self

    def parse_lyrics(self):
        if not self.has_lyrics:
            self.request_lyrics()
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

class Genie:

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

genie = Genie(CLIENT_ACCESS_TOKEN)
for result in genie.search('telephone calls'):
    for artist in result.request_api().featured_artists:
        print artist.name
song = genie.song_from_id(2893424)
song.request_lyrics().parse_lyrics()

output = ''
for section in song.sections:
    for fragment in section.fragments:
        name = 'Other'
        if fragment.artist:
            name = fragment.artist.name
        output += name + '\n' + fragment.text.replace('\n', ' ') + '\n\n'

print 'writ'
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
    song_obj.request_api().parse()

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
