import streamlit as st
import os
import tempfile
import uuid
from processing import create_canopy_height_model, create_canopy_cover, classify_ground

# --- Page Configuration ---
st.set_page_config(
    page_title="LiDAR Raster Processor",
    page_icon="🌳",
    layout="centered"
)

# --- Main UI ---
st.title("NNU LiDAR Raster Processor")
st.write("Provide the full path to your `.las` or `.laz` file to begin.")

las_file_path = st.text_input(
    "Enter the full path to your LiDAR file:",
    placeholder=r"C:\Users\YourName\Desktop\data\forest_scan.laz"
)

if las_file_path and os.path.exists(las_file_path):
    st.success("✅ File found!")
    
    # --- Classification Checkbox ---
    st.header("1. Classification")
    is_classified = st.checkbox(
        "My data is already classified (contains ground points)",
        value=False,
        help="Check this box if your file already has points classified as ground (Code 2). Otherwise, the app will classify it for you."
    )

    # --- Analysis Options ---
    st.header("2. Analysis Options")
    analysis_type = st.selectbox(
        "Select Analysis Type",
        ("Canopy Height Model", "Canopy Cover")
    )

    # --- Parameters ---
    if analysis_type == "Canopy Height Model":
        resolution_chm = st.number_input(
            "CHM Resolution (meters)", min_value=0.5, max_value=30.0, value=1.0, step=0.5
        )
    
    if analysis_type == "Canopy Cover":
        resolution_cc = st.number_input(
            "Canopy Cover Resolution (meters)", min_value=1.0, max_value=30.0, value=10.0, step=1.0
        )
        height_threshold = st.number_input(
            "Height Threshold (meters)", min_value=0.5, max_value=10.0, value=2.0, step=0.5
        )

    # --- Run Button ---
    if st.button(f"🚀 Run {analysis_type}", type="primary"):
        try:
            # Create a single temporary directory that will exist for the whole process
            with tempfile.TemporaryDirectory() as temp_dir:
                
                # Default to using the original file path
                path_to_process = las_file_path
                
                # --- CORRECTED LOGIC ---
                # If the user says their data is NOT classified, we run this block
                if not is_classified:
                    with st.spinner("Classifying ground points... (This can be slow for large files)"):
                        # Define a path for the new classified file inside the temp directory
                        classified_temp_path = os.path.join(temp_dir, "classified_temp.laz")
                        
                        # Run the classification
                        classify_ground(las_file_path, classified_temp_path)
                        
                        # Tell the rest of the script to use this NEW file
                        path_to_process = classified_temp_path
                        st.success("Ground classification complete.")

                # --- The rest of the process is NOW INSIDE the `with` block ---
                # It will correctly use `path_to_process` which is either the original
                # file or the new temporary classified file.
                
                output_filename = f"{os.path.splitext(os.path.basename(las_file_path))[0]}_{analysis_type.replace(' ', '_').lower()}.tif"
                output_path = os.path.join(temp_dir, output_filename)

                with st.spinner(f"Generating {analysis_type}..."):
                    if analysis_type == "Canopy Height Model":
                        create_canopy_height_model(path_to_process, output_path, resolution=resolution_chm)
                    elif analysis_type == "Canopy Cover":
                        create_canopy_cover(path_to_process, output_path, resolution=resolution_cc, height_threshold=height_threshold)

                st.success(f"✅ Analysis Complete!")
                
                # Read the final raster for the download button
                with open(output_path, "rb") as f:
                    file_bytes = f.read()

                st.download_button(
                    label="⬇️ Download Raster (.tif)",
                    data=file_bytes,
                    file_name=output_filename,
                    mime="image/tiff"
                )

        except Exception as e:
            st.error(f"An error occurred during processing: {e}")
            st.exception(e) # This gives the detailed traceback for debugging

elif las_file_path:
    st.error("❌ File not found. Please check the path is correct.")
else:
    st.info("Please enter a file path to get started.")

