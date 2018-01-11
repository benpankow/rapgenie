from genie import RapGenie

CLIENT_ACCESS_TOKEN = 'tRsags-AZOTDVeU7w-ntSiRFDWiyy7Fsy6WoVGavYNp7KTZz-liAaNQdJr5gQJ7P'
genie = RapGenie(CLIENT_ACCESS_TOKEN)

for result in genie.search(input('> ')):
    for section in result.parse_lyrics().sections:
        for fragment in section.fragments:
            print('[{}]'.format(fragment.artist.name))
            print(fragment.text.strip().replace('\n', ' \\\\ ') + '\n')
    break
