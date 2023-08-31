from export_svg_280 import *
import pytest

from test_helpers import *


class TestBasicTagsAttributeFormat:
    @pytest.mark.parametrize(
        "input_name,expected", [("some_name", "<some_name />"), ("other", "<other />")]
    )
    def test_named_empty_element(self, input_name, expected):
        tag = TAT_Node(input_name)
        assert get_trimmed_lines(tag) == [expected]

    @pytest.mark.parametrize(
        "attributes,expected",
        [
            ({"attr1": "val1"}, ['<element attr1="val1" />']),
            ({"attr2": "val2"}, ['<element attr2="val2" />']),
            (
                {"attr1": "val1", "attr2": "val2"},
                ['<element attr1="val1" attr2="val2" />'],
            ),
        ],
    )
    def test_empty_element_with_attributes(self, attributes, expected):
        tag = TAT_Node("element")

        for k, v in attributes.items():
            tag.add_attr(k, v)

        assert get_trimmed_lines(tag) == expected


class TestTagsAttributeFormatNesting:
    def test_contains_empty_element(self):
        tag = TAT_Node("root")
        tag.add_tag(TAT_Node("inner"))
        assert get_trimmed_lines(tag) == ["<root>", "<inner />", "</root>"]

    def test_contains_element_with_attributes(self):
        inner = TAT_Node("inner")
        inner.add_attr("my_attr", "my_value")
        tag = TAT_Node("root")
        tag.add_tag(inner)
        assert get_trimmed_lines(tag) == [
            "<root>",
            '<inner my_attr="my_value" />',
            "</root>",
        ]

    def test_format_with_proper_indent(self):
        tag = TAT_Node("root")
        tag.add_tag(TAT_Node("inner"))
        nested = TAT_Node("nested")
        nested.add_tag(TAT_Node("inner"))
        tag.add_tag(nested)
        assert (
            str(tag)
            == "<root>\n <inner />\n <nested>\n  <inner />\n </nested>\n</root>"
        )
