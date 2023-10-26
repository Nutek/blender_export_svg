import colorsys
from collections.abc import Iterable


def color_to_hstring(color):
    cast = lambda idx: int(255 * color[idx])
    return f"#{cast(0):02x}{cast(1):02x}{cast(2):02x}"


def generate_color_hue(idx, bits=8):
    reverse = 0
    left = bits
    while left:
        reverse = (reverse << 1) | (idx & 0x1)
        idx = idx >> 1
        left -= 1
    return reverse / float(1 << bits)


def get_color_by_idx(idx, s=0.85, v=0.8):
    if isinstance(idx, Iterable):
        return [get_color_by_idx(i, s, v) for i in idx]
    else:
        return color_to_hstring(colorsys.hsv_to_rgb(generate_color_hue(idx), s, v))
