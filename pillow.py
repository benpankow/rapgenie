from PIL import Image, ImageDraw, ImageFont
import string
from genie import RapGenie
import re

def split_text(font, width, text):
    out = []
    current_width = 0
    last_index = 0
    index = 0
    while index < len(text):
        while index < len(text):
            current_char_width = font.getsize(text[index])[0]
            index += 1
            if current_width + current_char_width < width:
                current_width += current_char_width
            else:
                break
        current = text[last_index:index]
        last_index = index
        out.append(current)
        current_width = 0
    return out

def get_line_height(font):
    return font.getsize(string.printable)[1]

def get_max_font_size(font_path, width, height, text):
    size = 7
    text_height = 0
    while text_height < height:
        size += 1
        print('a' + str(size))
        font = ImageFont.truetype(font_path, size)
        print('b' + str(size))
        lines = split_text(font, width, text)[:-1]
        print('c' + str(size))
        text_height = get_line_height(font) * len(lines)
    return size - 1

def get_average_color(image, x1, y1, x2, y2):
    x1 = max(0, x1)
    y1 = max(0, y1)
    x2 = min(image.width, x2)
    y2 = min(image.height, y2)
    n = 0
    r = 0
    g = 0
    b = 0
    for x in range(x1, x2):
        for y in range(y1, y2):
            rgb = image.getpixel((x, y))
            r += rgb[0]
            g += rgb[1]
            b += rgb[2]
            n += 1
    if n == 0:
        n = 1
    return (round(r / n), round(g / n), round(b / n))

reference = Image.open('flag.png').convert('RGB')

CLIENT_ACCESS_TOKEN = 'tRsags-AZOTDVeU7w-ntSiRFDWiyy7Fsy6WoVGavYNp7KTZz-liAaNQdJr5gQJ7P'
genie = RapGenie(CLIENT_ACCESS_TOKEN)

lyrics = ''
for section in next(genie.search('ultralight beam')).parse_lyrics().sections:
    for fragment in section.fragments:
        lyrics += fragment.text.strip().replace('\n', ' ') + ' '
    lyrics += ' '

lyrics = re.sub('\(.*?\)', ' ', lyrics)
lyrics = re.sub('\s+', ' ', lyrics)
lyrics = lyrics.strip()
lyrics = (lyrics + ' ') * 50

print('lyrics found')

print(reference.size)
img = Image.new('RGB', (reference.size[0], reference.size[1]))
draw = ImageDraw.Draw(img)

size = 10 #get_max_font_size('arial.ttf', img.width, img.height, lyrics)
print('size ' + str(size))

font = ImageFont.truetype('arial.ttf', size)

lines = split_text(font, img.width, lyrics)
line_height = font.getsize(lyrics)[1]

for i in range(len(lines)):
    if i * line_height > img.height:
        break

    line = lines[i]
    x = 0
    for char in line:
        char_size = font.getsize(char)[0]
        color = get_average_color(reference, x, i * line_height, x + char_size, (i + 1) * line_height)
        draw.text((x, i * line_height), char, color, font=font)
        x += char_size

img.save('out.png')
