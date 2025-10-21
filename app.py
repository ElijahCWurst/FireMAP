import streamlit as st
import os
import tempfile
import uuid
from processing import create_canopy_height_model, create_canopy_cover, classify_ground
import tkinter as tk
from tkinter import filedialog
from PIL import Image #

# --- Helper Function to open the file dialog ---
def open_file_dialog():
    """
    Opens a file dialog and returns the selected path.
    This function is designed to be more robust when used with Streamlit.
    """
    root = tk.Tk()
    root.withdraw()  # Hide the main tkinter window
    # Make the dialog appear on top of all other windows
    root.attributes('-topmost', True) 
    file_path = filedialog.askopenfilename(
        title="Select a LiDAR file",
        filetypes=(("LiDAR files", "*.las *.laz"), ("All files", "*.*"))
    )
    root.destroy()
    return file_path

# --- Callback function for the browse button ---
def update_path_from_dialog():
    """Callback to update session state after a file is selected."""
    selected_path = open_file_dialog()
    if selected_path:
        st.session_state.las_file_path = selected_path

try:
    # Open the original image
    original_icon = Image.open("icon.webp")
    
    # Get original dimensions
    width, height = original_icon.size
    
    # Determine the size for the new square background (the larger dimension)
    max_dim = max(width, height)
    
    # Create a new square image with a transparent background (RGBA)
    square_icon = Image.new("RGBA", (max_dim, max_dim), (0, 0, 0, 0))
    
    # Calculate the position to paste the original icon in the center
    paste_x = (max_dim - width) // 2
    paste_y = (max_dim - height) // 2
    
    # Paste the original icon onto the new square background
    square_icon.paste(original_icon, (paste_x, paste_y))
    
    # Use the newly created square icon
    icon = square_icon

except FileNotFoundError:
    icon = "🌳"

# --- Page Configuration ---
st.set_page_config(
    page_title="Point Cloud Processor",
    page_icon=icon,
    layout="centered" 
)

# --- Main UI ---
st.title("Point Cloud Processor")
st.write("Provide the full path to your `.las` or `.laz` file, or use the browse button.")

# Initialize session state to hold the file path
if 'las_file_path' not in st.session_state:
    st.session_state['las_file_path'] = ""

# --- File Selection UI ---
col1, col2 = st.columns([4, 1])

with col1:
    # This text input is now the single source of truth, bound to the session state key.
    # If the user types here, the state updates automatically.
    # If a callback updates the state, this box will reflect it on the next run.
    st.text_input(
        "Enter the full path to your data file:",
        key="las_file_path"
    )

with col2:
    # This CSS pushes the button down to vertically align with the text input box
    st.markdown(
        """
        <style>
        div[data-testid="stVerticalBlock"] div[data-testid="stButton"] > button {
            margin-top: 12px;
        }
        </style>
        """,
        unsafe_allow_html=True
    )
    # The button now uses an on_click callback. This function runs BEFORE the
    # rest of the page is rerendered, safely updating the session state.
    st.button("Browse...", on_click=update_path_from_dialog)


# Use the path from our single source of truth for the rest of the app
las_file_path = st.session_state['las_file_path']

if las_file_path and os.path.exists(las_file_path):
    # Display a more informative success message with the file name
    st.success(f"✅ File found: **{os.path.basename(las_file_path)}**")
    
    # # --- Classification Checkbox ---
    # st.header("1. Classification")
    # is_classified = st.checkbox(
    #     "My data is already classified (contains ground points)",
    #     value=False,
    #     help="Check this box if your file already has points classified as ground (Code 2). Otherwise, the app will classify it for you."
    # )

    # --- Analysis Options ---
    st.header("Analysis Options")
    # is_classified = st.checkbox(
    #     "My data is already classified (contains ground points)",
    #     value=False,
    #     help="Check this box if your file already has points classified as ground (Code 2). Otherwise, the app will classify it for you."
    # )

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
    if st.button(f"Run {analysis_type}", type="primary"):
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                path_to_process = las_file_path
                
                if not is_classified:
                    with st.spinner("Classifying ground points... (This can be slow for large files)"):
                        classified_temp_path = os.path.join(temp_dir, "classified_temp.laz")
                        classify_ground(las_file_path, classified_temp_path)
                        path_to_process = classified_temp_path
                        st.success("Ground classification complete.")

                output_filename = f"{os.path.splitext(os.path.basename(las_file_path))[0]}_{analysis_type.replace(' ', '_').lower()}.tif"
                output_path = os.path.join(temp_dir, output_filename)

                with st.spinner(f"Generating {analysis_type}..."):
                    if analysis_type == "Canopy Height Model":
                        create_canopy_height_model(path_to_process, output_path, resolution=resolution_chm)
                    elif analysis_type == "Canopy Cover":
                        create_canopy_cover(path_to_process, output_path, resolution=resolution_cc, height_threshold=height_threshold)

                st.success(f"✅ Analysis Complete!")
                
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
            st.exception(e)

elif las_file_path:
    st.error("❌ File not found. Please check the path is correct.")
else:
    st.info("Please enter a file path to get started.")

