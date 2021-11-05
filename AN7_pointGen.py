bl_info = {
	"name": "AN7 Point Generator",
	"author": "Iaian7 - John Einselen",
	"version": (0, 6, 1),
	"blender": (2, 80, 0),
	"location": "Scene (object mode) > AN7 Tools > Point Generator",
	"description": "Creates point arrays with vertex attribute data",
	"warning": "inexperienced developer, use at your own risk",
	"wiki_url": "",
	"tracker_url": "",
	"category": "3D View"}

# Based on the following resources:
# https://blender.stackexchange.com/questions/95616/generate-x-cubes-at-random-locations-but-not-inside-each-other
# https://blender.stackexchange.com/questions/1371/organic-yet-accurate-modeling-with-the-golden-spiral
# https://blender.stackexchange.com/questions/117558/how-to-add-vertices-into-specific-vertex-groups
# https://blender.stackexchange.com/questions/55484/when-to-use-bmesh-update-edit-mesh-and-when-mesh-update
# https://blenderartists.org/t/custom-vertex-attributes-data/1311915/3
# https://www.jasondavies.com/poisson-disc/
# https://onlinetoolz.net/sequences
# And most of all, the VF Point Array plugin developed at Vectorform

import bpy
from bpy.app.handlers import persistent
import bmesh
from random import uniform
from random import randint
from random import shuffle
from copy import deepcopy
from mathutils import Vector
import math
import time

###########################################################################
# Main classes

class AN7_Point_Walk(bpy.types.Operator):
	bl_idname = "an7pointwalk.offset"
	bl_label = "Replace Mesh" # "Create Points" is a lot nicer, but I'm concerned this is a real easy kill switch for important geometry!
	bl_description = "Create points using the selected options, deleting and replacing the currently selected mesh"
	bl_options = {'REGISTER', 'UNDO'}

	def execute(self, context):
		# Recursion settings
		elements = bpy.context.scene.an7_point_gen_settings.max_elements # target number of points
		failures = bpy.context.scene.an7_point_gen_settings.max_failures # maximum number of consecutive failures
		attempts = bpy.context.scene.an7_point_gen_settings.max_attempts # maximum number of iterations to try and meet the target number of points
		# Properties settings
		dimensions = True if bpy.context.scene.an7_point_gen_settings.walk_dimensions == "3D" else False
		directionality = bpy.context.scene.an7_point_gen_settings.walk_directionality
		direction_vector = bpy.context.scene.an7_point_gen_settings.walk_vector
		rotation = bpy.context.scene.an7_point_gen_settings.walk_rotation
		rMinimum = bpy.context.scene.an7_point_gen_settings.radius_min # minimum radius of the generated point
		rMaximum = bpy.context.scene.an7_point_gen_settings.radius_max # maximum radius of the generated point
		rDecay = bpy.context.scene.an7_point_gen_settings.radius_decay

		# Get the currently active object
		obj = bpy.context.object

		# Create a new bmesh
		bm = bmesh.new()

		# Set up attribute layers
		pi = bm.verts.layers.float.new('index')
		ps = bm.verts.layers.float.new('scale')
		pr = bm.verts.layers.float_vector.new('rotation')

		# Start timer
		timer = str(time.time())

		# Create points with poisson disc sampling
		points = []
		count = 0
		failmax = 0 # This is entirely for reporting purposes and is not needed structurally
		iteration = 0
		rPrevious = 0.0 # This stores the radius of the previous iteration so we can offset the current iteration correctly
		pPrevious = Vector([0.0, 0.0, 0.0])

		# Loop until we're too tired to continue...
		while len(points) < elements and count < failures and iteration < attempts:
			iteration += 1
			count += 1

			# Create check system (this prevents unnecessary cycles by exiting early if possible)
			check = 0

			# Generate random radius
			if rDecay:
				lerp = len(points) / elements
				radius = uniform(rMinimum, (rMinimum * lerp) + (rMaximum * (1.0 - lerp)))
			else:
				radius = uniform(rMinimum, rMaximum)

			# If this is the first iteration, just add a point at 0,0,0
			if len(points) == 0:
				points.append([0.0, 0.0, 0.0, radius])
				rPrevious = radius
				# And quit early (no need to check anything)
				continue

			# Generate random vector
			if dimensions:
				vec = Vector([uniform(-1.0, 1.0), uniform(-1.0, 1.0), uniform(-1.0, 1.0)])
			else:
				vec = Vector([uniform(-1.0, 1.0), uniform(-1.0, 1.0), 0.0])
			# Blend
			if directionality > 0.0:
				vec = vec.lerp(direction_vector, directionality)
			# Normalise
			vec = vec.normalized()

			# Scale and offset the random vector using the radius of the previous iteration and the current iteration, along with the previous position
			vec *= radius + rPrevious
			vec += pPrevious
			# Don't replace the previous radius and position variables until after we've determined if this current point is going to work

			# Create point data array
			point = [vec[0], vec[1], vec[2], radius]

			# Check if it overlaps with other radii
			i = 0
			while i < len(points) and check == 0:
				if Vector([points[i][0]-point[0], points[i][1]-point[1], points[i][2]-point[2]]).length < (points[i][3] + point[3]):
					check = 1
				i += 1

			# If no collisions are detected, add the point to the list and reset the failure counter
			if check == 0:
				points.append(point)
				# Finally, we have a winner! We can replace the previous radius and position variables
				rPrevious = radius
				pPrevious = vec
				# And now some data housekeeping
				failmax = max(failmax, count) # This is entirely for reporting purposes and is not needed structurally
				count = 0

		# One last check, in case the stop cause was maximum failure count and this value wasn't updated in a successful check status
		failmax = max(failmax, count) # This is entirely for reporting purposes and is not needed structurally

		pointsEnd = len(points) - 1
		# Create vertices from the points list
		for i, p in enumerate(points):
			v = bm.verts.new((p[0], p[1], p[2]))
			v[pi] = 0.0 if i == 0 else float(i) / float(len(points) - 1)
			v[ps] = p[3]
			# Point rotations
			tempX = 0.0
			tempY = 0.0
			tempZ = 0.0
			if rotation == "AHEAD":
				if i < pointsEnd:
					tempX = points[i+1][0] - p[0]
					tempY = points[i+1][1] - p[1]
					tempZ = points[i+1][2] - p[2]
				v[pr] = Vector([tempX, tempY, tempZ]).to_track_quat('X', 'Z').to_euler()
			elif rotation == "BEHIND":
				if i == 0:
					tempX = points[1][0] - p[0]
					tempY = points[1][1] - p[1]
					tempZ = points[1][2] - p[2]
				else:
					tempX = p[0] - points[i-1][0]
					tempY = p[1] - points[i-1][1]
					tempZ = p[2] - points[i-1][2]
				v[pr] = Vector([tempX, tempY, tempZ]).to_track_quat('-X', 'Z').to_euler()
			else:
				v[pr] = Vector([uniform(-math.pi, math.pi), uniform(-math.pi, math.pi), uniform(-math.pi, math.pi)])

		# Update the feedback strings
		context.scene.an7_point_gen_settings.feedback_elements = str(len(points))
		context.scene.an7_point_gen_settings.feedback_failures = str(failmax)
		context.scene.an7_point_gen_settings.feedback_attempts = str(iteration)
		context.scene.an7_point_gen_settings.feedback_time = str(round(time.time() - float(timer), 2))

		bm.to_mesh(obj.data)
		bm.free()
		obj.data.update() # This ensures the viewport updates

		return {'FINISHED'}

class AN7_Point_Grid(bpy.types.Operator):
	bl_idname = "an7pointgrid.offset"
	bl_label = "Replace Mesh" # "Create Points" is a lot nicer, but I'm concerned this is a real easy kill switch for important geometry!
	bl_description = "Create points using the selected options, deleting and replacing the currently selected mesh"
	bl_options = {'REGISTER', 'UNDO'}

	def execute(self, context):
		# Properties settings
		gridX = bpy.context.scene.an7_point_gen_settings.grid_count_X
		gridY = bpy.context.scene.an7_point_gen_settings.grid_count_Y
		radius = bpy.context.scene.an7_point_gen_settings.grid_spacing
		# Recursion settings
		recursion = bpy.context.scene.an7_point_gen_settings.division_levels
		percentage = bpy.context.scene.an7_point_gen_settings.division_percentage

		# Get the currently active object
		obj = bpy.context.object

		# Create a new bmesh
		bm = bmesh.new()

		# Set up attribute layers
		pi = bm.verts.layers.float.new('index')
		ps = bm.verts.layers.float.new('scale')
		pr = bm.verts.layers.float_vector.new('rotation')

		# Create initial grid
		grid = []
		for x in range(0, gridX):
			for y in range(0, gridY):
				grid.append([(float(x) - gridX*0.5 + 0.5)*radius*2, (float(y) - gridY*0.5 + 0.5)*radius*2, 0.0, radius])

		# Subdivide the grid
		rec = 0
		gridA = []
		gridB = []
		while rec < recursion:
			rec += 1
			shuffle(grid)
			for i, p in enumerate(grid):
				if float(i) / float(len(grid)) < percentage:
					gridA.append([p[0] + (p[3] * 0.5), p[1] - (p[3] * 0.5), p[2], p[3] * 0.5])
					gridA.append([p[0] + (p[3] * 0.5), p[1] + (p[3] * 0.5), p[2], p[3] * 0.5])
					gridA.append([p[0] - (p[3] * 0.5), p[1] + (p[3] * 0.5), p[2], p[3] * 0.5])
					gridA.append([p[0] - (p[3] * 0.5), p[1] - (p[3] * 0.5), p[2], p[3] * 0.5])
				else:
					gridB.append(p)
			grid = deepcopy(gridA)
			gridA.clear()

		shuffle(grid)
		gridB.extend(grid)

		# Create vertices from the points list
		for i, p in enumerate(gridB):
			v = bm.verts.new((p[0], p[1], p[2]))
			v[pi] = 0.0 if i == 0 else float(i) / float(len(gridB) - 1)
			v[ps] = p[3]
			if bpy.context.scene.an7_point_gen_settings.random_rotation:
				v[pr] = Vector([0.0, 0.0, float(randint(0, 3)) * 1.570796326794896619231321691639751]) # 90° in radians
			else:
				v[pr] = Vector([0.0, 0.0, 0.0])

		# Replace object with new mesh data
		bm.to_mesh(obj.data)
		bm.free()
		obj.data.update() # This ensures the viewport updates

		return {'FINISHED'}

class AN7_Point_Tri(bpy.types.Operator):
	bl_idname = "an7pointtri.offset"
	bl_label = "Replace Mesh" # "Create Points" is a lot nicer, but I'm concerned this is a real easy kill switch for important geometry!
	bl_description = "Create points using the selected options, deleting and replacing the currently selected mesh"
	bl_options = {'REGISTER', 'UNDO'}

	def execute(self, context):
		# Properties settings
		count = bpy.context.scene.an7_point_gen_settings.tri_count
		radius = bpy.context.scene.an7_point_gen_settings.grid_spacing
		offset = count * radius
		# Recursion settings
		recursion = bpy.context.scene.an7_point_gen_settings.division_levels
		percentage = bpy.context.scene.an7_point_gen_settings.division_percentage
		# Positional variables
		x = radius * 0.8660254037844386467637231707529361834714026269051903140279034897 # sine 60°
		y = radius * 0.5 # cosine 60°

		# Get the currently active object
		obj = bpy.context.object

		# Create a new bmesh
		bm = bmesh.new()

		# Set up attribute layers
		pi = bm.verts.layers.float.new('index')
		ps = bm.verts.layers.float.new('scale')
		pr = bm.verts.layers.float_vector.new('rotation')

		# Create initial grid
		grid = []
		for a in range(0, count):
			for b in range(0, a * 2 + 1):
				# Hexagonal grid points with triangular directions are created, and then shifted in counter-clockwise directions to fill out each row
				# Except I'm not doing the math for all of these to rotate in the same direction from 6 individual spokes...I'm just mirroring the first two to fill out all six "panels"...I feel like it's impure/cheating, but the order is randomised to do the division anyway, so what does it matter?
				# A = column start
				# B = row offset
				odd = math.floor(b % 2)
				rotation = math.pi if odd == 0 else 0.0 # determine the orientation of the element
					# Triangular array (just the top-middle of the Tri-Hex pattern)
				grid.append([(float(a) - float(b)) * x, (float(a) * 1.5 + 1.0 - odd * 0.5) * radius - offset, 0.0, radius, rotation])

		# Subdivide the grid (same as the Tri-Hex pattern)
		rec = 0
		gridA = []
		gridB = []
		while rec < recursion:
			rec += 1
			shuffle(grid)
			for i, p in enumerate(grid):
				if (float(i) / float(len(grid))) < percentage:
					# Recursion variables
					s = 1.0 if p[4] < 1.0 else -1.0 # determine the orientation of the element, which will flip all of our coordinates as needed
					s /= (2.0 ** float(rec)) # scale multiplier based on the current recursion level
					r = radius * abs(s) # calculate radius for this recursion level
					rotationA = math.pi if s < 0.0 else 0.0 # invert the rotation of the original point
					rotationB = math.pi if rotationA == 0.0 else 0.0 # invert it again...what...why...somehow nothing is working how I want it to!
					# Divide triangular space into four elements
						# middle
					gridA.append([p[0], p[1], 0.0, r, rotationB])
						# top
					gridA.append([p[0], p[1] + radius * s, 0.0, r, rotationA])
						# lower left
					gridA.append([p[0] + x * s, p[1] - radius * s * 0.5, 0.0, r, rotationA])
						# lower right
					gridA.append([p[0] - x * s, p[1] - radius * s * 0.5, 0.0, r, rotationA])
				else:
					gridB.append(p) # these aren't iterated over again, which is why we're not doing any compounding math in the recursion variables...it's entirely recursion level based, no compounding (where any level of recursion might be subdivided...the system gets more complicated, and it means most elements will tend toward medium-levels of division, with very few undivided or fully divided segments in the results)
			grid = deepcopy(gridA)
			gridA.clear()

		shuffle(grid)
		gridB.extend(grid)

		# Create vertices from the points list
		for i, p in enumerate(gridB):
			v = bm.verts.new((p[0], p[1], p[2]))
			v[pi] = 0.0 if i == 0 else float(i) / float(len(gridB) - 1)
			v[ps] = p[3]
			if bpy.context.scene.an7_point_gen_settings.random_rotation:
				v[pr] = Vector([0.0, 0.0, p[4] + float(randint(0, 2)) * 2.094395102393195492308428922186335]) # 120° in radians
			else:
				v[pr] = Vector([0.0, 0.0, p[4]])

		# Replace object with new mesh data
		bm.to_mesh(obj.data)
		bm.free()
		obj.data.update() # This ensures the viewport updates

		return {'FINISHED'}

class AN7_Point_TriHex(bpy.types.Operator):
	bl_idname = "an7pointtrihex.offset"
	bl_label = "Replace Mesh" # "Create Points" is a lot nicer, but I'm concerned this is a real easy kill switch for important geometry!
	bl_description = "Create points using the selected options, deleting and replacing the currently selected mesh"
	bl_options = {'REGISTER', 'UNDO'}

	def execute(self, context):
		# Properties settings
		count = bpy.context.scene.an7_point_gen_settings.hex_count
		radius = bpy.context.scene.an7_point_gen_settings.grid_spacing
		# Recursion settings
		recursion = bpy.context.scene.an7_point_gen_settings.division_levels
		percentage = bpy.context.scene.an7_point_gen_settings.division_percentage
		# Positional variables
		x = radius * 0.8660254037844386467637231707529361834714026269051903140279034897 # sine 60°
		y = radius * 0.5 # cosine 60°

		# Get the currently active object
		obj = bpy.context.object

		# Create a new bmesh
		bm = bmesh.new()

		# Set up attribute layers
		pi = bm.verts.layers.float.new('index')
		ps = bm.verts.layers.float.new('scale')
		pr = bm.verts.layers.float_vector.new('rotation')

		# Create initial grid
		grid = []
		for a in range(0, count):
			for b in range(0, a * 2 + 1):
				# Hexagonal grid points with triangular directions are created, and then shifted in counter-clockwise directions to fill out each row
				# Except I'm not doing the math for all of these to rotate in the same direction from 6 individual spokes...I'm just mirroring the first two to fill out all six "panels"...I feel like it's impure/cheating, but the order is randomised to do the division anyway, so what does it matter?
				# A = column start
				# B = row offset
				odd = math.floor(b % 2)
				rotA = 0.0 if odd == 0 else math.pi # determine the orientation of the element
				rotB = math.pi if odd == 0 else 0.0 # determine the orientation of the element
					# top-middle
				grid.append([(float(a) - float(b)) * x, (float(a) * 1.5 + 1.0 - odd * 0.5) * radius, 0.0, radius, rotB])
					# top-right
				grid.append([(float(a * 2 + 1) - math.floor(float(b) * 0.5 + 0.5)) * x, (float(b) * 1.5 + 1.0 - odd * 0.5) * 0.5 * radius, 0.0, radius, rotA])
					# top-left (x-mirror of top-right)
				grid.append([(float(a * 2 + 1) - math.floor(float(b) * 0.5 + 0.5)) * -x, (float(b) * 1.5 + 1.0 - odd * 0.5) * 0.5 * radius, 0.0, radius, rotA])
					# bottom-middle (y-mirror of top-middle)
				grid.append([(float(a) - float(b)) * x, (float(a) * 1.5 + 1.0 - odd * 0.5) * -radius, 0.0, radius, rotA])
					# bottom-right (y-mirror of top-right)
				grid.append([(float(a * 2 + 1) - math.floor(float(b) * 0.5 + 0.5)) * x, (float(b) * 1.5 + 1.0 - odd * 0.5) * 0.5 * -radius, 0.0, radius, rotB])
					# top-left (x&y-mirror of top-right)
				grid.append([(float(a * 2 + 1) - math.floor(float(b) * 0.5 + 0.5)) * -x, (float(b) * 1.5 + 1.0 - odd * 0.5) * 0.5 * -radius, 0.0, radius, rotB])

		# Subdivide the grid
		rec = 0
		gridA = []
		gridB = []
		while rec < recursion:
			rec += 1
			shuffle(grid)
			for i, p in enumerate(grid):
				if (float(i) / float(len(grid))) < percentage:
					# Recursion variables
					print("p:")
					print(p)
					print("p[4]:")
					print(p[4])
					s = 1.0 if p[4] < 1.0 else -1.0 # determine the orientation of the element, which will flip all of our coordinates as needed
					s /= (2.0 ** float(rec)) # scale multiplier based on the current recursion level
					r = radius * abs(s) # calculate radius for this recursion level
					rotationA = math.pi if s < 0.0 else 0.0 # invert the rotation of the original point
					rotationB = math.pi if rotationA == 0.0 else 0.0 # invert it again...what...why...somehow nothing is working how I want it to!
					# Divide triangular space into four elements
						# middle
					gridA.append([p[0], p[1], 0.0, r, rotationB])
						# top
					gridA.append([p[0], p[1] + radius * s, 0.0, r, rotationA])
						# lower left
					gridA.append([p[0] + x * s, p[1] - radius * s * 0.5, 0.0, r, rotationA])
						# lower right
					gridA.append([p[0] - x * s, p[1] - radius * s * 0.5, 0.0, r, rotationA])
				else:
					gridB.append(p) # these aren't iterated over again, which is why we're not doing any compounding math in the recursion variables...it's entirely recursion level based, no compounding (where any level of recursion might be subdivided...the system gets more complicated, and it means most elements will tend toward medium-levels of division, with very few undivided or fully divided segments in the results)
			grid = deepcopy(gridA)
			gridA.clear()

		shuffle(grid)
		gridB.extend(grid)

		# Create vertices from the points list
		for i, p in enumerate(gridB):
			v = bm.verts.new((p[0], p[1], p[2]))
			v[pi] = 0.0 if i == 0 else float(i) / float(len(gridB) - 1)
			v[ps] = p[3]
			if bpy.context.scene.an7_point_gen_settings.random_rotation:
				v[pr] = Vector([0.0, 0.0, p[4] + float(randint(0, 2)) * 2.094395102393195492308428922186335]) # 120° in radians
			else:
				v[pr] = Vector([0.0, 0.0, p[4]])

		# Replace object with new mesh data
		bm.to_mesh(obj.data)
		bm.free()
		obj.data.update() # This ensures the viewport updates

		return {'FINISHED'}

class AN7_Point_Hex(bpy.types.Operator):
	bl_idname = "an7pointhex.offset"
	bl_label = "Replace Mesh" # "Create Points" is a lot nicer, but I'm concerned this is a real easy kill switch for important geometry!
	bl_description = "Create points using the selected options, deleting and replacing the currently selected mesh"
	bl_options = {'REGISTER', 'UNDO'}

	def execute(self, context):
		# Properties settings
		count = bpy.context.scene.an7_point_gen_settings.hex_count
		radius = bpy.context.scene.an7_point_gen_settings.grid_spacing
		space = radius * 2.0 * 0.8660254037844386467637231707529361834714026269051903140279034897 # compensate the spacing for a "furthest-point" radius (which is how hexagons are generated using Cylinders in Blender) not a "flat side" radius (which is a larger object)
		# Recursion settings
		recursion = bpy.context.scene.an7_point_gen_settings.division_levels
		percentage = bpy.context.scene.an7_point_gen_settings.division_percentage
		# Positional variables
		x = space * 0.5 # cosine 60°
		y = space * 0.8660254037844386467637231707529361834714026269051903140279034897 # sine 60°

		# Get the currently active object
		obj = bpy.context.object

		# Create a new bmesh
		bm = bmesh.new()

		# Set up attribute layers
		pi = bm.verts.layers.float.new('index')
		ps = bm.verts.layers.float.new('scale')
		pr = bm.verts.layers.float_vector.new('rotation')

		# Create initial grid
		grid = []
		grid.append([0.0, 0.0, 0.0, radius])
		for a in range(1, count):
			for b in range(0, a):
				# Hexagonal grid points are created, and then shifted in counter-clockwise directions to fill out each row
				# A = column start
				# B = row offset
					# upper left column and row
				grid.append([float(a) * x - float(b) * space, float(a) * y, 0.0, radius])
					# left
				grid.append([float(a) * space - float(b) * x, float(b) * y, 0.0, radius])
					# lower left
				grid.append([float(a + b) * x, float(-a + b) * y, 0.0, radius])
					# lower right
				grid.append([float(-a) * x + float(b) * space, float(-a) * y, 0.0, radius])
					# right
				grid.append([float(-a) * space + float(b) * x, float(-b) * y, 0.0, radius])
					# upper right
				grid.append([float(-a - b) * x, float(a - b) * y, 0.0, radius])

		# Subdivide the grid
		rec = 0
		gridA = []
		gridB = []
		while rec < recursion:
			rec += 1
			shuffle(grid)
			for i, p in enumerate(grid):
				# Recursion variables
				s = space / (2.0 ** (float(rec) * 1.0)) / 3.0
				if bpy.context.scene.an7_point_gen_settings.random_rotation and randint(0, 1) == 0: # randomly flip the layout values to prevent recursive triangle formations (thanks to hexagons not dividing into more hexagons)
					s = -s
				r = p[3] * 0.5
				if float(i) / float(len(grid)) < percentage:
					# Divide hexagon space into three (hexagons don't divide into more hexagons, so this is the compromise we're making)
						# top
					gridA.append([p[0], p[1] + space * s, 0.0, r])
						# lower left
					gridA.append([p[0] + y * s, p[1] - x * s, 0.0, r])
						# lower right
					gridA.append([p[0] - y * s, p[1] - x * s, 0.0, r])
				else:
					gridB.append(p)
			grid = deepcopy(gridA)
			gridA.clear()

		shuffle(grid)
		gridB.extend(grid)

		# Create vertices from the points list
		for i, p in enumerate(gridB):
			v = bm.verts.new((p[0], p[1], p[2]))
			v[pi] = 0.0 if i == 0 else float(i) / float(len(gridB) - 1)
			v[ps] = p[3]
			if bpy.context.scene.an7_point_gen_settings.random_rotation:
				v[pr] = Vector([0.0, 0.0, float(randint(0, 5)) * 1.047197551196597746154214461093168]) # 60° in radians
			else:
				v[pr] = Vector([0.0, 0.0, 0.0])

		# Replace object with new mesh data
		bm.to_mesh(obj.data)
		bm.free()
		obj.data.update() # This ensures the viewport updates

		return {'FINISHED'}

###########################################################################
# User preferences and UI rendering class

class AN7PointGenPreferences(bpy.types.AddonPreferences):
	bl_idname = __name__

	show_feedback: bpy.props.BoolProperty(
		name="Show Processing Feedback",
		description='Displays relevant statistics from the last generated array',
		default=True)

	def draw(self, context):
		layout = self.layout
		layout.prop(self, "show_feedback")

###########################################################################
# Project settings and UI rendering classes

class an7PointGenSettings(bpy.types.PropertyGroup):
	gen_type: bpy.props.EnumProperty(
		name='Array Type',
		description='Point array format',
		items=[
			('GRID', 'Rectangular Array', 'Rectangular layout of square points'),
			('TRI', 'Triangular Array', 'Triangular layout of triangular points'),
			('TRIHEX', 'Tri-Hex Array', 'Hexagonal layout of triangular points'),
			('HEX', 'Hexagonal Array', 'Hexagonal layout of hexagonal points (will not subdivide without gaps)'),
			('WALK', 'Random Walk', 'Generates a random string of points')
			],
		default='GRID')

	# Grid settings
	grid_count_X: bpy.props.IntProperty(
		name="Grid Count",
		description="Number of starting elements in the X axis",
		default=8,
		soft_min=2,
		soft_max=20,
		min=2,
		max=100,)
	grid_count_Y: bpy.props.IntProperty(
		name="Grid Count",
		description="Number of starting elements in the Y axis",
		default=8,
		soft_min=2,
		soft_max=20,
		min=2,
		max=100,)

	# Triangular settings
	tri_count: bpy.props.IntProperty(
		name="Array Count",
		description="Number of starting elements in the radius axis",
		default=8,
		soft_min=2,
		soft_max=20,
		min=2,
		max=100,)

	# Hexagonal settings
	hex_count: bpy.props.IntProperty(
		name="Array Count",
		description="Number of starting elements in the radius axis",
		default=4,
		soft_min=1,
		soft_max=10,
		min=1,
		max=100,)

	# Shared settings
	grid_spacing: bpy.props.FloatProperty(
		name="Grid Spacing",
		description="Spacing of each grid point at 0 divisions",
		default=0.2,
		step=10,
		soft_min=0.1,
		soft_max=1.0,
		min=0.0001,
		max=10.0,)
	random_rotation: bpy.props.BoolProperty(
		name="Random Rotation",
		description="Rotate each point randomly, automatically limited to appropriate increments",
		default=True,)
	division_levels: bpy.props.IntProperty(
		name="Divisions",
		description="The number of times the algorithm will loop through dividing points",
		default=2,
		soft_min=0,
		soft_max=4,
		min=0,
		max=8,)
	division_percentage: bpy.props.FloatProperty(
		name="Percentage",
		description="Percentage chance that points will be selected for division",
		default=0.5,
		step=10,
		soft_min=0.0,
		soft_max=1.0,
		min=0.0,
		max=1.0,)

	# Sphere Walk settings
	walk_dimensions: bpy.props.EnumProperty(
		name='Area Shape',
		description='Mask for the area where points will be created',
		items=[
			('2D', '2D', 'Randomly walk in only X and Y dimensions'),
			('3D', '3D', 'Randomly generate points in all 3 dimensions'),
			],
		default='3D')
	walk_directionality: bpy.props.FloatProperty(
		name="Directionality",
		description="Amount to favour the specified vector when generating each step",
		default=0.0,
		step=10,
		soft_min=0.0,
		soft_max=1.0,
		min=0.0,
		max=1.0,)
	walk_vector: bpy.props.FloatVectorProperty(
		name="Vector",
		subtype="XYZ",
		description="Vector to favour when generating each step",
		default=[1.0, 0.0, 0.0],
		soft_min=-1.0,
		soft_max=1.0,
		min=-1.0,
		max=1.0,)

	radius_min: bpy.props.FloatProperty(
		name="Point Radius",
		description="Minimum scale of the generated points",
		default=0.2,
		step=10,
		soft_min=0.1,
		soft_max=1.0,
		min=0.0001,
		max=10.0,)
	radius_max: bpy.props.FloatProperty(
		name="Point Radius Maximum",
		description="Maximum scale of the generated points",
		default=0.8,
		step=10,
		soft_min=0.1,
		soft_max=1.0,
		min=0.0001,
		max=10.0,)
	radius_decay: bpy.props.BoolProperty(
		name="Radius Decay",
		description='Linearly reduces the maximum radius based on number of recursions and maximum number of elements',
		default=False)

	walk_rotation: bpy.props.EnumProperty(
		name='Rotation',
		description='Mask for the area where points will be created',
		items=[
			('RANDOM', 'Random', 'Assign a random rotation to each point'),
			('AHEAD', 'Look Ahead', 'Each point will aim at the next point in the sequence'),
			('BEHIND', 'Look Behind', 'Each point will aim at the previous point in the sequence'),
			],
		default='RANDOM')

	max_elements: bpy.props.IntProperty(
		name="Max Points",
		description="The maximum number of points that can be created (higher numbers will attempt to fill the space more)",
		default=300,
		soft_min=10,
		soft_max=1000,
		min=1,
		max=10000,)
	max_failures: bpy.props.IntProperty(
		name="Max Failures",
		description="The maximum number of consecutive failures before quitting (higher numbers won't give up when the odds are poor)",
		default=1000,
		soft_min=100,
		soft_max=10000,
		min=10,
		max=100000,)
	max_attempts: bpy.props.IntProperty(
		name="Max Attempts",
		description="The maximum number of placement attempts before quitting (higher numbers can take minutes to process)",
		default=10000,
		soft_min=1000,
		soft_max=100000,
		min=100,
		max=1000000,)

	feedback_elements: bpy.props.StringProperty(
		name="Feedback",
		description="Stores the total points from the last created array",
		default="",)
	feedback_failures: bpy.props.StringProperty(
		name="Feedback",
		description="Stores the maximum number of consecutive failures from the last created array",
		default="",)
	feedback_attempts: bpy.props.StringProperty(
		name="Feedback",
		description="Stores the total attempts from the last created array",
		default="",)
	feedback_time: bpy.props.StringProperty(
		name="Feedback",
		description="Stores the total time spent processing the last created array",
		default="",)

class AN7TOOLS_PT_point_gen(bpy.types.Panel):
	bl_space_type = "VIEW_3D"
	bl_region_type = "UI"
	bl_category = 'AN7 Tools'
	bl_order = 0
	bl_label = "Point Generator"
	bl_idname = "AN7TOOLS_PT_point_gen"

	@classmethod
	def poll(cls, context):
		return True

	def draw_header(self, context):
		try:
			layout = self.layout
		except Exception as exc:
			print(str(exc) + " | Error in the AN7 Point Generator panel header")

	def draw(self, context):
		try:
			layout = self.layout
			layout.use_property_split = True
			layout.use_property_decorate = False # No animation

			layout.prop(context.scene.an7_point_gen_settings, 'gen_type')

			# Rectangular Array
			if bpy.context.scene.an7_point_gen_settings.gen_type == "GRID":
				row = layout.row()
				row.prop(context.scene.an7_point_gen_settings, 'grid_count_X')
				row.prop(context.scene.an7_point_gen_settings, 'grid_count_Y', text="")
				layout.prop(context.scene.an7_point_gen_settings, 'grid_spacing')
				layout.prop(context.scene.an7_point_gen_settings, 'random_rotation')
				layout.prop(context.scene.an7_point_gen_settings, 'division_levels')
				layout.prop(context.scene.an7_point_gen_settings, 'division_percentage')
				box = layout.box()
				if bpy.context.view_layer.objects.active.type == "MESH" and bpy.context.object.mode == "OBJECT":
					layout.operator(AN7_Point_Grid.bl_idname)
					pointStart = bpy.context.scene.an7_point_gen_settings.grid_count_X * bpy.context.scene.an7_point_gen_settings.grid_count_Y
					pointCount = pointStart
					i = 0
					while i < bpy.context.scene.an7_point_gen_settings.division_levels:
						i += 1
						# example equation for an 8x8 grid: 64+(64*.5*3)+((64*.5*4)*.5*3)+(((64*.5*4)*.5*4)*.5*3)
						# there has to be a clever way to handle this, but I'm no mathematician
						pointStart *= bpy.context.scene.an7_point_gen_settings.division_percentage
						pointStart = math.ceil(pointStart) # fix the floating point discrepancy between this calculation and the simple "<" comparison in the loop code
						pointCount += pointStart * 3
						pointStart *= 4
					box.label(text="Generate " + str(int(pointCount)) + " points")
					box.label(text="WARNING: replaces mesh")

			# Triangular Array
			if bpy.context.scene.an7_point_gen_settings.gen_type == "TRI":
				layout.prop(context.scene.an7_point_gen_settings, 'tri_count')
				layout.prop(context.scene.an7_point_gen_settings, 'grid_spacing')
				layout.prop(context.scene.an7_point_gen_settings, 'random_rotation')
				layout.prop(context.scene.an7_point_gen_settings, 'division_levels')
				layout.prop(context.scene.an7_point_gen_settings, 'division_percentage')
				box = layout.box()
				if bpy.context.view_layer.objects.active.type == "MESH" and bpy.context.object.mode == "OBJECT":
					layout.operator(AN7_Point_Tri.bl_idname)
					pointStart = bpy.context.scene.an7_point_gen_settings.tri_count ** 2
					pointCount = pointStart
					i = 0
					while i < bpy.context.scene.an7_point_gen_settings.division_levels:
						i += 1
						pointStart *= bpy.context.scene.an7_point_gen_settings.division_percentage
						pointStart = math.ceil(pointStart) # fix the floating point discrepancy between this calculation and the simple "<" comparison in the loop code
						pointCount += pointStart * 3
						pointStart *= 4
					box.label(text="Generate " + str(int(pointCount)) + " points")
					box.label(text="WARNING: replaces mesh")

			# Tri-Hex Array
			if bpy.context.scene.an7_point_gen_settings.gen_type == "TRIHEX":
				layout.prop(context.scene.an7_point_gen_settings, 'hex_count')
				layout.prop(context.scene.an7_point_gen_settings, 'grid_spacing')
				layout.prop(context.scene.an7_point_gen_settings, 'random_rotation')
				layout.prop(context.scene.an7_point_gen_settings, 'division_levels')
				layout.prop(context.scene.an7_point_gen_settings, 'division_percentage')
				box = layout.box()
				if bpy.context.view_layer.objects.active.type == "MESH" and bpy.context.object.mode == "OBJECT":
					layout.operator(AN7_Point_TriHex.bl_idname)
					pointStart = 6 * (bpy.context.scene.an7_point_gen_settings.hex_count ** 2)
					pointCount = pointStart
					i = 0
					while i < bpy.context.scene.an7_point_gen_settings.division_levels:
						i += 1
						pointStart *= bpy.context.scene.an7_point_gen_settings.division_percentage
						pointStart = math.ceil(pointStart) # fix the floating point discrepancy between this calculation and the simple "<" comparison in the loop code
						pointCount += pointStart * 3
						pointStart *= 4
					box.label(text="Generate " + str(int(pointCount)) + " points")
					box.label(text="WARNING: replaces mesh")

			# Hexagonal Array
			if bpy.context.scene.an7_point_gen_settings.gen_type == "HEX":
				layout.prop(context.scene.an7_point_gen_settings, 'hex_count')
				layout.prop(context.scene.an7_point_gen_settings, 'grid_spacing')
				layout.prop(context.scene.an7_point_gen_settings, 'random_rotation')
				layout.prop(context.scene.an7_point_gen_settings, 'division_levels')
				layout.prop(context.scene.an7_point_gen_settings, 'division_percentage')
				box = layout.box()
				if bpy.context.view_layer.objects.active.type == "MESH" and bpy.context.object.mode == "OBJECT":
					layout.operator(AN7_Point_Hex.bl_idname)
					pointStart = 3 * (bpy.context.scene.an7_point_gen_settings.hex_count ** 2) - 3 * bpy.context.scene.an7_point_gen_settings.hex_count + 1
					pointCount = pointStart
					i = 0
					while i < bpy.context.scene.an7_point_gen_settings.division_levels:
						i += 1
						pointStart *= bpy.context.scene.an7_point_gen_settings.division_percentage
						pointStart = math.ceil(pointStart) # fix the floating point discrepancy between this calculation and the simple "<" comparison in the loop code
						pointCount += pointStart * 2
						pointStart *= 3
					box.label(text="Generate " + str(int(pointCount)) + " points")
					box.label(text="WARNING: replaces mesh")

			# Random Walk
			elif bpy.context.scene.an7_point_gen_settings.gen_type == "WALK":
				layout.prop(context.scene.an7_point_gen_settings, 'walk_dimensions')
				layout.prop(context.scene.an7_point_gen_settings, 'walk_directionality')
				if bpy.context.scene.an7_point_gen_settings.walk_directionality > 0.0:
					col=layout.column()
					col.prop(context.scene.an7_point_gen_settings, 'walk_vector')

				row = layout.row()
				row.prop(context.scene.an7_point_gen_settings, 'radius_min')
				row.prop(context.scene.an7_point_gen_settings, 'radius_max')
				layout.prop(context.scene.an7_point_gen_settings, 'radius_decay')

				layout.prop(context.scene.an7_point_gen_settings, 'walk_rotation')

				layout.prop(context.scene.an7_point_gen_settings, 'max_elements')
				layout.prop(context.scene.an7_point_gen_settings, 'max_failures')
				layout.prop(context.scene.an7_point_gen_settings, 'max_attempts')

				box = layout.box()
				if bpy.context.view_layer.objects.active.type == "MESH" and bpy.context.object.mode == "OBJECT":
					layout.operator(AN7_Point_Walk.bl_idname)
					if len(context.scene.an7_point_gen_settings.feedback_time) > 0 and bpy.context.preferences.addons['AN7_pointGen'].preferences.show_feedback:
						boxcol=box.column()
						boxcol.label(text="Points created: " + context.scene.an7_point_gen_settings.feedback_elements)
						boxcol.label(text="Successive fails: " + context.scene.an7_point_gen_settings.feedback_failures) # Alternative: consecutive?
						boxcol.label(text="Total attempts: " + context.scene.an7_point_gen_settings.feedback_attempts)
						boxcol.label(text="Processing Time: " + context.scene.an7_point_gen_settings.feedback_time)
					box.label(text="WARNING: replaces mesh")

			# Guidance feedback (coach the user on what will enable processing)
			if bpy.context.view_layer.objects.active.type != "MESH":
				box.label(text="Active item must be a mesh")
			elif bpy.context.object.mode != "OBJECT":
				box.label(text="Must be in object mode")

		except Exception as exc:
			print(str(exc) + " | Error in the AN7 Point Generator panel")

classes = (AN7PointGenPreferences, AN7_Point_Walk, AN7_Point_Grid, AN7_Point_Tri, AN7_Point_TriHex, AN7_Point_Hex, an7PointGenSettings, AN7TOOLS_PT_point_gen)

###########################################################################
# Addon registration functions

def register():
	for cls in classes:
		bpy.utils.register_class(cls)
	bpy.types.Scene.an7_point_gen_settings = bpy.props.PointerProperty(type=an7PointGenSettings)

def unregister():
	for cls in reversed(classes):
		bpy.utils.unregister_class(cls)
	del bpy.types.Scene.an7_point_gen_settings

if __name__ == "__main__":
	register()
