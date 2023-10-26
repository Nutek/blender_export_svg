import mathutils as M
import math
import matplotlib.pyplot as plt
import numpy as np
import mpl_toolkits.mplot3d as m3d
from color_ops import *


def IdGen():
    id = 0
    while True:
        yield id
        id += 1


def take_n(gen, count):
    while count:
        yield next(gen)
        count -= 1


def vectors(arr: np.ndarray):
    return [M.Vector(p) for p in arr]


color_id = IdGen()

ax = plt.figure().add_axes((0, 0, 1, 1), projection="3d")
ax.autoscale(tight=True)
ax.set_xlim([-3, 3])
ax.set_ylim([-3, 3])
ax.set_zlim([-3, 3])

# Make the grid
# x, y, z = np.meshgrid(
#     np.arange(-0.8, 1, 0.2), np.arange(-0.8, 1, 0.2), np.arange(-0.8, 1, 0.8)
# )

# Make the direction data for the arrows
# u = np.sin(np.pi * x) * np.cos(np.pi * y) * np.cos(np.pi * z)
# v = -np.cos(np.pi * x) * np.sin(np.pi * y) * np.cos(np.pi * z)
# w = np.sqrt(2.0 / 3.0) * np.cos(np.pi * x) * np.cos(np.pi * y) * np.sin(np.pi * z)

# ax.quiver(x, y, z, u, v, w, length=0.1, normalize=True)


# stripe = np.array([[-1, 1, 1], [-0.9, 1, 1], [-0.9, 1, -1], [-1, 1, -1]])
# stripes = np.array([stripe + i * np.array([0.1, 0, 0]) for i in range(20)])

# srf = m3d.art3d.Poly3DCollection(
#     stripes,
#     alpha=1,
#     facecolor=get_color_by_idx(range(len(stripes))),
# )


def face(points):
    return np.array(points, dtype=M.Vector)


test_faces = [
    face([(0, 0, 1), (0, 0, -1), (-1, 0.25, 0)]),
    face([(0, 0, 1), (0, 0, -1), (-1, -0.25, 0)]),
]

ax.add_collection3d(
    m3d.art3d.Poly3DCollection(
        test_faces,
        alpha=1,
        facecolor=get_color_by_idx(take_n(color_id, len(test_faces))),
    )
)

vector_patterm = np.array(
    [
        ((0, 0, 0), (0, 0, 1)),
        ((0, 0.05, 0.9), (0, 0, 1)),
        ((0, -0.05, 0.9), (0, 0, 1)),
        ((0.05, 0, 0.9), (0, 0, 1)),
        ((-0.05, 0, 0.9), (0, 0, 1)),
    ],
    dtype=M.Vector,
)

screen_transform = M.Euler([0, 0, math.radians(0)]).to_matrix()

print(vector_patterm * screen_transform)

ax.add_collection3d(m3d.art3d.Line3DCollection(vector_patterm))

print([vectors(f) for f in test_faces])

normals = [M.geometry.normal(vectors(f)) for f in test_faces]

print(normals)

centers = [M.Vector(f.mean()) for f in test_faces]

print(centers)

ax.set_xlabel("X")
ax.set_ylabel("Y")
ax.set_zlabel("Z")

plt.show()
