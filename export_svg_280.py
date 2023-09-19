bl_info = {
    "name": "Viewport to SVG",
    "version": (0, 2, 1, 4),
    "blender": (2, 80, 0),
    "location": "View3D > Sidebar",
    "description": "Generate an SVG file from active view",
    "category": "Import-Export",
}

import bpy, bmesh, os, math, time, re, itertools
import mathutils as M, random as R, bpy_extras
from bpy_extras import view3d_utils as V3D
from mathutils import Vector
from collections.abc import Iterable


#####################################################################
# General helpers
#####################################################################


# 2D helpers
class Size2D:
    def __init__(self, width: float, height: float):
        self.width = width
        self.height = height


def frames_with_file_path(frame_numbers: Iterable, output_path: str):
    fill_size = len(str(max(frame_numbers)))
    basename_path, extension = os.path.splitext(output_path)
    for frame_number in frame_numbers:
        frame_number_str = str(int(frame_number)).zfill(fill_size)
        yield (frame_number, f"{basename_path}_{frame_number_str}{extension}")


class ObjectTypes:
    Mesh = "MESH"
    Curve = "CURVE"
    Font = "FONT"
    Surface = "SURFACE"
    Meta = "META"


#####################################################################
# SVG Format helpers
#####################################################################


# Spacer
class Spacer:
    def __init__(self, level, indent_size=1):
        self._level = level
        self._indent_size = indent_size

    def __str__(self):
        return " " * (self._level * self._indent_size)

    def __add__(self, diff: int):
        return Spacer(self._level + diff, self._indent_size)


# TagsAttributesTree
class TAT_Defaults:
    spacer = Spacer(0, 1)
    name_pattern = r"([_A-Za-z][_\-A-Za-z0-9]*)(:[_A-Za-z][_\-A-Za-z0-9]*)?"
    attr_value_pattern = r"[^\"\<\>]*"
    comment_pattern = r"((?!--).)+"


def validate_value(value, str_pattern=None, valid_types=[]):
    if valid_types and type(value) not in valid_types:
        raise TypeError(f"Expected type `{valid_types}`; given: {type(value)}")

    if str_pattern and isinstance(value, str) and not re.fullmatch(str_pattern, value):
        raise ValueError(
            f"Value does not fit to pattern: {str_pattern}; given: {value}"
        )


class TAT_Entity:
    def __init__(self, raw_content: str = ""):
        self._raw_content = raw_content

    def format_string(self, spacer: Spacer = TAT_Defaults.spacer):
        return f"{spacer}{self._raw_content}"

    def __str__(self):
        return self.format_string()


class TAT_Node(TAT_Entity):
    def __init__(self, name):
        super().__init__()
        validate_value(name, TAT_Defaults.name_pattern, [str])
        self._name = name
        self._children = []
        self._attributes = {}

    def format_string(self, spacer: Spacer = Spacer(0, 1)):
        formated_attributes = ""
        if len(self._attributes) != 0:
            formated_attributes = " " + " ".join(
                [f'{n}="{v}"' for n, v in self._attributes.items()]
            )

        if len(self._children) == 0:
            return f"{spacer}<{self._name}{formated_attributes} />"

        formated_children = [c.format_string(spacer + 1) for c in self._children]
        return "\n".join(
            [
                f"{spacer}<{self._name}{formated_attributes}>",
                *formated_children,
                f"{spacer}</{self._name}>",
            ]
        )

    def add_nodes(self, *tags):
        for tag in tags:
            if issubclass(type(tag), TAT_Entity):
                self._children.append(tag)
            elif type(tag) is list:
                self.add_nodes(*tag)
            elif tag is None:
                continue
            else:
                raise TypeError(
                    f"Expected type is subclass of TAT_Entity or list of such types; Given type: {type(tag)}"
                )
        return self

    def add_attrs(self, *dicts, **attrs):
        for d in dicts:
            if d is None:
                continue
            validate_value(d, valid_types=[dict])
            self.add_attrs(**d)
        for name, value in attrs.items():
            validate_value(name, TAT_Defaults.name_pattern, [str])
            validate_value(value, TAT_Defaults.attr_value_pattern, [str, int, float])
            self._attributes[name] = value
        return self


class TAT_Comment(TAT_Entity):
    def __init__(self, content):
        super().__init__()
        validate_value(content, TAT_Defaults.comment_pattern, [str, int, float])
        self._content = content

    def format_string(self, spacer: Spacer = Spacer(0, 1)):
        return f"{spacer}<!-- {self._content} -->"


# SVG Components
class SVG_Entity:
    def __init__(self, raw_content: TAT_Entity = TAT_Entity()):
        self._raw_content = raw_content

    def export(self):
        return self._raw_content

    def __str__(self) -> str:
        return f"{self.export()}\n"


class SVG_Element(SVG_Entity):
    def __init__(self, name: str, properties: dict = {}):
        super().__init__()
        self._name = name
        self._properties = properties

    def export(self) -> TAT_Entity:
        return TAT_Node(self._name).add_attrs(self._properties)

    def set_props(self, *dicts, **properties):
        for d in dicts:
            if d is None:
                continue
            self.set_props(**d)
        for name, value in properties.items():
            self._properties[name] = value
        return self


class SVG_Text(SVG_Element):
    def __init__(self, text: str, properties: dict = {}):
        super().__init__("text", properties)
        self._text = text

    def export(self):
        return super().export().add_nodes(TAT_Entity(self._text))


class SVG_Group(SVG_Element):
    def __init__(self, properties: dict = {}, name="g"):
        super().__init__(name, properties)
        self._components = []

    def export(self) -> TAT_Entity:
        return super().export().add_nodes([c.export() for c in self._components])

    def add(self, entity: SVG_Entity):
        self._components.append(entity)
        return self


class SVG_Document(SVG_Group):
    def __init__(self, width: int, height: int):
        super().__init__(
            name="svg",
            properties={
                "xmlns": "http://www.w3.org/2000/svg",
                "xmlns:inkscape": "http://www.inkscape.org/namespaces/inkscape",
                "xmlns:xlink": "http://www.w3.org/1999/xlink",
                "width": f"{width}px",
                "height": f"{height}px",
            },
        )
        self._components = []


def write_full_svg(output_file, size: Size2D, svg_entities: []):
    svg_doc = SVG_Document(size.width, size.height)

    # TODO: Remove it after task completion
    svg_doc.add(
        SVG_Element(
            "rect",
            {
                "width": size.width,
                "height": size.height,
                "style": "fill:none;stroke-width:1%;stroke:rgb(200,200,200)",
            },
        )
    )

    for entity in svg_entities:
        svg_doc.add(entity)
    output_file.write(str(svg_doc))


#####################################################################
# Main content of plugin
#####################################################################


class ExportSVG(bpy.types.Operator):
    bl_idname = "export.svg"
    bl_label = "Export SVG"
    bl_description = "Generate SVG file from active view"
    bl_options = {"REGISTER", "UNDO"}

    precision = 4

    def noise(self, a, b):
        return round(R.gauss(a, b), ExportSVG.precision)

    def execute(self, context):
        sce = bpy.context.scene
        region = context.region
        region3d = context.space_data.region_3d
        orto = region3d.is_perspective == False
        wm = bpy.context.window_manager
        output_file_path = bpy.path.abspath(wm.route)

        selected_objects = bpy.context.selected_objects
        center = (region.width / 2, region.height / 2)
        camera_coordinates = V3D.region_2d_to_origin_3d(region, region3d, center)

        col = M.Color((0, 0, 0))

        # use a plane named 'bisect' to cut meshes
        if wm.bisect in sce.objects:
            bis = sce.objects.get(wm.bisect)
            bis_co = bis.location
            bis_no = Vector((0, 0, 1))
            bis_no.rotate(bis.matrix_world)
            bis.select_set(False)
        else:
            bis = False

        # define scale factor for ortogonal mode -> 1BU = 100px
        if orto and wm.auto_sca:
            BU = Vector((1, 0, 0))
            BU.rotate(region3d.view_matrix.inverted())
            X0 = V3D.location_3d_to_region_2d(region, region3d, (0, 0, 0))
            X1 = V3D.location_3d_to_region_2d(region, region3d, BU)
            svg_sca = 100 / (X1 - X0).length * wm.svg_scale
            slide_x = -X0[0] * svg_sca
            slide_y = -X0[1] * svg_sca
        else:
            svg_sca = wm.svg_scale
            slide_x = slide_y = 0

        def visible(mes, indice, type):
            if hasattr(mes.verts, "ensure_lookup_table"):
                mes.verts.ensure_lookup_table()
                mes.faces.ensure_lookup_table()

            if type == "face":
                val = mes.faces[indice].calc_center_median()
                coo = V3D.location_3d_to_region_2d(region, region3d, val)
                if not coo:
                    return (0, 0, 0, 0, 0, False)
                for v in mes.faces[indice].verts:
                    if not V3D.location_3d_to_region_2d(
                        region, region3d, mes.verts[v.index].co
                    ):
                        return (0, 0, 0, 0, 0, False)
                ojo = V3D.region_2d_to_vector_3d(region, region3d, coo).normalized()
                dot = mes.faces[indice].normal.dot(ojo)
                if orto:
                    dis = M.geometry.distance_point_to_plane(
                        val, camera_coordinates, ojo
                    )
                else:
                    dis = (camera_coordinates - val).length
            elif type == "vertice":
                v = mes.verts[indice]
                val = v.co
                coo = V3D.location_3d_to_region_2d(region, region3d, val)
                if not coo:
                    return (0, 0, 0, 0, 0, False)
                ojo = V3D.region_2d_to_vector_3d(region, region3d, coo)
                dot = mes.verts[indice].normal.dot(ojo)
                dis = (camera_coordinates - val).length
            return (val, coo, ojo, dot, dis, True)

        # 3d coordinate to 2d coordinate
        def v3d_to_v2d(v3d):
            return V3D.location_3d_to_region_2d(region, region3d, v3d)

        # 3d co - 2d co - vector view - product - distance - valid
        def str_xy(
            coo3D, esc=svg_sca, xxx=wm.offset_x + slide_x, yyy=wm.offset_y + slide_y
        ):
            coo = V3D.location_3d_to_region_2d(region, region3d, coo3D)
            if not coo:
                return (0, 0, 0, 0, False)
            x = round(coo[0] * esc + xxx, ExportSVG.precision)
            if orto:
                y = round((-region.height + coo[1]) * -esc + yyy, ExportSVG.precision)
            else:
                y = round((region.height - coo[1]) * esc + yyy, ExportSVG.precision)
            return (str(x), str(y), str(x) + "," + str(y) + " ", Vector((x, y)), True)
            # str x - str y - str x,y - vector x,y - valido

        def vcol(col, r=0.25):
            ncol = col.copy()
            ncol.h = (ncol.h + R.random() * 2 * r - r) % 1
            ncol.s = max(0, min(1, ncol.s + 0.2 * R.triangular(-r, r)))
            ncol.v = max(0, min(1, ncol.v + 0.4 * R.triangular(-r, r)))
            return ncol

        def str_rgb(vector):
            r, g, b = vector[0], vector[1], vector[2]
            color = "rgb(%s,%s,%s)" % (round(r * 255), round(g * 255), round(b * 255))
            return color

        def render_line(obj):
            mode_curve, mode_bezier = False, False
            if obj.type == "CURVE":
                if (
                    not obj.data.bevel_object
                    and obj.data.bevel_depth < 0.001
                    and obj.data.extrude < 0.001
                ):
                    mode_curve = True
                if "BEZIER" in [s.type for s in obj.data.splines]:
                    mode_bezier = True
            return (mode_curve, mode_bezier)

        def object_2_bmesh(context, obj, convert=False):
            mesh = bmesh.new()

            if convert:
                depsgraph = bpy.context.evaluated_depsgraph_get()
                tmp = bpy.data.meshes.new_from_object(obj.evaluated_get(depsgraph))
                tmp.transform(obj.matrix_world)
                mesh.from_mesh(tmp)
                bpy.data.meshes.remove(tmp)
            else:
                if wm.dissolver or wm.collapse < 1:
                    mod = obj.modifiers.new("mod", "DECIMATE")
                    mod.decimate_type = wm.deci_type
                    if wm.deci_type == "DISSOLVE":
                        mod.angle_limit = wm.dissolver
                        mod.use_dissolve_boundaries = False
                    else:
                        mod.ratio = wm.collapse
                if obj.type == ObjectTypes.Mesh:
                    mesh.from_object(obj, context.depsgraph)
                    mesh.transform(obj.matrix_world)
                else:
                    tmp = obj.to_mesh(depsgraph=context.depsgraph)
                    tmp.transform(obj.matrix_world)
                    mesh.from_mesh(tmp)
                    bpy.data.meshes.remove(tmp)

                if wm.dissolver or wm.collapse < 1:
                    obj.modifiers.remove(mod)

            # use a plane named 'bisect' to cut meshes
            if bis:
                bmesh.ops.bisect_plane(
                    mesh,
                    geom=mesh.verts[:] + mesh.edges[:] + mesh.faces[:],
                    plane_co=bis_co,
                    plane_no=bis_no,
                    clear_outer=True,
                )

            mesh.normal_update()
            return mesh

        if wm.render_range == True:
            frame_list = frames_with_file_path(
                range(sce.frame_start, sce.frame_end + 1), output_file_path
            )
        else:
            frame_list = [(sce.frame_current, output_file_path)]
        restore_frame = sce.frame_current

        open_file_mode = "r+" if wm.use_continue else "w"

        ## LOOP ANIMATION
        for frame, output_file_path in frame_list:
            sce.frame_set(frame)

            begin_frame_time = time.time()

            if not wm.use_seed:
                wm.ran_seed = R.randrange(0, 9999)
            R.seed(wm.ran_seed)

            properties_for_all_objects = {}
            opacity = round(wm.col_opacity, ExportSVG.precision)
            if not math.isclose(opacity, 1, abs_tol=0.01):
                properties_for_all_objects["opacity"] = opacity

            # open file
            with open(output_file_path, open_file_mode) as output_file:
                # new inkscape layer
                layer = SVG_Group(
                    {"inkscape:groupmode": "layer", "id": str(time.asctime())}
                )

                # object to clone
                if wm.algo_vert != "nothing" and wm.use_clone:
                    clone = "X_" + str(R.choice(list(range(999))))
                    layer.add(
                        SVG_Group(
                            {
                                "id": clone,
                                "stroke-width": "2",
                                "stroke": str_rgb(wm.col_4),
                                **properties_for_all_objects,
                            }
                        )
                        .add(
                            SVG_Element(
                                "line",
                                {
                                    "x1": "-10",
                                    "y1": "0",
                                    "x2": "10",
                                    "y2": "0",
                                },
                            )
                        )
                        .add(
                            SVG_Element(
                                "line",
                                {
                                    "x1": "0",
                                    "y1": "10",
                                    "x2": "0",
                                    "y2": "-10",
                                },
                            )
                        )
                    )

                # dashed pattern
                if wm.algo_color == "pattern":
                    ran = str(R.randint(0, 999))
                    if wm.pat_col:
                        background = "none"
                    else:
                        background = str_rgb(wm.col_2)
                    layer.add(
                        SVG_Group(
                            {
                                "id": f"stripe{ran}",
                            }
                        )
                        .add(
                            SVG_Element(
                                "rect",
                                {
                                    "fill": background,
                                    "x": "0",
                                    "y": "0",
                                    "height": "10",
                                    "width": "1",
                                },
                            )
                        )
                        .add(
                            SVG_Element(
                                "rect",
                                {
                                    "fill": str_rgb(wm.col_3),
                                    "x": "0",
                                    "y": "0",
                                    "height": "2",
                                    "width": "1",
                                },
                            )
                        )
                    )

                    definitions = SVG_Group(name="defs")
                    c = [2.5, 3.5, 5, 7, 10]
                    for i in range(5):
                        definitions.add(
                            SVG_Group(
                                name="pattern",
                                properties={
                                    "id": f"pat_{ran}_{i}",
                                    "patternUnits": "userSpaceOnUse",
                                    "width": "1",
                                    "height": c[i],
                                    "patternTransform": f"rotate({R.randrange(-45, 45)}) scale({wm.pat_sca})",
                                },
                            ).add(SVG_Element("use", {"xlink:href": f"#stripe{ran}"}))
                        )
                    layer.add(definitions)

                ## OPERATIONS AT MESH LEVEL >>

                # remove object with invalid coordinates
                valid_selected_objects = [
                    o
                    for o in selected_objects
                    if v3d_to_v2d(o.matrix_world.to_translation()) is not None
                ]

                # sort objects by distance to viewer -usa object origin-
                if wm.order_obj:
                    distance = [
                        (
                            round((camera_coordinates - o.location).length_squared, 5),
                            o.name,
                        )
                        for o in valid_selected_objects
                    ]
                    distance.sort(reverse=True)
                    valid_selected_objects = [sce.objects[d[1]] for d in distance]

                grouped_objects = {
                    obj_type: list(objects)
                    for obj_type, objects in itertools.groupby(
                        valid_selected_objects, key=lambda o: o.type
                    )
                }

                if len(grouped_objects) == 0:
                    self.report({"ERROR"}, f"No selected objects for frame {frame}!")

                # unite all objects into a single mesh
                join = None
                if wm.join_objs and len(valid_selected_objects) > 1:
                    bpy.ops.object.select_all(action="DESELECT")

                    for i, o in enumerate(itertools.chain(*grouped_objects.values())):
                        depsgraph = bpy.context.evaluated_depsgraph_get()  ###
                        tmp = bpy.data.meshes.new_from_object(
                            o.evaluated_get(depsgraph)
                        )
                        tmp.transform(o.matrix_world)  ###

                        if not i:
                            join = bpy.data.objects.new("join", tmp)  ###
                            sce.collection.objects.link(join)
                        else:
                            add = bpy.data.objects.new("add", tmp)
                            sce.collection.objects.link(add)
                            add.select_set(True)
                            join.select_set(True)
                            context.view_layer.objects.active = join  ###
                            bpy.ops.object.join()
                            try:
                                bpy.data.meshes.remove(tmp)  ###
                            except:
                                pass
                    grouped_objects[ObjectTypes.Mesh] = [join]

                # overlap beziers
                bezier_outline = []

                # mesh loop
                print(grouped_objects)
                types_to_get = [
                    ObjectTypes.Mesh,
                    ObjectTypes.Curve,
                    ObjectTypes.Surface,
                ]
                for obj in itertools.chain(
                    *map(lambda key: grouped_objects.get(key, []), types_to_get)
                ):
                    # convert objects + mesh modifiers
                    line = render_line(obj)
                    mesh = object_2_bmesh(context, obj, line)
                    verts = mesh.verts

                    object_group = SVG_Group({"id": obj.name})

                    object_group.add(SVG_Entity(TAT_Comment(f"start {obj.name}")))
                    layer.add(object_group)

                    # draw a curve in the SVG
                    if line[0]:
                        I = [str_xy(v.co) for v in mesh.verts]
                        V = [v for v in I if v[4]]
                        if len(V) > 1:
                            points = " ".join(
                                [f"M {V[0][0]},{V[0][1]} L", *[c[2] for c in V]]
                            )
                            props = {
                                "id": f"curve_3D.{obj.name}",
                                "stroke": str_rgb(wm.col_5),
                                "stroke-width": str(round(wm.stroke_wid, 2)),
                                "stroke-linecap": "round",
                                "fill": "none",
                                "d": points,
                            }
                            bezier_outline.append(SVG_Element("path", props))

                        # overlap beziers
                        if wm.use_bezier and line[1]:
                            if not line[0]:
                                I = [str_xy(v.co) for v in mesh.verts]
                                V = [v for v in I if v[4]]
                            if len(V) > 1:
                                cur = obj.data.copy()
                                cur.transform(obj.matrix_world)
                                for spline in cur.splines:
                                    if spline.type == "BEZIER":
                                        bp = spline.bezier_points

                                        points = "M" + str_xy(bp[0].co)[2]
                                        nodos = [
                                            (
                                                bp[i - 1].handle_right,
                                                bp[i].handle_left,
                                                bp[i].co,
                                            )
                                            for i in range(1, len(bp))
                                        ]
                                        for v in nodos:
                                            points += (
                                                "C"
                                                + str_xy(v[0])[2]
                                                + str_xy(v[1])[2]
                                                + str_xy(v[2])[2]
                                            )
                                        if spline.use_cyclic_u:
                                            points += f"C{str_xy(bp[-1].handle_right)[2]}{str_xy(bp[0].handle_left)[2]}{str_xy(bp[0].co)[2]}z"

                                        props = {
                                            "stroke": "black",
                                            "opacity": ".5",
                                            "fill": "none",
                                            "d": points,
                                        }
                                        object_group.add(SVG_Element("path", props))
                                bpy.data.curves.remove(cur)

                    # gather info for the faces
                    FF = {}
                    for i, f in enumerate(mesh.faces):
                        FF[i] = visible(
                            mesh, i, "face"
                        )  # 3D - 2D - vector view - product - distance - valid

                    # list of visible faces
                    S = wm.use_select - 1

                    if wm.use_frontal:
                        P = [
                            k
                            for k in FF.keys()
                            if mesh.faces[k].select > S
                            and FF[k][5]
                            and mesh.faces[k].calc_area() > wm.min_area
                            and FF[k][3] < 0
                        ]
                    else:
                        P = [
                            k
                            for k in FF.keys()
                            if mesh.faces[k].select > S
                            if FF[k][5] and mesh.faces[k].calc_area() > wm.min_area
                        ]

                    # list of vertices in visible faces ####
                    I = []
                    for k in P:
                        I.append([v.index for v in mesh.faces[k].verts])
                    V = list(set([v for f in I for v in f]))

                    # gather info for vertices on visible faces
                    QQ = {}  # str x - str y - str x,y - vector x,y - valid
                    for v in V:
                        QQ[v] = str_xy(verts[v].co)

                    # order the faces according to distance to the viewer -use centroid-
                    distance = [(round(FF[f][4], ExportSVG.precision), f) for f in P]
                    distance.sort(reverse=True)
                    P = [d[1] for d in distance]

                    # remove vertices inside faces with 3 or 4 edges -see extend to ngons-
                    if wm.use_occ:
                        if wm.extra_bordes != "nothing" or wm.algo_vert != "nothing":
                            for c in P:
                                if mesh.faces[c].calc_area() > wm.min_area * 10:
                                    pv = mesh.faces[c].verts
                                    for v in V:
                                        if len(pv) == 3:
                                            q = M.geometry.intersect_point_tri_2d(
                                                QQ[v][3],
                                                QQ[pv[0].index][3],
                                                QQ[pv[1].index][3],
                                                QQ[pv[2].index][3],
                                            )
                                        else:
                                            q = M.geometry.intersect_point_quad_2d(
                                                QQ[v][3],
                                                QQ[pv[0].index][3],
                                                QQ[pv[1].index][3],
                                                QQ[pv[2].index][3],
                                                QQ[pv[3].index][3],
                                            )
                                        if q and v in V:
                                            if (camera_coordinates - verts[v].co) > (
                                                camera_coordinates - FF[c][0]
                                            ):
                                                V.remove(v)

                    # fill faces & trace edges
                    if P and (
                        wm.algo_color != "nothing"
                        or wm.algo_edge != "nothing"
                        or wm.algo_shade == "nothing"
                    ):
                        # border width
                        border_props = {}
                        if wm.algo_edge != "nothing":
                            if wm.edge_wid:
                                border_props.update(
                                    {
                                        "stroke-width": f"{wm.edge_wid}px",
                                        "stroke-linejoin": wm.edge_join,
                                        "stroke-linecap": "round",
                                    }
                                )

                        # border style
                        if wm.algo_edge == "linear":
                            border_props.update({"stroke": str_rgb(wm.col_3)})
                        elif wm.algo_edge == "dashed":
                            border_props.update(
                                {
                                    "stroke": str_rgb(wm.col_3),
                                    "stroke-dasharray": f"{1 + 3 * wm.edge_wid},{1 + 1.5 * wm.edge_wid}",
                                }
                            )

                        object_group.set_props(border_props)

                        # calculate step depth
                        if wm.algo_shade == "depth" or wm.use_effect == "explode":
                            if len(P):
                                range_value = (
                                    abs((distance[0][0] - distance[-1][0])) + 1e-05
                                )
                            else:
                                range_value = 0.5
                            # if wm.algo_shade == 'depth':
                            #     col = vcol(wm.col_1, wm.col_noise)

                        # object color
                        if wm.algo_color == "object":
                            colobj = vcol(wm.col_1, wm.col_noise)

                        elif wm.algo_color == "obj_pallete":
                            colobj = R.choice(
                                [wm.col_1, wm.col_2, wm.col_3, wm.col_4, wm.col_5]
                            )

                        # loop faces ------------------------------------------------------>
                        for i, f in enumerate(P):
                            if wm.algo_shade == "depth" or wm.use_effect == "explode":
                                dis = (distance[0][0] - distance[i][0]) / range_value

                            # apply color by faces
                            if (
                                wm.algo_color == "object"
                                or wm.algo_color == "obj_pallete"
                            ):
                                col = colobj

                            elif wm.algo_color == "faces":
                                col = vcol(wm.col_2, 0.01 + wm.col_noise / 2)

                            elif wm.algo_color == "face_pallete":
                                col = R.choice(
                                    [wm.col_1, wm.col_2, wm.col_3, wm.col_4, wm.col_5]
                                )

                            elif wm.algo_color == "material":
                                sl = mesh.faces[f].material_index
                                if obj.material_slots and obj.material_slots[sl].name:
                                    col = M.Color(
                                        obj.material_slots[sl].material.diffuse_color[
                                            :-1
                                        ]
                                    )
                                    col = vcol(col, wm.col_noise)
                                else:
                                    col = wm.col_1

                            elif wm.algo_color == "indices":
                                val = round(f / len(mesh.faces), ExportSVG.precision)
                                col.r = 1 - val
                                col.g = col.b = val

                            elif wm.algo_color == "pattern":
                                n = int(5.25 * abs(FF[f][3]) - 0.5)
                                if n > 4:
                                    fill = background
                                else:
                                    fill = "url(#pat_" + ran + "_" + str(n) + ")"

                            # apply shading

                            col_copy = col.copy()

                            if wm.algo_shade == "back_light":
                                dot = abs(FF[f][3])
                                col_copy.v = max(1 - dot, 0.001)
                                col_copy.s *= dot

                            elif wm.algo_shade == "front_light":
                                dot = abs(FF[f][3])
                                col_copy.v = dot
                                col_copy.s *= 1 - dot

                            elif wm.algo_shade == "indices":
                                val = round(f / len(mesh.faces), ExportSVG.precision)
                                col_copy.v = 1 - val
                                col_copy.s = 0.75 - val / 2

                            elif wm.algo_shade == "color_ramp":
                                dot = abs(FF[f][3])
                                col_copy.v = dot
                                col_copy.h = math.modf(col_copy.h + dot)[0]

                            elif wm.algo_shade == "soft_shading":
                                dot = abs(FF[f][3])
                                col_copy.v = dot

                            elif wm.algo_shade == "posterize":
                                dot = round(abs(FF[f][3]) * wm.pos_step)
                                col_copy.v = dot / wm.pos_step

                            elif wm.algo_shade == "depth":
                                col_copy.v = dis
                                col_copy.s = dis * col.s

                            elif wm.algo_shade == "backfaces":
                                dot = (FF[f][3]) < 0
                                col_copy.v = 0.5 * dot + 0.25

                            if wm.algo_color != "pattern":
                                fill = str_rgb(col_copy)

                            if wm.algo_color == "nothing":
                                fill = "none"

                            # edge per face
                            stroke_properties = {}
                            if wm.algo_color != "nothing" or wm.algo_shade == "pattern":
                                if wm.algo_edge == "match_fill":
                                    stroke_properties["stroke"] = fill

                            # draw the vertices of the faces
                            if wm.use_effect == "nothing" or wm.use_effect == "explode":
                                polygon_properties = {
                                    **stroke_properties,
                                    **properties_for_all_objects,
                                    "fill": fill,
                                }
                                points = ""
                                for v in mesh.faces[f].verts:
                                    if wm.use_effect == "explode":
                                        m = Vector(
                                            (
                                                ExportSVG.noise(0, wm.fac_noise),
                                                ExportSVG.noise(0, wm.fac_noise),
                                                (ExportSVG.noise(0, wm.fac_noise)),
                                            )
                                        )
                                        test = str_xy(verts[v.index].co + m / 50)
                                        if test[4]:
                                            points += str(test[2])
                                    else:
                                        points += str(QQ[v.index][2])
                                polygon_properties["points"] = points

                                if wm.use_effect == "explode":
                                    try:
                                        m = (
                                            str(FF[i][1][0])
                                            + ","
                                            + str(-FF[i][1][1] + region.height)
                                        )
                                    except:
                                        m = "0,0"
                                    polygon_properties[
                                        "transform"
                                    ] = f"rotate({str(dis * ExportSVG.noise(0, wm.fac_expl))},{m})"

                                object_group.add(
                                    SVG_Element("polygon", polygon_properties)
                                )

                            else:
                                dot = abs(FF[f][3])
                                delta = FF[f][4]
                                a = math.sqrt(mesh.faces[f].calc_area())
                                l = (
                                    a
                                    * dot
                                    * 100
                                    * wm.shape_size
                                    / delta
                                    * wm.svg_scale
                                    / (1 + 25 * orto)
                                )  ####
                                xy = str_xy(FF[f][0])
                                x = float(xy[0])
                                y = float(xy[1])

                                if wm.use_effect == "circles" and l > 1:
                                    object_group.add(
                                        SVG_Element(
                                            "circle",
                                            {
                                                **stroke_properties,
                                                **properties_for_all_objects,
                                                "fill": fill,
                                                "cx": x,
                                                "cy": y,
                                                "r": l,
                                            },
                                        )
                                    )

                                if wm.use_effect == "squares" and l > 1:
                                    object_group.add(
                                        SVG_Element(
                                            "rect",
                                            {
                                                **stroke_properties,
                                                **properties_for_all_objects,
                                                "fill": fill,
                                                "x": x - l,
                                                "y": y - l,
                                                "width": l * 2,
                                                "height": l * 2,
                                            },
                                        )
                                    )

                    # draw vertices as circles / clones
                    if wm.algo_vert != "nothing":
                        vertices_group = SVG_Group(
                            {
                                "id": f"vertices.{obj.name}",
                                "fill": str_rgb(wm.col_4),
                            }
                        )
                        object_group.add(vertices_group)
                        for i, v in enumerate(V):
                            test = visible(mesh, v, "vertice")
                            if test[5]:
                                vis = True
                                dot = test[3]
                                # if wm.use_frontal and dot > 0:
                                # vis = False
                                if vis:
                                    if wm.algo_vert == "linear":
                                        r = round(
                                            wm.svg_scale * wm.diam1, ExportSVG.precision
                                        )
                                    elif wm.algo_vert == "normal_to_inside":
                                        r = round(
                                            wm.svg_scale * wm.diam1 * abs(dot),
                                            ExportSVG.precision,
                                        )
                                    elif wm.algo_vert == "normal_to_outside":
                                        r = round(
                                            wm.svg_scale * wm.diam1 * (1 - abs(dot)),
                                            ExportSVG.precision,
                                        )
                                    else:
                                        # algo: use distance on an axis
                                        if wm.ver_spa == "local":
                                            matriz = obj.matrix_world.to_translation()
                                            z = abs(
                                                verts[v].co[int(wm.ver_axis)]
                                                - matriz[int(wm.ver_axis)]
                                            )
                                        else:
                                            z = abs(verts[v].co[int(wm.ver_axis)])
                                        r = round(
                                            wm.svg_scale * z * wm.diam1,
                                            ExportSVG.precision,
                                        )

                                    # draw vertices
                                    c = str_xy(verts[v].co)
                                    if r >= 1:
                                        if wm.use_clone:
                                            vertices_group.add(
                                                SVG_Element(
                                                    "use",
                                                    {
                                                        "xlink:href": f"#{clone}",
                                                        "transform": f"translate({c[2]}) scale({round(r / 10, ExportSVG.precision)},{round(r / 10, ExportSVG.precision)}) rotate({str(round(R.random() * 360))})",
                                                    },
                                                )
                                            )
                                        else:
                                            vertices_group.add(
                                                SVG_Element(
                                                    "circle",
                                                    {
                                                        "cx": c[0],
                                                        "cy": c[1],
                                                        "r": r / 2,
                                                        **properties_for_all_objects,
                                                    },
                                                )
                                            )

                    # step value per object
                    lev = len(verts)
                    if lev:
                        offset = R.randrange(0, lev)
                    extra = R.randrange(0, wm.curve_var + 1)

                    # path vertices -step + variation-
                    if wm.vert_conn and len(verts) > 1:
                        i = 1
                        off = offset
                        c = str_xy(verts[off].co)
                        if c[4]:
                            data = f"M {c[0]},{c[1]} {wm.curve} "
                            while i <= lev:
                                if i + off >= lev:
                                    off -= lev
                                c = str_xy(verts[i + off].co)
                                if c[4]:
                                    data += c[2]
                                i += wm.curve_step + extra
                            data += " z"

                            object_group.add(
                                SVG_Element(
                                    "path",
                                    {
                                        "id": f"path.{obj.name}",
                                        "stroke": str_rgb(wm.col_5),
                                        "fill": "none",
                                        "d": data,
                                    },
                                )
                            )

                    # number vertices -step + variation-
                    verts.ensure_lookup_table()
                    if wm.use_num and len(verts) > 1:
                        i = 1
                        off = offset
                        c = str_xy(verts[off].co)
                        if c[4]:
                            text_group = SVG_Group(
                                {
                                    "id": f"indices.{obj.name}",
                                    "font-size": wm.fon_size,
                                    "text-anchor": "middle",
                                }
                            )

                            while i <= lev:  ####
                                if i + off >= lev:
                                    off -= lev
                                c = str_xy(verts[i + off].co)
                                if c[4]:
                                    text_group.add(
                                        SVG_Text(
                                            str(i),
                                            {
                                                "x": c[0],
                                                "y": c[1],
                                            },
                                        )
                                    )
                                i += wm.curve_step + extra

                            object_group.add(text_group)

                    # extra solid border
                    if wm.extra_bordes != "nothing":
                        borders_group = SVG_Group(
                            {
                                "id": f"bordes.{o.name}",
                                "stroke": str_rgb(wm.col_6),
                                "stroke-linecap": "round",
                                "fill": "none",
                            }
                        )
                        object_group.add(borders_group)

                        edg = mesh.edges

                        for e in edg:
                            vis = True
                            if e.verts[0].index not in V or e.verts[1].index not in V:
                                vis = False
                            if wm.use_boundary:
                                vis = e.is_boundary
                            if vis:
                                vis = e.calc_face_angle(1.5708) > wm.stroke_ang
                            if vis:
                                v1 = str_xy(verts[e.verts[1].index].co)[3]
                                v2 = str_xy(verts[e.verts[0].index].co)[3]
                                delta = v1 - v2
                                le = delta.length * wm.svg_scale
                                if le > wm.min_len:
                                    # mover los extremos
                                    if wm.extra_bordes == "extender":
                                        if wm.edg_displ:
                                            v1 += delta * wm.edg_displ
                                            v2 -= delta * wm.edg_displ
                                        if wm.edg_noise:
                                            v1 += delta * (
                                                ExportSVG.noise(0, wm.edg_noise)
                                            )
                                            v2 -= delta * (
                                                ExportSVG.noise(0, wm.edg_noise)
                                            )
                                    if wm.extra_bordes == "brush":
                                        w = wm.stroke_wid + le / 25
                                        v1 -= delta * w / 250
                                        v2 += delta * w / 250

                                    a, b = str(round(v1[0], ExportSVG.precision)), str(
                                        round(v1[1], ExportSVG.precision)
                                    )
                                    c, d = str(round(v2[0], ExportSVG.precision)), str(
                                        round(v2[1], ExportSVG.precision)
                                    )

                                    if wm.extra_bordes == "extender":
                                        borders_group.add(
                                            SVG_Element(
                                                "line",
                                                {
                                                    "stroke-width": round(
                                                        wm.stroke_wid, 2
                                                    ),
                                                    "x1": a,
                                                    "y1": b,
                                                    "x2": c,
                                                    "y2": d,
                                                },
                                            )
                                        )
                                    elif wm.extra_bordes == "curved_strokes":
                                        v3 = (
                                            v1
                                            - delta / 2
                                            + Vector(
                                                (
                                                    ExportSVG.noise(
                                                        0, le * wm.cur_noise
                                                    ),
                                                    ExportSVG.noise(
                                                        0, le * wm.cur_noise
                                                    ),
                                                )
                                            )
                                        )
                                        e, f = str(
                                            round(v3[0], ExportSVG.precision)
                                        ), str(round(v3[1], ExportSVG.precision))
                                        borders_group.add(
                                            SVG_Element(
                                                "path",
                                                {
                                                    "stroke-width": round(
                                                        wm.stroke_wid, 2
                                                    ),
                                                    "d": "M {a} {b} Q {e},{f} {c},{d}",
                                                },
                                            )
                                        )
                                    elif wm.extra_bordes == "brush":
                                        r1, r2 = Vector(
                                            (
                                                ExportSVG.noise(0, w),
                                                ExportSVG.noise(0, w),
                                            )
                                        ), Vector(
                                            (
                                                ExportSVG.noise(0, w),
                                                ExportSVG.noise(0, w),
                                            )
                                        )
                                        v3, v4 = (
                                            v1 - delta / 2 + r1,
                                            v1 - delta / 2 + r2,
                                        )
                                        e, f = str(
                                            round(v3[0], ExportSVG.precision)
                                        ), str(round(v3[1], ExportSVG.precision))
                                        g, h = str(
                                            round(v4[0], ExportSVG.precision)
                                        ), str(round(v4[1], ExportSVG.precision))
                                        borders_group.add(
                                            SVG_Element(
                                                "path",
                                                {
                                                    "fill": str_rgb(wm.col_6),
                                                    "d": "M {a},{b} Q {e},{f} {c},{d} Q {g},{h} {a},{b}",
                                                },
                                            )
                                        )
                                    else:  # outline
                                        W = visible(mesh, e.verts[0].index, "vertice")[
                                            3
                                        ]
                                        W += visible(mesh, e.verts[1].index, "vertice")[
                                            3
                                        ]
                                        W = 10 - round(abs(W * 5), ExportSVG.precision)
                                        if W > wm.stroke_con * 9:
                                            borders_group.add(
                                                SVG_Element(
                                                    "line",
                                                    {
                                                        "stroke-width": round(
                                                            W * wm.stroke_wid / 5, 2
                                                        ),
                                                        "x1": a,
                                                        "y1": b,
                                                        "x2": c,
                                                        "y2": d,
                                                    },
                                                )
                                            )

                    # release mesh memory
                    mesh.free()

                # overlap beziers
                if wm.use_bezier:
                    map(layer.add, bezier_outline)

                ## OBJECT LEVEL OPERATIONS >>

                OO = [
                    str_xy(o.matrix_world.to_translation())
                    for o in valid_selected_objects
                ]

                # origin as a circle / name
                if wm.use_origin:
                    object_origins_group = SVG_Group(
                        {"id": "object.origin", "fill": str_rgb(wm.col_5)}
                    )
                    layer.add(object_origins_group)
                    for i, o in enumerate(valid_selected_objects):
                        s = max(
                            0.5,
                            abs(o.dimensions[0] * wm.obj_x)
                            + abs(o.dimensions[1] * wm.obj_y)
                            + abs(o.dimensions[2] * wm.obj_z),
                        )
                        n = wm.obj_x + wm.obj_y + wm.obj_z
                        if n:
                            s /= n
                        else:
                            s = 1
                        r = round(wm.svg_scale * s * wm.diam2, ExportSVG.precision)
                        c = OO[i]
                        if wm.use_name:
                            object_origins_group.add(
                                SVG_Text(
                                    str(o.name),
                                    {
                                        "font-size": round(wm.fon_size * r / 10, 1),
                                        "text-anchor": "middle",
                                        "transform": f"rotate({str(round(ExportSVG.noise(0, s * 2)))},{c[2]})",
                                        "x": c[0],
                                        "y": c[1],
                                        **properties_for_all_objects,
                                    },
                                )
                            )
                        else:
                            object_origins_group.add(
                                SVG_Element(
                                    "circle",
                                    {
                                        "cx": c[0],
                                        "cy": c[1],
                                        "r": r,
                                        **properties_for_all_objects,
                                    },
                                )
                            ).add(
                                SVG_Element(
                                    "circle",
                                    {
                                        "fill": str_rgb(vcol(wm.col_2)),
                                        "cx": c[0],
                                        "cy": c[1],
                                        "r": r / 2,
                                        **properties_for_all_objects,
                                    },
                                )
                            )

                # continuous line object
                if wm.obj_conn:
                    if len(OO) > 1:
                        points = "M"
                        for i, c in enumerate(OO[:-1]):
                            if i == 0:
                                points += f" {c[0]},{c[1]} {wm.curve} "
                            else:
                                points += str(c[2])
                            if wm.curve != "L":
                                delta = OO[i + 1][3] - c[3]
                                le = round(delta.length) * 5
                                cc = (
                                    c[3]
                                    + delta / 2
                                    + Vector(
                                        (
                                            ExportSVG.noise(0, le * wm.cur_noise),
                                            ExportSVG.noise(0, le * wm.cur_noise),
                                        )
                                    )
                                )
                                points = f"{cc[0]},{cc[1]} "
                        points += f"{OO[-1][2]}"

                        layer.add(
                            SVG_Element(
                                "path",
                                {
                                    "id": "object.union",
                                    "stroke": str_rgb(wm.col_5),
                                    "fill": "none",
                                    "d": points,
                                },
                            )
                        )

                # draw hierarchies / object relations
                if wm.obj_rel:
                    relations_group = SVG_Group(
                        {"id": "relations", "stroke": str_rgb(wm.col_5), "fill": "none"}
                    )
                    layer.add(relations_group)
                    for i, o in enumerate(valid_selected_objects):
                        if o.parent:
                            h = str_xy(o.matrix_world.to_translation())
                            p = str_xy(o.parent.matrix_world.to_translation())
                            relations_group.add(
                                SVG_Element(
                                    "path",
                                    {
                                        "id": f"rel.{o.name}.{o.parent.name}",
                                        "d": f"M {p[2]}",
                                    },
                                )
                            )

                # cleaning temporary object from 'join'
                if wm.join_objs and join:
                    for o in valid_selected_objects:
                        o.select_set(True)
                    context.view_layer.objects.active = valid_selected_objects[-1]
                    tmp = join.data
                    sce.collection.objects.unlink(join)
                    bpy.data.objects.remove(join)
                    bpy.data.meshes.remove(tmp)

                new_session_comment = SVG_Entity(TAT_Comment("new blender session"))
                total_write = lambda: write_full_svg(
                    output_file,
                    Size2D(sce.render.resolution_x, sce.render.resolution_y),
                    [new_session_comment, layer],
                )

                if wm.use_continue:
                    whole_content = output_file.read()

                    output_file.seek(0, os.SEEK_SET)
                    previous, separator, rest = whole_content.rpartition("</svg>")
                    if len(separator):
                        output_file.write(
                            "\n".join(
                                [
                                    previous,
                                    new_session_comment.export().format_string(
                                        Spacer(1)
                                    ),
                                    layer.export().format_string(Spacer(1)),
                                    separator,
                                    rest,
                                ]
                            )
                        )
                    else:
                        total_write()
                        output_file.write(rest)
                else:
                    total_write()

            print(
                "Frame", frame, ">", round(time.time() - begin_frame_time, 4), "seconds"
            )

        sce.frame_set(restore_frame)
        return {"FINISHED"}


class IncrSVG(bpy.types.Operator):
    bl_idname = "add_to.svg"
    bl_label = "Add to SVG"
    bl_description = "Add shapes to the end of a file"

    def execute(self, context):
        wm = bpy.context.window_manager
        wm.use_continue = True
        bpy.ops.export.svg()
        if wm.use_continue == False:
            self.report({"ERROR"}, "Can not append to this file")
        wm.use_continue = False
        bpy.ops.ed.undo()
        return {"FINISHED"}


class ComprSVG(bpy.types.Operator):
    bl_idname = "compress.svg"
    bl_label = "Compress"
    bl_description = "Compress selected file to an SVGZ file"

    def execute(self, context):
        import gzip

        wm = bpy.context.window_manager
        if wm.route.endswith(".svg"):
            svzroute = wm.route + "z"
            try:
                with open(wm.route, "rb") as entrada:
                    with gzip.open(svzroute, "wb") as output:
                        output.writelines(entrada)
            except:
                self.report({"ERROR"}, "Verify the path")
        else:
            self.report({"ERROR"}, "Verify the path")

        return {"FINISHED"}


class OpenSVG(bpy.types.Operator):
    bl_idname = "open.svg"
    bl_label = "Open"
    bl_description = "Open the file"

    def execute(self, context):
        wm = bpy.context.window_manager
        try:
            bpy.ops.wm.url_open(url=wm.route)
        # try: bpy.ops.wm.path_open(filepath=wm.route)
        except:
            pass
        return {"FINISHED"}


class PanelSVG(bpy.types.Panel):
    bl_label = "Export SVG"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "SVG"
    bl_idname = "OBJECT_PT_PanelSVG"

    def draw(self, context):
        wm = bpy.context.window_manager
        layout = self.layout
        column = layout.column()
        split = column.split(align=True)
        split.operator("export.svg", text="Export SVG")
        split.operator("add_to.svg")
        column.prop(wm, "route")
        split = column.split()
        split.operator("open.svg")
        split.operator("compress.svg")

        column.separator()
        split = column.split(align=True)
        split.prop(wm, "svg_scale")
        split.prop(wm, "offset_x")
        split.prop(wm, "offset_y")

        column = layout.column()
        column.separator()
        column.prop(wm, "algo_color", icon="FACESEL")
        column.prop(wm, "algo_shade", icon="SNAP_FACE")
        column.prop(wm, "algo_edge", icon="EDGESEL")
        column.prop(wm, "extra_bordes", icon="SNAP_EDGE")
        column.prop(wm, "algo_vert", icon="VERTEXSEL")
        column.prop(wm, "use_effect", icon="CLIPUV_DEHLT")

        column = layout.column()
        column.separator()
        row = column.row(align=True)
        row.prop(wm, "col_1")
        row.prop(wm, "col_2")
        row.prop(wm, "col_3")
        row.prop(wm, "col_4")
        row.prop(wm, "col_5")
        row = column.row(align=True)
        row.prop(wm, "col_noise", slider=True)
        row.prop(wm, "col_opacity", slider=True)

        column = layout.column(align=True)
        column.separator()
        split = column.split()

        izq = split.column(align=True)
        izq.label(text="Export Options:")
        izq.prop(wm, "use_frontal")
        izq.prop(wm, "order_obj")
        izq.prop(wm, "use_select")
        izq.prop(wm, "use_boundary")
        izq.prop(wm, "use_occ")
        if not context.space_data.region_3d.is_perspective:
            izq.prop(wm, "auto_sca")
        izq.prop(wm, "join_objs")
        izq.prop(wm, "bisect")

        der = split.column(align=True)
        der.label(text="Draw Extras:")
        der.prop(wm, "use_origin")
        der.prop(wm, "obj_conn")
        der.prop(wm, "obj_rel")
        der.prop(wm, "vert_conn")
        der.prop(wm, "use_num")
        der.prop(wm, "use_clone")
        der.prop(wm, "use_bezier")

        column.separator()
        column = layout.column()
        column.label(text="Geometry:")
        split = column.split(align=True)
        split.prop(wm, "deci_type")
        if wm.deci_type == "DISSOLVE":
            split.prop(wm, "dissolver", slider=True)
        else:
            split.prop(wm, "collapse", slider=True)
        row = column.row(align=True)
        row.prop(wm, "min_area", slider=True)
        row.prop(wm, "min_len", expand=True)

        if wm.use_effect != "nothing":
            column.label(text="Effects:")
            if wm.use_effect == "explode":
                row = column.row(align=True)
                row.prop(wm, "fac_expl", slider=True)
                row.prop(wm, "fac_noise", slider=True)
            else:
                column.prop(wm, "shape_size", slider=True)

        if wm.algo_edge != "nothing":
            column.label(text="Edges:")
            split = column.split(factor=0.8, align=True)
            split.prop(wm, "edge_wid", slider=True)
            split.prop(wm, "edge_join")

        if wm.algo_shade == "posterize":
            column.label(text="Posterization:")
            column.prop(wm, "pos_step", slider=True)

        if wm.algo_color == "pattern":
            column.label(text="Hatch Pattern:")
            split = column.split()
            split.prop(wm, "pat_sca", slider=True)
            split.prop(wm, "pat_col", slider=True)

        if wm.extra_bordes != "nothing":
            column.label(text="Strokes:")
            column.prop(wm, "stroke_ang", slider=True)
            split = column.split(factor=0.8, align=True)
            split.prop(wm, "stroke_wid", slider=True)
            split.prop(wm, "col_6")
            if wm.extra_bordes == "extender":
                split = column.split(align=True)
                split.prop(wm, "edg_displ", slider=True)
                split.prop(wm, "edg_noise", slider=True)
            if wm.extra_bordes == "curved_strokes":
                column.prop(wm, "cur_noise", slider=True)
            if wm.extra_bordes == "countour":
                column.prop(wm, "stroke_con", slider=True)

        if wm.use_origin or wm.algo_vert != "nothing":
            column.label(text="Objects | Verts:")
            if wm.use_origin:
                column.prop(wm, "diam2", slider=True)
                split = column.split(align=True)
                izq = split.column(align=True)
                izq.prop(wm, "use_name")
                der = split.row(align=True)
                der.prop(wm, "obj_x")
                der.prop(wm, "obj_y")
                der.prop(wm, "obj_z")
            if wm.algo_vert != "nothing":
                column.prop(wm, "diam1", slider=True)
                if wm.algo_vert == "axis":
                    row = column.row(align=True)
                    row.prop(wm, "ver_axis", expand=True)
                    row.prop(wm, "ver_spa", expand=True)

        if wm.vert_conn or wm.use_num or wm.obj_conn:
            column.label(text="Connections:")
            split = column.row(align=True)
            if wm.use_num or wm.vert_conn:
                split.prop(wm, "curve_step")
                split.prop(wm, "curve_var")
            if wm.use_num:
                column.prop(wm, "fon_size", slider=True)
            if wm.vert_conn or wm.obj_conn:
                row = column.row()
                row.prop(wm, "curve", expand=True)

        column.label(text="Seed:")
        split = column.split(factor=0.35, align=True)
        split.prop(wm, "use_seed")
        split.prop(wm, "ran_seed", slider=True)

        column.prop(wm, "render_range")


bpy.types.WindowManager.route = bpy.props.StringProperty(
    name="",
    subtype="FILE_PATH",
    default="C:\\tmp\\algo.svg",
    description="Save the SVG file - use absolute path",
)
bpy.types.WindowManager.use_continue = bpy.props.BoolProperty(
    name="Add to SVG", default=False, description="Adds geometry to the end of a file"
)
bpy.types.WindowManager.svg_scale = bpy.props.FloatProperty(
    name="Scale", min=0.01, max=10, default=1, description="Document scale"
)
bpy.types.WindowManager.offset_x = bpy.props.IntProperty(
    name="Slide X", min=-10000, max=10000, default=-0, description="Horizontal offset"
)
bpy.types.WindowManager.offset_y = bpy.props.IntProperty(
    name="Slide Y", min=-10000, max=10000, default=0, description="Vertical offset"
)

bpy.types.WindowManager.algo_color = bpy.props.EnumProperty(
    name="Color",
    items=[
        ("nothing", "0. Nothing", "Skip from export"),
        ("object", "1. Object: Random", "Variations on first color - use slider"),
        ("faces", "3. Face: Random", "Variations on second color - use slider"),
        ("obj_pallete", "2. Object: Palette", "Pick colors from palette"),
        ("face_pallete", "4. Face: Palette", "Pick colors from palette"),
        ("material", "5. Materials", "Diffuse color from Face Material"),
        ("indices", "6. Indices", "Based on face indices"),
        (
            "pattern",
            "7. Pattern",
            "Generate a hatching effect using third and second color",
        ),
    ],
    description="Base color for selected shapes",
    default="object",
)
bpy.types.WindowManager.algo_shade = bpy.props.EnumProperty(
    name="Shading",
    items=[
        ("nothing", "0. Nothing", "Skip from export"),
        ("back_light", "1. Back Light", "Shading"),
        ("front_light", "2. Front Light", "Sombreado"),
        ("indices", "3. Indices", "Based on face indices"),
        ("depth", "4. Depth", "Distance from camera -local space ramp-"),
        ("soft_shading", "5. Soft Shading", "Soft Shading"),
        ("posterize", "6. Posterization", "Reduce the number of shade steps"),
        ("color_ramp", "7. Color Ramp", "Displace hue based on angle"),
        ("backfaces", "8. Backfacing", "Front / Back shading"),
    ],
    description="Shape shading - modifies the color",
    default="soft_shading",
)
bpy.types.WindowManager.algo_edge = bpy.props.EnumProperty(
    name="Edges",
    items=[
        ("nothing", "0. Nothing", "Skip from export"),
        ("linear", "1. Linear", "Regular Edges"),
        ("dashed", "2. Dashed", "Dashed lines"),
        (
            "match_fill",
            "3. Match Fill",
            "Extend the fill to edges, helps on aliasing artifacts",
        ),
    ],
    description="Edges style on each face",
    default="match_fill",
)
bpy.types.WindowManager.extra_bordes = bpy.props.EnumProperty(
    name="Strokes",
    items=[
        ("nothing", "0. Nothing", "Skip from export"),
        ("extender", "1. Extend Edges", "Extend the edges with some variations"),
        ("curved_strokes", "2. Curved Strokes", "Curved Strokes"),
        ("countour", "3. Contour", "Change width based on angle"),
        ("brush", "4. Brush", "Modulate width along curve"),
    ],
    description="Export Strokes over shapes as a separate group",
    default="nothing",
)
bpy.types.WindowManager.algo_vert = bpy.props.EnumProperty(
    name="Vertices",
    items=[
        ("nothing", "0. Nothing", "Skip from export"),
        ("linear", "1. Constant", "Same size for all vertices"),
        ("normal_to_inside", "2. Inside", "Base diameter on normals"),
        ("normal_to_outside", "3. Outside", "Base diameter on normals"),
        ("axis", "4. Use an Axis", "Base diameter on distance along an axis"),
    ],
    description="Export Vertices over shapes",
    default="nothing",
)
bpy.types.WindowManager.use_effect = bpy.props.EnumProperty(
    name="Effects",
    items=[
        ("nothing", "0. Nothing", "Skip from export"),
        ("explode", "1. Explode", "Explode Faces"),
        ("squares", "2. Squares", "Faces as Squares"),
        ("circles", "3. Circles", "Faces as Circles"),
    ],
    description="Distort faces for export",
    default="nothing",
)

bpy.types.WindowManager.col_1 = bpy.props.FloatVectorProperty(
    name="",
    description="Objects",
    default=(0.8, 0.4, 0.1),
    min=0,
    max=1,
    step=1,
    precision=3,
    subtype="COLOR_GAMMA",
    size=3,
)
bpy.types.WindowManager.col_2 = bpy.props.FloatVectorProperty(
    name="",
    description="Faces",
    default=(1, 0.9, 0.5),
    min=0,
    max=1,
    step=1,
    precision=3,
    subtype="COLOR_GAMMA",
    size=3,
)
bpy.types.WindowManager.col_3 = bpy.props.FloatVectorProperty(
    name="",
    description="Edges",
    default=(0.2, 0.1, 0),
    min=0,
    max=1,
    step=1,
    precision=3,
    subtype="COLOR_GAMMA",
    size=3,
)
bpy.types.WindowManager.col_4 = bpy.props.FloatVectorProperty(
    name="",
    description="Vertices",
    default=(0.8, 0.1, 0.2),
    min=0,
    max=1,
    step=1,
    precision=3,
    subtype="COLOR_GAMMA",
    size=3,
)
bpy.types.WindowManager.col_5 = bpy.props.FloatVectorProperty(
    name="",
    description="Paths",
    default=(0.1, 0.2, 0.3),
    min=0,
    max=1,
    step=1,
    precision=3,
    subtype="COLOR_GAMMA",
    size=3,
)
bpy.types.WindowManager.col_6 = bpy.props.FloatVectorProperty(
    name="",
    description="Strokes",
    default=(0, 0, 0),
    min=0,
    max=1,
    step=1,
    precision=3,
    subtype="COLOR_GAMMA",
    size=3,
)

bpy.types.WindowManager.col_noise = bpy.props.FloatProperty(
    name="Variation",
    min=0,
    soft_max=1,
    max=5,
    default=0.25,
    description="Modify solid color for Objects and Faces",
)
bpy.types.WindowManager.col_opacity = bpy.props.FloatProperty(
    name="Opacity",
    min=0,
    max=1,
    default=0.9,
    description="Affects the mixing of shapes",
)

bpy.types.WindowManager.deci_type = bpy.props.EnumProperty(
    name="",
    items=[
        ("DISSOLVE", "Dissolve", "Merge faces based on angle"),
        ("COLLAPSE", "Collapse", "Edge collapsing"),
    ],
    description="Simplify mesh before exporting",
    default="DISSOLVE",
)
bpy.types.WindowManager.dissolver = bpy.props.FloatProperty(
    name="Dissolve Faces",
    subtype="ANGLE",
    min=0,
    max=0.7854,
    default=0.08727,
    description="Simplify mesh before export",
)
bpy.types.WindowManager.collapse = bpy.props.FloatProperty(
    name="Collapse Edges",
    min=0.01,
    max=1,
    default=0.75,
    description="Simplify mesh before export",
)
bpy.types.WindowManager.min_area = bpy.props.FloatProperty(
    name="A",
    min=0,
    max=5,
    default=0.0001,
    description="Area: skip smaller Faces from export",
)
bpy.types.WindowManager.min_len = bpy.props.FloatProperty(
    name="L",
    min=0,
    max=15,
    default=0.025,
    description="Length: skip shorter Edges from export",
)
bpy.types.WindowManager.use_origin = bpy.props.BoolProperty(
    name="Objects Origin",
    default=False,
    description="Mark selected objects Location and Scale",
)
bpy.types.WindowManager.obj_conn = bpy.props.BoolProperty(
    name="Connect Objects",
    default=False,
    description="Connect selected objects with a Path",
)
bpy.types.WindowManager.obj_rel = bpy.props.BoolProperty(
    name="Hierarchy",
    default=False,
    description="Connect objects child objects to parent",
)
bpy.types.WindowManager.vert_conn = bpy.props.BoolProperty(
    name="Connect Vertices",
    default=False,
    description="Connect defined vertices with a Path",
)
bpy.types.WindowManager.use_num = bpy.props.BoolProperty(
    name="Number Vertices",
    default=False,
    description="Show index Number for defined vertices",
)
bpy.types.WindowManager.use_clone = bpy.props.BoolProperty(
    name="Clones on Vertices",
    default=False,
    description="VERTICES: place instances of a symbol you can edit later in Inkscape",
)
bpy.types.WindowManager.use_expl = bpy.props.BoolProperty(
    name="Explode Faces",
    default=False,
    description="Distort and add explode effect to Faces",
)
bpy.types.WindowManager.dissolver = bpy.props.FloatProperty(
    name="Dissolve Faces",
    subtype="ANGLE",
    min=0,
    max=0.7854,
    default=0.08727,
    precision=1,
    description="Simplify mesh before export",
)
bpy.types.WindowManager.min_area = bpy.props.FloatProperty(
    name="A",
    min=0,
    max=5,
    default=0.0001,
    description="Area: skip smaller Faces from export",
)
bpy.types.WindowManager.min_len = bpy.props.FloatProperty(
    name="L",
    min=0,
    max=15,
    default=0.025,
    description="Length: skip shorter Edges from export",
)
bpy.types.WindowManager.edge_wid = bpy.props.FloatProperty(
    name="Edges Width", min=0, max=50, default=1, description="Edges Width"
)
bpy.types.WindowManager.edge_join = bpy.props.EnumProperty(
    name="",
    items=[
        ("miter", "Miter", "Miter"),
        ("round", "Round", "Round"),
        ("bevel", "Bevel", "Bevel"),
    ],
    description="Stroke Linejoin - corners",
    default="miter",
)
bpy.types.WindowManager.pat_col = bpy.props.BoolProperty(
    name="Transparent Pattern", default=False, description="Draw a transparent pattern"
)
bpy.types.WindowManager.pat_sca = bpy.props.FloatProperty(
    name="Scale", min=0.25, max=5, default=0.75, description="Hatch pattern: Scale"
)
bpy.types.WindowManager.pos_step = bpy.props.IntProperty(
    name="Posterization Steps",
    min=2,
    max=8,
    default=3,
    description="Posterization Steps",
)

bpy.types.WindowManager.use_frontal = bpy.props.BoolProperty(
    name="Facing Only",
    default=True,
    description="Export only facing faces and vertices",
)
bpy.types.WindowManager.order_obj = bpy.props.BoolProperty(
    name="Order Objects",
    default=True,
    description="Order objects based on distance from origin to view",
)
bpy.types.WindowManager.use_select = bpy.props.BoolProperty(
    name="Selected Faces", default=False, description="Export only Selected faces"
)
bpy.types.WindowManager.use_boundary = bpy.props.BoolProperty(
    name="Boundaries",
    default=False,
    description="Only export Strokes on boundaries of open meshes",
)
bpy.types.WindowManager.use_bezier = bpy.props.BoolProperty(
    name="Bezier Overlay",
    default=False,
    description="Bezier curve objects are exported as such - may be some distortion",
)

bpy.types.WindowManager.ver_axis = bpy.props.EnumProperty(
    name="A",
    items=[("0", "X", "Axis X"), ("1", "Y", "Axis Y"), ("2", "Z", "Axis Z")],
    description="Vertex size from distance along axis",
    default="2",
)
bpy.types.WindowManager.ver_spa = bpy.props.EnumProperty(
    name="B",
    items=[("local", "LOC", "Local"), ("global", "GLOB", "Global")],
    description="Vertex size from distance along axis",
    default="local",
)
bpy.types.WindowManager.curve = bpy.props.EnumProperty(
    name="Path",
    items=[
        ("L", "L", "Linear"),
        ("Q", "Q", "Quadratic"),
        ("T", "T", "Smooth Quadratic"),
        ("C", "C", "Cubic"),
        ("S", "S", "Smooth Cubic"),
    ],
    description="The kind of SVG curve that connects objects and vertices",
    default="L",
)
bpy.types.WindowManager.use_occ = bpy.props.BoolProperty(
    name="Oclude Strokes",
    default=False,
    description="Hide Strokes that are ocluded by a tri or quad - very slow",
)
bpy.types.WindowManager.auto_sca = bpy.props.BoolProperty(
    name="Fixed Scale",
    default=False,
    description="Ortho Mode: use a fixed scale for output - default is 1BU = 100px",
)

bpy.types.WindowManager.diam1 = bpy.props.FloatProperty(
    name="Vertices Diameter",
    min=0.1,
    max=1000,
    default=10,
    description="Vertex Mark size",
)
bpy.types.WindowManager.diam2 = bpy.props.FloatProperty(
    name="Objects Diameter",
    min=0.1,
    max=1000,
    default=10,
    description="Object Mark size",
)
bpy.types.WindowManager.use_name = bpy.props.BoolProperty(
    name="Use Names", default=False, description="Show object name"
)
bpy.types.WindowManager.obj_x = bpy.props.BoolProperty(
    name="X", default=False, description="Local X size affects diameter"
)
bpy.types.WindowManager.obj_y = bpy.props.BoolProperty(
    name="Y", default=True, description="Local Y size affects diameter"
)
bpy.types.WindowManager.obj_z = bpy.props.BoolProperty(
    name="Z", default=False, description="Local Z size affects diameter"
)
bpy.types.WindowManager.fon_size = bpy.props.IntProperty(
    name="Font Size",
    min=4,
    max=96,
    default=9,
    description="Font size to show names and numbers",
)
bpy.types.WindowManager.curve_step = bpy.props.IntProperty(
    name="Step",
    min=1,
    max=250,
    default=4,
    description="Step between vertices, affects Connect and Numerate",
)
bpy.types.WindowManager.curve_var = bpy.props.IntProperty(
    name="Var",
    min=0,
    max=250,
    default=4,
    description="Step Variation between vertices, affects Connect and Numerate",
)
bpy.types.WindowManager.edg_displ = bpy.props.FloatProperty(
    name="Extend",
    min=0,
    max=0.5,
    default=0.05,
    description="Strokes: extend end points",
)
bpy.types.WindowManager.edg_noise = bpy.props.FloatProperty(
    name="Variation",
    min=0,
    max=0.5,
    default=0.05,
    description="Strokes: displace along edges",
)
bpy.types.WindowManager.cur_noise = bpy.props.FloatProperty(
    name="Curvature",
    min=0,
    max=0.5,
    default=0.05,
    description="Strokes: move center point",
)
bpy.types.WindowManager.stroke_ang = bpy.props.FloatProperty(
    name="Sharp Angle",
    min=0,
    max=math.radians(135),
    default=math.radians(15),
    subtype="ANGLE",
    description="Strokes: use angle to limit export",
)
bpy.types.WindowManager.stroke_wid = bpy.props.FloatProperty(
    name="Stroke Width", min=0, max=10, default=1.5, description="Strokes: width"
)
bpy.types.WindowManager.stroke_con = bpy.props.FloatProperty(
    name="Contrast", min=0, max=1, default=0.5, description="Contour: contrast"
)
bpy.types.WindowManager.fac_expl = bpy.props.FloatProperty(
    name="Explode", min=0, max=90, default=5, description="Faces: explode"
)
bpy.types.WindowManager.fac_noise = bpy.props.FloatProperty(
    name="Distort", min=0, max=50, default=5, description="Faces: move vertices"
)
bpy.types.WindowManager.shape_size = bpy.props.FloatProperty(
    name="Shape Size",
    min=1,
    max=50,
    default=5,
    description="Square and Circles size multiplier",
)
bpy.types.WindowManager.bisect = bpy.props.StringProperty(
    name="",
    default="bisect_plane",
    description="Name of an object used as reference plane to cut geometries",
)
bpy.types.WindowManager.join_objs = bpy.props.BoolProperty(
    name="Join Objects",
    default=False,
    description="Useful for Face sorting, breaks some shaders",
)
bpy.types.WindowManager.use_seed = bpy.props.BoolProperty(
    name="Fixed Seed",
    default=False,
    description="Useful for animation, keeps variation values stable",
)
bpy.types.WindowManager.ran_seed = bpy.props.IntProperty(
    name="Seed", min=0, max=9999, default=5555, description="Random Seed"
)

bpy.types.WindowManager.render_range = bpy.props.BoolProperty(
    name="SVG Sequence",
    default=False,
    description="Export animation as a sequence of SVG files",
)


if __name__ == "__main__":
    classes = (ExportSVG, OpenSVG, IncrSVG, ComprSVG, PanelSVG)
    register, unregister = bpy.utils.register_classes_factory(classes)
    register()
