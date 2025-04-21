from pxr import UsdGeom, Sdf


def get_or_create_world_prim(stage):
    root_path = Sdf.Path.absoluteRootPath
    world_prim_path = root_path.AppendChild("World")
    world_prim = stage.GetPrimAtPath(world_prim_path)
    if not world_prim:
        # world prim as xform to be able to transform it
        world_prim = UsdGeom.Xform.Define(stage,world_prim_path)
        world_prim.GetPrim().SetMetadata("kind","group")
    return world_prim

def get_or_create_cameras_prim(stage):
    world_prim = get_or_create_world_prim(stage)
    cameras_prim_path = world_prim.GetPath().AppendChild("Cameras")
    cameras_prim = stage.GetPrimAtPath(cameras_prim_path)
    if not cameras_prim:
        cameras_prim = UsdGeom.Scope.Define(stage,cameras_prim_path)
        #cameras_prim.GetPrim().SetMetadata("kind","group")
    return cameras_prim
