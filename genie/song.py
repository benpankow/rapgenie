from bs4 import BeautifulSoup
from bs4 import Comment
import requests
import re
import string
import difflib
from .section import Section
from .fragment import Fragment
from .artist import Artist

GENIUS_URL = 'https://genius.com/'
API_GENIUS_URL = 'https://api.genius.com/'

API_SONG_BASE_URL = API_GENIUS_URL + 'songs/'
API_ARTISTS_BASE_URL = API_GENIUS_URL + 'artists/'
API_SEARCH_BASE_URL = API_GENIUS_URL + 'search?q='

# Load a given webpage's html contents into a BeautifulSoup object
def bs_spoof(url):
    response = requests.get(url, headers = {'User-Agent': 'Mozilla/5.0'})
    return BeautifulSoup(response.text, 'lxml')

# Searches for a number of terms in a given string
# Returns a tuple with the first element the index of the first locate
# term, the second element the term itself
def min_search(target_string, search_terms):
    lowest = -1
    best = None
    for term in search_terms:
        index = target_string.find(term)
        if index != -1 and (index < lowest or lowest == -1):
            lowest = index
            best = term
    return (lowest, best)

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
        if (self.song_id is None) and self.url:
            self.request_lyrics()
        if not self.has_data:
            self.get_song_data()
        return self

    def request_lyrics(self):
        if self.url is None:
            self.request_api()
        if not self.has_lyrics:
            self.get_song_lyrics()
        return self

    def parse_lyrics(self):
        if not self.has_lyrics:
            self.request_lyrics()
        if not self.has_fragments:
            self.process_song_fragments()
        return self

    def __str__(self):
        if self.has_data:
            return self.title + ' (' + self.url + ')'
        elif self.url:
            return 'Unrequested song with URL ' + self.url
        else:
            return 'Unrequested song with ID ' + self.song_id

    # Fetch song lyrics and metadata
    def get_song_data(self):
        json_response = None

        # Fetch song API info, extract song url from page
        json_response = self.genie.api_access(API_SONG_BASE_URL + self.song_id)
        self.url = json_response['response']['song']['url']

        self.has_data = True

        # Fill in fields from json
        json_data = json_response['response']['song']
        self.title = json_data['title']
        self.release_date = json_data['release_date']
        self.artist = self.genie.artist_from_id(json_data['primary_artist']['id'])
        self.artist.name = json_data['primary_artist']['name']
        self.featured_artists = []

        for featured_artist in json_data['featured_artists']:
            featured_artist_obj = self.genie.artist_from_id(featured_artist['id'])
            featured_artist_obj.name = featured_artist['name']
            self.featured_artists.append(featured_artist_obj)

        self.credits = {}

        for additional_credits in json_data['custom_performances']:
            label = additional_credits['label']
            self.credits[label] = []
            for credited_artist in additional_credits['artists']:
                credited_artist_obj = self.genie.artist_from_id(credited_artist['id'])
                credited_artist_obj.name = credited_artist['name']
                self.credits[label].append(credited_artist_obj)


    # Fetch song lyrics
    def get_song_lyrics(self):
        if self.url:
            html_response = bs_spoof(self.url)
            if self.song_id is None:
                id_base = html_response('meta', {'name' : 'newrelic-resource-path'})[0]['content']
                song_id = id_base[id_base.rfind('/') + 1:]
                self.song_id = song_id

            # Store song lyrics, in plaintext and html
            lyrics_html = html_response('div', {'class' : 'lyrics'})[0]
            self.lyrics = lyrics_html.text.strip()

            for tag in lyrics_html.findAll('a'):
                tag.replaceWithChildren()
            for tag in lyrics_html.findAll('p'):
                tag.replaceWithChildren()
            for tag in lyrics_html.findAll('div'):
                tag.replaceWithChildren()
            for elem in lyrics_html.children:
                if isinstance(elem, Comment):
                    elem.extract()

            self.html_lyrics = str(lyrics_html)

    def get_potential_artists(self):
        potential_artists = self.featured_artists + [self.artist]
        if 'Additional Vocals' in self.credits:
            potential_artists += self.credits['Additional Vocals']
        return potential_artists

    def process_fragment_text(self, fragments, current_artist, fragment_text):
        if len(fragment_text.strip()) > 0:
            fragment_obj = Fragment(current_artist, fragment_text)
            # Append fragment to the last if their artists match
            if len(fragments) > 0 and fragments[-1].artist == fragment_obj.artist:
                fragments[-1].text += fragment_text
            else:
                fragments.append(fragment_obj)
        return fragments

    # Parses song's lyrics, and splits them into sections and fragments tied to
    # specific artists
    def process_song_fragments(self):
        self.has_fragments = True

        lyrics_left = self.html_lyrics

        sections = []
        section_artists = {}

        current_section = Section('Intro', self.artist)
        current_artist = self.artist
        current_fragment_tags = []

        search_for_parens = False
        tag_search_str_base = '\[|<i>|</i>|<b>|</b>|<em>|</em>|<strong>|</strong>'
        tag_search_str = tag_search_str_base[:]

        # Potential artists who may deliver lyrics in the song
        potential_artists = self.get_potential_artists()

        # Search for section header or HTML tag
        # found_index, found_type = min_search(lyrics_left, tags_to_look_for)
        found = re.search(tag_search_str, lyrics_left)

        while found:
            found_index = found.start(0)
            found_end_index = found.end(0)
            found_type = found.group(0)

            paren_before_tag = False

            # Create fragment of text up to the found tag / header
            fragment = lyrics_left[:found_index]
            if len(fragment) > 0 and fragment[-1] == '(':
                fragment = fragment[:-1]
                paren_before_tag = True
            if lyrics_left[found_end_index] == ')':
                fragment += ')'
                found_end_index += 1

            fragment_text = BeautifulSoup(fragment, 'lxml').text
            current_section.fragments = self.process_fragment_text(current_section.fragments, current_artist, fragment_text)

            # If a non-section-header square bracket is found (ie a [?] for an unknown lyric)
            if found_type == '[' and (lyrics_left[found_index - 1] != '\n' or lyrics_left[lyrics_left[found_index:].find(']') + found_index + 1] != '<'):
                lyrics_left = lyrics_left[found_end_index:]
                end_bracket_index = lyrics_left.find(']')
                lyrics_left = lyrics_left[end_bracket_index + 1:]
            # When a section header
            elif (found_type == '['):
                if len(current_section.fragments) > 0:
                    sections.append(current_section)
                lyrics_left = lyrics_left[found_end_index:]
                end_bracket_index = lyrics_left.find(']')

                tag = lyrics_left[:end_bracket_index]
                end_name_index = tag.find(':')
                if end_name_index == -1:
                    end_name_index = end_bracket_index
                tag_name = tag[:end_name_index]

                # Get the list of artists present in the song section
                artists_string = tag[end_name_index + 1:].strip()

                tag_artists = [x.strip() for x in re.split(',?\s*and\s*|\s*&amp;\s*|\s(?=\()|\s*,\s*', artists_string)]

                if len(tag_artists) == 0 or len(tag_artists[0]) == 0:
                    for section in sections:
                        if section.name == tag_name:
                            tag_artists = map(lambda x : x.name, section.artists)

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
                        tag_names = [tag.name for tag in tags]
                        if has_parens:
                            tag_names += '('
                        tag_names.sort()

                        artist_obj = None
                        max_ratio = 0

                        for featured_artist in potential_artists:
                            ratio = difflib.SequenceMatcher(None, featured_artist.name, artist_name).ratio()
                            if ratio > .8 and ratio > max_ratio:
                                artist_obj = featured_artist
                                max_ratio = ratio
                        if artist_obj is None:
                            artist_obj = Artist(self.genie)
                            artist_obj.name = artist_name

                        tag_names_str = ''.join(tag_names)
                        section_artists[tag_names_str] = artist_obj

                if not '' in section_artists:
                    section_artists[''] = self.artist

                current_artist = section_artists['']

                # If an artist in this section is identified by parenthesis, make
                # sure to search for them in the lyrics, otherwise treat them as
                # ordinary text
                tag_search_str = tag_search_str_base[:]
                if look_for_parens:
                    tag_search_str += '|\)|\('
                current_section = Section(tag_name, [section_artists['']] + list(section_artists.values()))

                lyrics_left = lyrics_left[end_bracket_index + 1:]
            else:
                lyrics_left = lyrics_left[found_end_index:]
                if paren_before_tag:
                    lyrics_left = '(' + lyrics_left

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
            found = re.search(tag_search_str, lyrics_left)

        fragment = lyrics_left.strip()
        fragment_text = BeautifulSoup(fragment, 'lxml').text
        current_section.fragments = self.process_fragment_text(current_section.fragments, current_artist, fragment_text)

        if len(current_section.fragments) > 0:
            sections.append(current_section)

        self.sections = sections
