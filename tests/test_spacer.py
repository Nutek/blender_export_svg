from ..export_svg_280 import *
import pytest

from .test_helpers import *


class TestSpacer:
    @pytest.mark.parametrize(
        "level,indent_size,expected",
        [
            (0, 1, 0),
            (0, 2, 0),
            (2, 2, 4),
            (1, 3, 3),
        ],
    )
    def test_produce_proper_space(self, level, indent_size, expected):
        spacer = Spacer(level, indent_size)
        assert str(spacer) == " " * expected

    def test_increase_level(self):
        spacer = Spacer(0, 2)
        assert str(spacer) == ""
        spacer2 = spacer + 1
        assert str(spacer2) == " " * 2
        spacer3 = spacer + 2
        assert str(spacer3) == " " * 4
        spacer4 = spacer2 + 1
        assert str(spacer4) == " " * 4
