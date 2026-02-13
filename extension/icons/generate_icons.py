#!/usr/bin/env python3
"""
Generate extension icons from SVG.
Run this script to create PNG icons for the Chrome extension.

Requirements: pip install cairosvg pillow
"""

import os
import sys

try:
    from PIL import Image
    import io
except ImportError:
    print("Installing required packages...")
    os.system("pip install pillow")
    from PIL import Image
    import io

def create_icon(size, filename):
    """Create a simple gradient icon."""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    pixels = img.load()
    
    center_x, center_y = size // 2, size // 2
    
    for y in range(size):
        for x in range(size):
            # Shield shape check (simplified)
            dx = abs(x - center_x)
            dy = y - size * 0.1
            
            # Shield boundary
            shield_width = size * 0.45 * (1 - max(0, dy / (size * 0.8)) * 0.3)
            
            if dy >= 0 and dy < size * 0.85 and dx < shield_width:
                # Gradient from purple to indigo
                t = (x + y) / (2 * size)
                r = int(99 + (139 - 99) * t)  # 6366f1 to 8b5cf6
                g = int(102 + (92 - 102) * t)
                b = int(241 + (246 - 241) * t)
                
                # Eye area (lighter)
                eye_y = size * 0.45
                eye_dist = ((x - center_x) ** 2 / (size * 0.22) ** 2 + 
                           (y - eye_y) ** 2 / (size * 0.14) ** 2)
                
                if eye_dist < 1:
                    # White eye background
                    if eye_dist < 0.3:
                        # Pupil
                        r, g, b = 79, 70, 229  # Indigo
                    else:
                        r, g, b = 255, 255, 255
                
                pixels[x, y] = (r, g, b, 255)
    
    img.save(filename, 'PNG')
    print(f"Created {filename}")

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    sizes = [16, 32, 48, 128]
    
    for size in sizes:
        filename = os.path.join(script_dir, f"icon-{size}.png")
        create_icon(size, filename)
    
    print("\nAll icons generated successfully!")
    print("You can also use the icon.svg for better quality icons.")

if __name__ == "__main__":
    main()
