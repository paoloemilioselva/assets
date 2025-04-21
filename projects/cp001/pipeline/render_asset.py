#!/bin/env python

import os
import sys
import subprocess
import math
import tempfile

import pipe_globals

from pxr import Usd, UsdGeom, Sdf, Gf, UsdRender


def stage_begin(filename, start=1.0, end=1.0):
    layer = Sdf.Layer.CreateNew( filename, args={'format':'usda'} )
    stage = Usd.Stage.Open( layer )
    stage.SetStartTimeCode(start)
    stage.SetEndTimeCode(end)
    stage.SetMetadata("metersPerUnit", 1.0 )
    stage.SetMetadata("upAxis", "Y")
    return stage


def stage_end(i_stage):
    i_stage.GetRootLayer().Save()


def get_default_camera_settings():
    return {
            "shutter:open":  { "type":Sdf.ValueTypeNames.Double,   "value":0.0 },
            "shutter:close": { "type":Sdf.ValueTypeNames.Double,   "value":0.0 }
        }


def create_default_camerarig( stage, camera_settings={}):
    # force-create default camera as root-xform with any camera-rig underneath
    # NOTE: Do we need a full rig ? Maybe not, could simplify this.
    cameras_prim = pipe_globals.get_or_create_cameras_prim(stage)
    camera_xform_name = "mainCamera"
    camera_name = "mono" # mono, left, right, center, etc.
    camera_xform_prim_path = cameras_prim.GetPath().AppendChild(camera_xform_name)
    camera_xform_prim = UsdGeom.Xform.Define(stage,camera_xform_prim_path)
    camera_prim_path = camera_xform_prim.GetPath().AppendChild(camera_name)
    camera_prim = UsdGeom.Camera.Define(stage,camera_prim_path)
    
    camera_prim.CreateFocalLengthAttr().Set(32.0)
    camera_prim.CreateClippingRangeAttr().Set((0.1,100000.0))
    if len(camera_settings) == 0:
        camera_settings = get_default_camera_settings()
    for s in camera_settings.keys():
        camera_prim.GetPrim().CreateAttribute( "%s" % s, camera_settings[s]["type"] ).Set( camera_settings[s]["value"] )

    return (camera_xform_prim, camera_prim)


def make_turntable( stage, camera_xform_prim, camera_prim, frame_begin=1.0, frame_end=120.0, bbox=None, bbox_dist_multiplier=2.0, elevation=10):
    if bbox is None:
        # scene bounds
        bbox = UsdGeom.BBoxCache(0.0,["render","proxy","default"],useExtentsHint=True).ComputeWorldBound( stage.GetPseudoRoot() )

    ccenter = bbox.ComputeCentroid()
    crange = bbox.ComputeAlignedRange()
    dim = crange.GetSize()
    plane_corner = Gf.Vec2d(dim[0], dim[1])/2
    plane_radius = math.sqrt( Gf.Dot(plane_corner, plane_corner) )
    half_fov = 16
    distance = plane_radius / math.tan( Gf.DegreesToRadians( half_fov ) )
    distance += dim[2] * bbox_dist_multiplier

    #camera_xform_prim.ClearXformOpOrder()
    translateOp = camera_xform_prim.AddTranslateOp( opSuffix="zoomedIn" )
    rotateYOp = camera_xform_prim.AddRotateYOp( opSuffix="zoomedIn" )
    rotateXOp = camera_xform_prim.AddRotateXOp( opSuffix="zoomedIn" )

    for frame in range(int(frame_begin), int(frame_end)):
        cf = frame - frame_begin
        cr = cf*360.0/(frame_end - frame_begin)
        y_pos = math.sin(Gf.DegreesToRadians( elevation ))*distance
        y_pos_cos = math.cos(Gf.DegreesToRadians( elevation ))
        x_pos = (math.sin(Gf.DegreesToRadians( cr ))*distance)*y_pos_cos
        z_pos = (math.cos(Gf.DegreesToRadians( cr ))*distance)*y_pos_cos
        translateOp.Set( ccenter + Gf.Vec3d(x_pos, y_pos, z_pos), frame )        
        rotateYOp.Set( cr, frame )
        rotateXOp.Set( -elevation, frame )

    return True


def add_product_to_rendersettings( product_prim, rendersettings_prim ):
    if rendersettings_prim is not None and product_prim is not None:
        rendersettings_prim.GetProductsRel().AddTarget( product_prim.GetPath() )


def add_var_to_product( var_prim, product_prim ):
    if product_prim is not None and var_prim is not None:
        product_prim.GetOrderedVarsRel().AddTarget( var_prim.GetPath() )


def create_renderproduct(
    stage,
    product_name='',
    product_filepath='',
    driver_parameters={},
    camera_prim=None,
    resolution=[1024,768],
    ndc=(0,0,1,1),
    par=1.0,
    ):

    prim = UsdRender.Product.Define( stage, "/Render/Products/{name}".format(name=product_name) )
    prim.GetAspectRatioConformPolicyAttr().Set( "expandAperture" )
    prim.GetProductNameAttr().Set( product_filepath )
    prim.GetResolutionAttr().Set( Gf.Vec2i( resolution ) )
    prim.GetDataWindowNDCAttr().Set( ndc )
    prim.GetPixelAspectRatioAttr().Set( par )
    prim.GetInstantaneousShutterAttr().Set(False)
    
    prim.GetCameraRel().SetTargets( [ camera_prim.GetPath() ] )

    driver_parameters = {
        "imageName":{ "type":Sdf.ValueTypeNames.String, "value":"beauty" },
        "partName":{ "type":Sdf.ValueTypeNames.String, "value":"rgba" },
        "driver:imagePath":{ "type":Sdf.ValueTypeNames.String, "value":product_filepath },
        "driver:aovNames":{ "type":Sdf.ValueTypeNames.String, "value":"rgba" },
        "driver:parameters:subimage":{ "type":Sdf.ValueTypeNames.String, "value":"rgba" },
    } 
    for a in driver_parameters.keys():
        prim.GetPrim().CreateAttribute( a, driver_parameters[a]["type"] ).Set( driver_parameters[a]["value"] )

    return prim

def create_rendervar(
    stage, 
    aov_name='',
    aov_source='',
    aov_format='',
    ):

    prim = UsdRender.Var.Define( stage, "/Render/Products/Vars/{name}".format(name=aov_name) )

    prim.GetSourceNameAttr().Set( aov_name )
    prim.GetPrim().CreateAttribute( "driver:parameters:aov:name", Sdf.ValueTypeNames.String ).Set( aov_name )
    prim.GetPrim().CreateAttribute( "driver:parameters:aov:source", Sdf.ValueTypeNames.String ).Set( aov_source )
    if aov_format != '':
        prim.GetPrim().CreateAttribute( "driver:parameters:aov:format", Sdf.ValueTypeNames.String ).Set( aov_format )

    return prim





def create_rendersettings( 
        stage, 
        prim_path='/Render/rendersettings', 
        resolution=[1024,768], 
        camera_prim=None, 
        ndc=(0,0,1,1), 
        par=1.0, 
        purposes=["default"], 
        render_settings={} ):
    prim = None
    render_scope_prim = UsdGeom.Scope.Define( stage, '/Render' )
    prim = UsdRender.Settings.Define( stage, prim_path )

    prim.GetAspectRatioConformPolicyAttr().Set( "expandAperture" )
    prim.GetResolutionAttr().Set( Gf.Vec2i( resolution ) )
    prim.GetDataWindowNDCAttr().Set( ndc )
    prim.GetPixelAspectRatioAttr().Set( par )
    prim.GetInstantaneousShutterAttr().Set( False )
    prim.GetIncludedPurposesAttr().Set( purposes )

    stage.SetMetadata("renderSettingsPrimPath", prim_path )

    prim.GetCameraRel().SetTargets( [ camera_prim.GetPath() ] )

    for k in render_settings.keys():
        attr = prim.GetPrim().CreateAttribute( k, render_settings[k]["type"] )
        attr.Set( render_settings[k]["value"] )

    return prim


def main(args):
    output_prefix = "./render"
    inputs = []
    frame = 1.0
    i = 1

    while(i < len(args)):
        curr_arg = args[i]
        
        if curr_arg in ["-i","--input"]:
            i+=1
            inputs.append(str(args[i]))
        
        elif curr_arg in ["-f","--frame"]:
            i+=1
            frame = float(args[i])

        elif curr_arg in ["-op","--outputprefix"]:
            i+=1
            output_prefix = str(args[i])

        i+=1

    if len(inputs) == 0:
        exit(1)

    (_, tmp_usda) = tempfile.mkstemp(suffix=".usda",text=True)
    print(tmp_usda)
    stage = stage_begin(tmp_usda, start=1.0, end=120.0)
    stage.GetRootLayer().subLayerPaths = inputs
    (camera_xform_prim, camera_prim) = create_default_camerarig(stage)
    make_turntable(stage, camera_xform_prim, camera_prim)
    
    rendervar_prim = create_rendervar(stage, aov_name="rgba", aov_source="rgba", aov_format="")
    output_filename = f"{output_prefix}_1001.jpg"
    renderproduct_prim = create_renderproduct(stage, product_name="rgba", camera_prim=camera_prim, product_filepath=output_filename)
    add_var_to_product(rendervar_prim, renderproduct_prim)

    rendersettings_prim = create_rendersettings(stage, camera_prim=camera_prim)
    add_product_to_rendersettings( renderproduct_prim, rendersettings_prim )
    
    stage_end(stage)

    usdrecord_args = [
        "usdrecord",
        "--renderSettingsPrimPath",
        str(rendersettings_prim.GetPath()),
        tmp_usda,
        output_filename,
    ]
    print(usdrecord_args)
    subprocess.run(usdrecord_args)

if __name__ == '__main__':
    main(sys.argv)