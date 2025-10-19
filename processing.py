import numpy as np
import laspy
import rasterio
from rasterio.transform import from_origin
from scipy.interpolate import griddata
import pdal
import json

def classify_ground(unclassified_las_path, classified_las_path):
    """
    Reads an unclassified LAS file, classifies ground points using a PDAL
    SMRF pipeline, and saves a new classified LAS file.
    """
    print("Building simplified PDAL pipeline for ground classification...")

    # --- CORRECTED PIPELINE (This part is the same) ---
    pipeline_json = {
        "pipeline": [
            unclassified_las_path,
            {
                "type": "filters.smrf"
            },
            {
                "type":"writers.las",
                "filename": classified_las_path
            }
        ]
    }

    print("Executing PDAL pipeline...")
    pipeline = pdal.Pipeline(json.dumps(pipeline_json))
    
    # --- CORRECTED LOGIC ---
    # The execute() method returns the number of points processed.
    # We capture this count to check if the pipeline was successful.
    count = pipeline.execute()
    
    if count > 0:
        print(f"PDAL classification complete. Processed {count} points. Classified file saved to: {classified_las_path}")
    else:
        raise RuntimeError("PDAL pipeline executed but produced no points. Check the input file and pipeline.")


def create_canopy_height_model(las_path, output_raster_path, resolution=1.0):
    """
    Creates a Canopy Height Model (CHM) from a (now classified) LAS/LAZ file.
    """
    print("Reading LAS file for CHM...")
    with laspy.open(las_path) as f:
        las = f.read()

    ground_points = las.points[las.classification == 2]
    non_ground_points = las.points[las.classification != 2]

    if len(ground_points) == 0:
        raise ValueError("No ground points found in the file. Cannot create DTM.")
    
    print(f"Found {len(ground_points)} ground points and {len(non_ground_points)} non-ground points.")

    min_x, min_y = np.min(las.x), np.min(las.y)
    max_x, max_y = np.max(las.x), np.max(las.y)
    grid_x_min = np.floor(min_x / resolution) * resolution
    grid_y_min = np.floor(min_y / resolution) * resolution
    x_coords = np.arange(grid_x_min, max_x, resolution)
    y_coords = np.arange(grid_y_min, max_y, resolution)
    cols = len(x_coords)
    rows = len(y_coords)
    
    print("Creating DTM...")
    ground_xyz = np.vstack((ground_points.x, ground_points.y, ground_points.z)).transpose()
    grid_x, grid_y = np.meshgrid(x_coords, y_coords)
    dtm = griddata(ground_xyz[:, :2], ground_xyz[:, 2], (grid_x, grid_y), method='linear')
    dtm = griddata(ground_xyz[:, :2], ground_xyz[:, 2], (grid_x, grid_y), method='nearest', fill_value=np.nan)
    dtm = np.flipud(dtm)

    print("Creating DSM...")
    dsm = np.full((rows, cols), -9999.0, dtype=np.float32)
    col_indices = np.floor((non_ground_points.x - grid_x_min) / resolution).astype(int)
    row_indices = np.floor((non_ground_points.y - grid_y_min) / resolution).astype(int)
    row_indices = (rows - 1) - row_indices
    unique_cells = np.unique(np.vstack([row_indices, col_indices]).T, axis=0)
    for r, c in unique_cells:
        if 0 <= r < rows and 0 <= c < cols:
            mask = (row_indices == r) & (col_indices == c)
            dsm[r, c] = np.max(non_ground_points.z[mask])
    dsm[dsm == -9999.0] = dtm[dsm == -9999.0]

    print("Calculating CHM...")
    chm = dsm - dtm
    chm[chm < 0] = 0
    chm[np.isnan(dtm)] = -9999.0

    print(f"Saving CHM to {output_raster_path}")
    transform = from_origin(grid_x_min, y_coords.max(), resolution, resolution)
    with rasterio.open(
        output_raster_path, 'w', driver='GTiff', height=rows, width=cols,
        count=1, dtype=rasterio.float32, crs=las.header.parse_crs(),
        transform=transform, nodata=-9999.0
    ) as dst:
        dst.write(chm.astype(rasterio.float32), 1)

def create_canopy_cover(las_path, output_raster_path, resolution=10.0, height_threshold=2.0):
    """
    Calculates canopy cover. This function also expects a classified file.
    """
    print("Reading LAS file for canopy cover...")
    with laspy.open(las_path) as f:
        las = f.read()

    ground_points = las.points[las.classification == 2]
    if len(ground_points) == 0:
        raise ValueError("No ground points found. Cannot normalize heights for cover calculation.")
        
    print("Normalizing point heights...")
    dtm_interpolator = griddata(
        (ground_points.x, ground_points.y), 
        ground_points.z, 
        (las.x, las.y), 
        method='nearest'
    )
    normalized_z = las.z - dtm_interpolator

    min_x, min_y = np.min(las.x), np.min(las.y)
    max_x, max_y = np.max(las.x), np.max(las.y)
    grid_x_min = np.floor(min_x / resolution) * resolution
    grid_y_min = np.floor(min_y / resolution) * resolution
    x_coords = np.arange(grid_x_min, max_x, resolution)
    y_coords = np.arange(grid_y_min, max_y, resolution)
    cols = len(x_coords)
    rows = len(y_coords)

    print("Tallying points for canopy cover...")
    total_returns = np.zeros((rows, cols), dtype=np.int32)
    above_threshold_returns = np.zeros((rows, cols), dtype=np.int32)
    col_indices = np.floor((las.x - grid_x_min) / resolution).astype(int)
    row_indices = np.floor((las.y - grid_y_min) / resolution).astype(int)
    row_indices = (rows - 1) - row_indices
    valid_indices = (row_indices >= 0) & (row_indices < rows) & (col_indices >= 0) & (col_indices < cols)
    np.add.at(total_returns, (row_indices[valid_indices], col_indices[valid_indices]), 1)
    above_mask = normalized_z > height_threshold
    valid_above_indices = valid_indices & above_mask
    np.add.at(above_threshold_returns, (row_indices[valid_above_indices], col_indices[valid_above_indices]), 1)
    
    print("Calculating cover percentage...")
    canopy_cover = np.full((rows, cols), -9999.0, dtype=np.float32)
    valid_cells = total_returns > 0
    canopy_cover[valid_cells] = (above_threshold_returns[valid_cells] / total_returns[valid_cells]) * 100

    print(f"Saving canopy cover to {output_raster_path}")
    transform = from_origin(grid_x_min, y_coords.max(), resolution, resolution)
    with rasterio.open(
        output_raster_path, 'w', driver='GTiff', height=rows, width=cols,
        count=1, dtype=rasterio.float32, crs=las.header.parse_crs(),
        transform=transform, nodata=-9999.0
    ) as dst:
        dst.write(canopy_cover.astype(rasterio.float32), 1)

