import streamlit as st
import cv2
import math
import csv
import os
from streamlit_webrtc import webrtc_streamer, VideoProcessorBase, RTCConfiguration
import numpy as np
from PIL import Image
from streamlit_drawable_canvas import st_canvas

# Default fallback ratio (can be overwritten by calibration)
DEFAULT_RATIO = 15/273.03
CSV_FILENAME = "measurements.csv"

# Initialize CSV
if not os.path.exists(CSV_FILENAME):
    with open(CSV_FILENAME, mode="w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["Product Number", "Width (cm)", "Height (cm)", "Distances (cm)"])

# Global session state
for key in ["points", "measured_distances", "product_count", "captured_image", "ratio", "calibration_mode"]:
    if key not in st.session_state:
        st.session_state[key] = [] if key in ["points", "measured_distances"] else 0 if key == "product_count" else None if key in ["captured_image", "ratio"] else False

st.title("📏 Object Measurement System with Dynamic Calibration")

st.info("Steps:\n"
        "- Click 'Capture Frame'\n"
        "- Select 2 points to calibrate (e.g., across a 15 cm object)\n"
        "- Enter real-world distance and press 'Calibrate'\n"
        "- Select more points for measurement\n"
        "- Click 'Measure & Save'\n"
        "- Click 'Start New Product' to reset")

# Button to start new product
if st.button("Start New Product"):
    st.session_state.points.clear()
    st.session_state.measured_distances.clear()
    st.session_state.product_count += 1
    st.session_state.captured_image = None

# Toggle Calibration Mode
st.session_state.calibration_mode = st.checkbox("🛠️ Enable Calibration Mode", value=st.session_state.calibration_mode)

# WebRTC stream
class VideoProcessor(VideoProcessorBase):
    def __init__(self):
        self.frame = None

    def recv(self, frame):
        img = frame.to_ndarray(format="bgr24")
        self.frame = img.copy()
        return frame.from_ndarray(img, format="bgr24")

ctx = webrtc_streamer(
    key="example",
    video_processor_factory=VideoProcessor,
    rtc_configuration=RTCConfiguration({"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]}),
)

# Capture Frame
if st.button("Capture Frame"):
    if ctx.video_processor and ctx.video_processor.frame is not None:
        st.session_state.captured_image = ctx.video_processor.frame.copy()
        st.image(st.session_state.captured_image, caption="Captured Frame", channels="BGR", use_column_width=True)

# Select Points
if st.session_state.captured_image is not None:
    img = st.session_state.captured_image
    img_pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))

    canvas_result = st_canvas(
        fill_color="rgba(255, 0, 0, 0.3)",
        stroke_width=3,
        stroke_color="#000",
        background_image=img_pil,
        height=img.shape[0],
        width=img.shape[1],
        drawing_mode="point",
        key="canvas",
    )

    if canvas_result.json_data:
        st.session_state.points = [
            (int(obj["left"]), int(obj["top"])) for obj in canvas_result.json_data["objects"]
        ]
        st.write("Selected Points:", st.session_state.points)

    # Calibration Mode
    if st.session_state.calibration_mode:
        if len(st.session_state.points) == 2:
            known_cm = st.number_input("Enter real-world distance (cm) between the two points:", min_value=0.1, value=15.0)
            pt1, pt2 = st.session_state.points
            pixel_dist = math.hypot(pt2[0] - pt1[0], pt2[1] - pt1[1])
            if pixel_dist > 0:
                st.session_state.ratio = known_cm / pixel_dist
                st.success(f"✅ Calibration successful: {st.session_state.ratio:.4f} cm/pixel")
            else:
                st.error("❌ Selected points are too close.")
        elif len(st.session_state.points) > 2:
            st.warning("Please select only 2 points for calibration.")
    else:
        # Use measured ratio (or fallback) and draw lines
        ratio = st.session_state.ratio or DEFAULT_RATIO
        img_copy = img.copy()
        distances = []

        for i in range(len(st.session_state.points) - 1):
            pt1 = st.session_state.points[i]
            pt2 = st.session_state.points[i + 1]
            cv2.line(img_copy, pt1, pt2, (0, 0, 255), 2)

            dist_px = math.hypot(pt2[0] - pt1[0], pt2[1] - pt1[1])
            dist_cm = dist_px * ratio
            distances.append(dist_cm)

            mid = ((pt1[0] + pt2[0]) // 2, (pt1[1] + pt2[1]) // 2)
            cv2.putText(img_copy, f"{dist_cm:.2f} cm", mid, cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

        st.image(img_copy, caption="Measured Image", channels="BGR", use_column_width=True)

        # Display distance table
        if distances:
            st.session_state.measured_distances = distances
            st.table({
                "Point Pair": [f"Point {i+1} & {i+2}" for i in range(len(distances))],
                "Distance (cm)": [f"{d:.2f}" for d in distances]
            })

# Save Measurements
if st.button("Measure & Save"):
    if len(st.session_state.points) > 1 and st.session_state.ratio:
        x_vals = [pt[0] for pt in st.session_state.points]
        y_vals = [pt[1] for pt in st.session_state.points]

        width_px = max(x_vals) - min(x_vals)
        height_px = max(y_vals) - min(y_vals)
        width_cm = width_px * st.session_state.ratio
        height_cm = height_px * st.session_state.ratio

        with open(CSV_FILENAME, mode="a", newline="") as file:
            writer = csv.writer(file)
            writer.writerow([
                st.session_state.product_count + 1,
                f"{width_cm:.2f}",
                f"{height_cm:.2f}",
                ", ".join([f"{d:.2f}" for d in st.session_state.measured_distances])
            ])

        st.success(f"✅ Measurements saved for Product {st.session_state.product_count + 1}")
        st.session_state.points.clear()
        st.session_state.captured_image = None
        st.session_state.measured_distances.clear()
    else:
        st.warning("⚠️ Make sure you have measured and calibrated properly before saving.")
