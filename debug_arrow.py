import bpy
from mathutils import Vector


class Container:
    def debug_arrow(self, obj_name, coord, direction):
        arrow_obj = bpy.data.objects.get(obj_name)
        if arrow_obj is None:
            dbg_arr = bpy.data.objects.get("debug_arrow")
            if dbg_arr is None:
                raise RuntimeError(
                    "There is no object named `debug_arrow` which may be duplicated"
                )
            arrow_obj = bpy.data.objects.new(obj_name, dbg_arr.data)
            bpy.context.scene.collection.objects.link(arrow_obj)

        up = Vector((0, 0, 1))

        # arrow_obj.hide_set(True)
        arrow_obj.location = coord
        arrow_obj.scale = (1, 1, direction.length)
        arrow_obj.rotation_euler = (
            up.rotation_difference(direction).to_matrix().to_euler()
        )
