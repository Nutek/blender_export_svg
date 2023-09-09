from ..export_svg_280 import *
import pytest

from .testing_helpers import *


class TestBasicTagsAttributeFormat:
    @pytest.mark.parametrize(
        "input_name,expected", [("some_name", "<some_name />"), ("other", "<other />")]
    )
    def test_named_empty_element(self, input_name, expected):
        node = TAT_Node(input_name)
        assert get_trimmed_lines(node) == [expected]

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
        node = TAT_Node("element")

        node.add_attrs(**attributes)

        assert get_trimmed_lines(node) == expected

    @pytest.mark.parametrize(
        "label,expected",
        [
            ("comment", ["<!-- comment -->"]),
            ("other text", ["<!-- other text -->"]),
        ],
    )
    def test_some_comment(self, label, expected):
        node = TAT_Comment(label)
        assert get_trimmed_lines(node) == expected


class TestTagsAttributeFormatNesting:
    def test_contains_empty_element(self):
        node = TAT_Node("root")
        node.add_nodes(TAT_Node("inner"))
        assert get_trimmed_lines(node) == ["<root>", "<inner />", "</root>"]

    def test_contains_element_with_attributes(self):
        inner = TAT_Node("inner")
        inner.add_attrs(my_attr="my_value")
        node = TAT_Node("root")
        node.add_nodes(inner)
        assert get_trimmed_lines(node) == [
            "<root>",
            '<inner my_attr="my_value" />',
            "</root>",
        ]

    def test_format_with_proper_indent(self):
        node = TAT_Node("root")
        node.add_nodes(TAT_Node("inner"))
        nested = TAT_Node("nested")
        nested.add_nodes(TAT_Node("inner"))
        nested.add_nodes(TAT_Comment("text"))
        node.add_nodes(nested)
        assert (
            str(node)
            == "<root>\n <inner />\n <nested>\n  <inner />\n  <!-- text -->\n </nested>\n</root>"
        )


class TestTagsAttributeFormatMultipleAddition:
    def test_adding_multiple_nodes(self):
        node = TAT_Node("root")
        node.add_nodes(TAT_Node("inner1"), TAT_Node("inner2"))
        assert get_trimmed_lines(node) == [
            "<root>",
            "<inner1 />",
            "<inner2 />",
            "</root>",
        ]

    def test_adding_multiple_attributes(self):
        node = TAT_Node("root")
        node.add_attrs(attr1="val1", attr2="val2")
        assert get_trimmed_lines(node) == [
            '<root attr1="val1" attr2="val2" />',
        ]

    def test_adding_multiple_attributes_by_map(self):
        node = TAT_Node("root")
        node.add_attrs(**{"name:attr1": "val1", "name:attr2": "val2"})
        assert get_trimmed_lines(node) == [
            '<root name:attr1="val1" name:attr2="val2" />',
        ]


class TestTagsAttributeFormatChaining:
    def test_adding_nodes_by_chaining(self):
        node = (
            TAT_Node("root")
            .add_nodes(TAT_Node("inner1"))
            .add_nodes(TAT_Node("inner2"))
            .add_nodes(TAT_Node("inner3"))
        )
        assert get_trimmed_lines(node) == [
            "<root>",
            "<inner1 />",
            "<inner2 />",
            "<inner3 />",
            "</root>",
        ]

    def test_adding_attributes_by_chaining(self):
        node = (
            TAT_Node("root")
            .add_attrs(attr1="val1")
            .add_attrs(attr2="val2")
            .add_attrs(attr3="val3")
        )
        assert get_trimmed_lines(node) == [
            '<root attr1="val1" attr2="val2" attr3="val3" />',
        ]
