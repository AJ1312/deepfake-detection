#!/usr/bin/env python3
"""Generate extension icons."""
from PIL import Image

def create_icon(size, filename):
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    pixels = img.load()
    cx, cy = size // 2, size // 2
    
    for y in range(size):
        for x in range(size):
            dx = abs(x - cx)
            dy = y - size * 0.1
            sw = size * 0.45 * (1 - max(0, dy / (size * 0.8)) * 0.3)
            
            if dy >= 0 and dy < size * 0.85 and dx < sw:
                t = (x + y) / (2 * size)
                r = int(99 + 40 * t)
                g = int(102 - 10 * t)
                b = int(241 + 5 * t)
                ey = size * 0.45
                ed = ((x - cx) ** 2 / (size * 0.22) ** 2 + (y - ey) ** 2 / (size * 0.14) ** 2)
                if ed < 1:
                    if ed < 0.3:
                        r, g, b = 79, 70, 229
                    else:
                        r, g, b = 255, 255, 255
                pixels[x, y] = (r, g, b, 255)
    img.save(filename, 'PNG')
    print(f'Created {filename}')

if __name__ == '__main__':
    for s in [16, 32, 48, 128]:
        create_icon(s, f'icon-{s}.png')
    print('Done!')
