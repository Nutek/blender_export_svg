from export_svg_280 import *
import pytest

from test_helpers import *


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

        for k, v in attributes.items():
            node.add_attr(k, v)

        assert get_trimmed_lines(node) == expected


class TestTagsAttributeFormatNesting:
    def test_contains_empty_element(self):
        node = TAT_Node("root")
        node.add_node(TAT_Node("inner"))
        assert get_trimmed_lines(node) == ["<root>", "<inner />", "</root>"]

    def test_contains_element_with_attributes(self):
        inner = TAT_Node("inner")
        inner.add_attr("my_attr", "my_value")
        node = TAT_Node("root")
        node.add_node(inner)
        assert get_trimmed_lines(node) == [
            "<root>",
            '<inner my_attr="my_value" />',
            "</root>",
        ]

    def test_format_with_proper_indent(self):
        node = TAT_Node("root")
        node.add_node(TAT_Node("inner"))
        nested = TAT_Node("nested")
        nested.add_node(TAT_Node("inner"))
        node.add_node(nested)
        assert (
            str(node)
            == "<root>\n <inner />\n <nested>\n  <inner />\n </nested>\n</root>"
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
            .add_node(TAT_Node("inner1"))
            .add_nodes(TAT_Node("inner2"))
            .add_node(TAT_Node("inner3"))
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
            .add_attr("attr1", "val1")
            .add_attrs(attr2="val2")
            .add_attr("attr3", "val3")
        )
        assert get_trimmed_lines(node) == [
            '<root attr1="val1" attr2="val2" attr3="val3" />',
        ]
