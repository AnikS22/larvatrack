# Fly treadmill - builds the assembly in Fusion 360 with WORKING revolute joints.
# Run: Fusion 360 -> Utilities -> ADD-INS -> Scripts and Add-Ins -> Scripts tab ->
#      green "+" -> pick this folder -> select FlyTreadmill -> Run
#
# Fusion works in CENTIMETRES internally, so every mm value below is divided by 10.

import adsk.core, adsk.fusion, traceback

MM = 0.1  # mm -> cm

# ---- the numbers (mm) ----
SPAN      = 78.0    # pulley centre to pulley centre
AXIS_H    = 16.0    # shaft axis above the frame floor
FRAME_L   = 116.2
FRAME_W   = 32.0    # outside width
WALL      = 4.0
FLOOR_T   = 3.0
GAP       = FRAME_W - 2 * WALL     # 24.0 between the walls
SHAFT_D   = 5.0
PULLEY_OD = 12.22   # over the tooth tips, 20T GT2
FLANGE_D  = 17.0
FLANGE_T  = 1.2
BELT_W    = 7.0     # channel between the flanges


def box(comp, name, x, y, z, w, d, h):
    """axis-aligned box, corner at (x,y,z), size w x d x h, all mm"""
    sk = comp.sketches.add(comp.xYConstructionPlane)
    p = adsk.core.Point3D.create
    sk.sketchCurves.sketchLines.addTwoPointRectangle(
        p(x * MM, y * MM, 0), p((x + w) * MM, (y + d) * MM, 0))
    prof = sk.profiles.item(0)
    inp = comp.features.extrudeFeatures.createInput(
        prof, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    inp.setDistanceExtent(False, adsk.core.ValueInput.createByReal(h * MM))
    ext = comp.features.extrudeFeatures.add(inp)
    body = ext.bodies.item(0)
    body.name = name
    # lift it to z
    if abs(z) > 1e-9:
        mv = adsk.core.ObjectCollection.create(); mv.add(body)
        t = adsk.core.Matrix3D.create()
        t.translation = adsk.core.Vector3D.create(0, 0, z * MM)
        mi = comp.features.moveFeatures.createInput(mv, t)
        comp.features.moveFeatures.add(mi)
    return body


def cyl(comp, name, cx, cy, cz, dia, length, axis='z'):
    """cylinder, centre of its base face at (cx,cy,cz), extruded along `axis`, mm"""
    if axis == 'z':
        plane = comp.xYConstructionPlane; c = (cx, cy); off = cz
    else:  # 'y' : built on XZ, extruded along -Y in Fusion, so we flip later
        plane = comp.xZConstructionPlane; c = (cx, cz); off = cy
    sk = comp.sketches.add(plane)
    sk.sketchCurves.sketchCircles.addByCenterRadius(
        adsk.core.Point3D.create(c[0] * MM, c[1] * MM, 0), dia / 2 * MM)
    prof = sk.profiles.item(0)
    inp = comp.features.extrudeFeatures.createInput(
        prof, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    inp.setDistanceExtent(False, adsk.core.ValueInput.createByReal(length * MM))
    ext = comp.features.extrudeFeatures.add(inp)
    b = ext.bodies.item(0); b.name = name
    if abs(off) > 1e-9:
        mv = adsk.core.ObjectCollection.create(); mv.add(b)
        t = adsk.core.Matrix3D.create()
        v = adsk.core.Vector3D.create(0, 0, off * MM) if axis == 'z' \
            else adsk.core.Vector3D.create(0, -off * MM, 0)
        t.translation = v
        comp.features.moveFeatures.add(comp.features.moveFeatures.createInput(mv, t))
    return b


def new_comp(root, name):
    occ = root.occurrences.addNewComponent(adsk.core.Matrix3D.create())
    occ.component.name = name
    return occ


def run(context):
    ui = None
    try:
        app = adsk.core.Application.get()
        ui = app.userInterface
        doc = app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
        design = app.activeProduct
        design.designType = adsk.fusion.DesignTypes.ParametricDesignType
        root = design.rootComponent
        root.name = 'Fly Treadmill'

        # ---------------- FRAME ----------------
        fo = new_comp(root, 'Frame'); frame = fo.component
        box(frame, 'floor', -FRAME_L/2, -FRAME_W/2, 0, FRAME_L, FRAME_W, FLOOR_T)
        for s in (-1, 1):
            y = s * (GAP/2 + WALL) - (WALL if s > 0 else 0)
            box(frame, f'wall{s}', -FRAME_L/2, y, FLOOR_T, FRAME_L, WALL, 29 - FLOOR_T)

        # ---------------- SHAFTS ----------------
        so = new_comp(root, 'Shafts'); shafts = so.component
        for nm, x in (('shaft_drive', -SPAN/2), ('shaft_idler', SPAN/2)):
            cyl(shafts, nm, x, FRAME_W/2 + 6, AXIS_H, SHAFT_D, FRAME_W + 12, axis='y')

        # ---------------- PULLEYS (one component each, so each can rotate) -------
        pulleys = []
        for nm, x in (('Pulley_drive', -SPAN/2), ('Pulley_idler', SPAN/2)):
            po = new_comp(root, nm); pc = po.component
            cyl(pc, 'body',   x, BELT_W/2,            AXIS_H, PULLEY_OD, BELT_W,   axis='y')
            cyl(pc, 'flangeA', x, BELT_W/2 + FLANGE_T, AXIS_H, FLANGE_D, FLANGE_T, axis='y')
            cyl(pc, 'flangeB', x, -BELT_W/2,           AXIS_H, FLANGE_D, FLANGE_T, axis='y')
            pulleys.append(po)

        # ---------------- JOINTS: this is the part that makes it rotate ----------
        def first_cyl_face(occ):
            """the pulley bore / shaft outside, as a proxy in the assembly context"""
            for b in occ.bRepBodies:
                for f in b.faces:
                    if f.geometry.surfaceType == adsk.core.SurfaceTypes.CylinderSurfaceType:
                        return f
            return None

        made = 0
        shaft_face = first_cyl_face(so)
        for po in pulleys:
            try:
                pf = first_cyl_face(po)
                if pf is None or shaft_face is None:
                    continue
                g_pulley = adsk.fusion.JointGeometry.createByNonPlanarFace(
                    pf, adsk.fusion.JointKeyPointTypes.CenterKeyPoint)
                g_shaft = adsk.fusion.JointGeometry.createByNonPlanarFace(
                    shaft_face, adsk.fusion.JointKeyPointTypes.CenterKeyPoint)
                ji = root.joints.createInput(g_pulley, g_shaft)
                ji.setAsRevoluteJointMotion(
                    adsk.fusion.JointDirections.YAxisJointDirection)
                root.joints.add(ji)
                made += 1
            except Exception:
                pass

        app.activeViewport.fit()
        ui.messageBox(
            'Fly treadmill built.\n\n'
            f'Span {SPAN} mm, shaft axis {AXIS_H} mm, belt top 23.0 mm.\n'
            f'Revolute joints created: {made} of 2.\n\n'
            'If a joint is missing: Assemble > Joint, click the pulley bore, then the '
            'shaft, and pick Revolute. Then drag the pulley and it will spin.')

    except:
        if ui:
            ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))
