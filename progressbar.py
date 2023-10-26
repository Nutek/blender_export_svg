# How to make progressbar?
import bpy

wm = bpy.context.window_manager

# progress from [0 - 1000]
tot = 1000
wm.progress_begin(0, tot)
for i in range(tot):
    wm.progress_update(i)
wm.progress_end()
