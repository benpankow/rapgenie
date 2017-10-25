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
