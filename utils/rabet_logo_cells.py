"""Compact RABET dot-logo cell data for startup splash painting."""

from __future__ import annotations

import math
import random


LOGO_ROWS = (
    "000000000000000001122000000000000000",
    "000000000000000011122000012222200000",
    "000000000000001111120012222232200000",
    "000000000000011111101112233332200000",
    "000000000000011111011113333332000000",
    "000000000000111110111333333322000000",
    "000000000004411111155553333220000000",
    "000000000004441111555553332200000000",
    "000000000044441115555555311000000000",
    "000000000044464555555551110000000000",
    "000000000774488555555111100000000000",
    "000000777777788885541110000000000000",
    "000007777777777444446000000000000000",
    "0009777777777A4440000000000012220000",
    "0097777777777BBB40000001111110000000",
    "0077777444777BBB44000011110000000000",
    "0C777774467777BB44440000000001122222",
    "0DD77776777777BB44444441111111111000",
    "DDDD7777777777BB44444411111110000000",
    "CCDD7777777777BAA4444411111000000000",
    "446DD7777777777AA4444441000000011000",
    "64CCD777777777AAA4444440000111110000",
    "04CCCD7777777AAAA4444400011110000000",
    "004DCD7777AAAAAAA4440001111000000000",
    "00044444AAAAABBAAA400041110000000000",
    "0000000AAAAABBBBAA004441000000000000",
    "0000000AAAA77BBBAE044440000000000000",
    "000000EAAAA777BBB0444400000000000000",
    "000000EAAA7777BB04440000000000000000",
    "000000EAA877777AA4400000000000000000",
    "0000000EA777777AAA000000000000000000",
    "00000000A77777AAA0000000000000000000",
    "00000000777777AA00000000000000000000",
    "0000000D77777AA000000000000000000000",
    "000000DD7777A00000000000000000000000",
    "000009DDD7A0000000000000000000000000",
    "000009DD0000000000000000000000000000",
)

LOGO_PALETTE = {
    "1": "#008ABD",
    "2": "#00CFFF",
    "3": "#00FFCE",
    "4": "#3130AD",
    "5": "#31CFAD",
    "6": "#002073",
    "7": "#FF7573",
    "8": "#9C659C",
    "9": "#DE6521",
    "A": "#8C00AD",
    "B": "#DE20BD",
    "C": "#FFCF63",
    "D": "#FFAA21",
    "E": "#8C0063",
}

LOGO_FILL_PATTERNS = (
    "center_out",
    "top_down",
    "left_to_right",
    "diagonal",
    "color_ramp",
    "radar_sweep",
    "pulse_rings",
    "random_sparkle",
    "noise_to_logo",
    "checker_reveal",
    "baseline_rise",
)


def _cell_noise(row, col):
    """Return a stable pseudo-random value for a logo grid coordinate."""
    value = (row + 1) * 73856093 ^ (col + 1) * 19349663
    value = (value ^ (value >> 13)) * 83492791
    return (value & 0xFFFFFFFF) / 0xFFFFFFFF


def logo_cells(pattern="center_out"):
    """Return non-empty logo cells sorted by the requested reveal pattern."""
    cells = []
    for row, line in enumerate(LOGO_ROWS):
        for col, value in enumerate(line):
            if value != "0":
                cells.append((row, col, value))

    if not cells:
        return []

    max_row = len(LOGO_ROWS) - 1
    max_col = max(len(row) for row in LOGO_ROWS) - 1
    center_row = max_row / 2.0
    center_col = max_col / 2.0
    max_distance = math.hypot(center_row, center_col)

    if pattern == "top_down":
        key = lambda cell: (cell[0], cell[1])
    elif pattern == "left_to_right":
        key = lambda cell: (cell[1], cell[0])
    elif pattern == "diagonal":
        key = lambda cell: (cell[0] + cell[1], cell[0])
    elif pattern == "color_ramp":
        key = lambda cell: (int(cell[2], 36), cell[0] + cell[1])
    elif pattern == "radar_sweep":
        key = lambda cell: (
            math.atan2(cell[1] - center_col, -(cell[0] - center_row)) % (math.pi * 2),
            math.hypot(cell[0] - center_row, cell[1] - center_col),
        )
    elif pattern == "pulse_rings":
        def key(cell):
            distance = math.hypot(cell[0] - center_row, cell[1] - center_col)
            ring = int(distance / 3.6)
            angle = math.atan2(cell[0] - center_row, cell[1] - center_col)
            return (ring, angle if ring % 2 == 0 else -angle, distance)
    elif pattern == "random_sparkle":
        shuffled = cells[:]
        random.shuffle(shuffled)
        return shuffled
    elif pattern == "noise_to_logo":
        def key(cell):
            distance = math.hypot(cell[0] - center_row, cell[1] - center_col)
            noise = _cell_noise(cell[0], cell[1])
            if noise < 0.42:
                return (0, noise)
            return (1, distance / max_distance, noise)
    elif pattern == "checker_reveal":
        key = lambda cell: ((cell[0] + cell[1]) % 2, cell[0] + cell[1], cell[0])
    elif pattern == "baseline_rise":
        key = lambda cell: (-cell[0], abs(cell[1] - center_col), cell[1])
    else:
        key = lambda cell: (
            math.hypot(cell[0] - center_row, cell[1] - center_col),
            math.atan2(cell[0] - center_row, cell[1] - center_col),
        )

    return sorted(cells, key=key)
