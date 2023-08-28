from export_svg_280 import *


def get_trimmed_lines(obj):
    return list(map(lambda s: s.strip(), str(obj).splitlines()))


class TestBasicTagsAttributeFormat:
    def test_named_empty_element(self):
        tag = TAT_Tag("some_name")
        assert get_trimmed_lines(tag) == ["<some_name />"]
