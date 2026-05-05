# Live Object Tracker for 3D Printer Bed
# This code pulls the Sovol ACE live video stream from it's LAN webcam, compares each frame
# against a saved "blank bed" reference image, and isolates any new object sitting on
# the printer bed. The detected object's position, bounding box, and a transparent PNG
# crop of it are then streamed over UDP to a Unity application for visualization.
# The image is projected onto a blank object on the Unity digital twin print bed to simulate the object. 
# Part of my research project for ME597 new material.
# Updated 5/3/2026
# Trevor Kates

import cv2
import numpy as np
import socket
import os
import time
import threading

# --- 1. NETWORKING SETUP ---
# UDP socket pointed at localhost. Unity listens on port 5005 and reconstructs the
# sprite from each packet.
UDP_IP   = "127.0.0.1"
UDP_PORT = 5005
sock     = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# --- 2. CALIBRATION DATA ---
# Pentagon outlining the printer bed in camera-space (640x480). Anything outside
# this polygon is masked out so the tracker ignores the printer frame, gantry,
# desk, etc. These points were hand-picked from a reference frame.
current_pts = np.array([[234, 208], [463, 212], [498, 455], [359, 455], [166, 438]], np.int32)

# Default starting parameters (overridden by sliders at runtime).
# These are the values the trackbars boot up with — tuning happens live.
DEFAULT_THRESH     = 6      # Binary threshold cutoff after diff+edge combine
DEFAULT_SAT_WEIGHT = 0.19   # How much HSV saturation diff matters vs value diff
DEFAULT_CANNY_MIN  = 123    # Lower hysteresis bound for Canny edge detector
DEFAULT_DILATION   = 2      # How aggressively to thicken detected edges
DEFAULT_MIN_AREA   = 5     # x100 = 100 px² — reject anything smaller (noise)
DEFAULT_MAX_AREA   = 500    # x100 = 50,000 px² — reject anything bigger (lighting changes)

# --- 3. TRACKING PARAMETERS ---
STREAM_URL      = "http://192.168.1.8/webcam/?action=stream"  # Live webcam link for printer API
SMOOTHING       = 0.15      # Exponential smoothing alpha. Lower = more sluggish but stable.
MAX_SPRITE_SIZE = 96        # Starting max dimension for the PNG sent to Unity.
                            # Shrinks dynamically below if encoded packet exceeds Mac's UDP limit.

class StreamGrabber:
    """Reads video stream on a daemon thread, only keeps latest frame."""
    def __init__(self, url):
        self.url     = url
        self.cap     = cv2.VideoCapture(url)
        self.frame   = None                # Latest frame (overwritten each read)
        self.running = True
        self.lock    = threading.Lock()    # Guards self.frame against torn reads
        # daemon = True means the thread dies automatically when the program exits
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self):
        # pull frames as fast as the camera will give them.
        # On any failure, tear down and reopen the stream so a transient
        # network blip doesn't kill the tracker.
        while self.running:
            if not self.cap.isOpened():
                time.sleep(0.5)
                self.cap = cv2.VideoCapture(self.url)
                continue
            ok, f = self.cap.read()
            if not ok:
                # Stream hiccup — recycle the connection
                self.cap.release()
                self.cap = cv2.VideoCapture(self.url)
                time.sleep(0.2)
                continue
            with self.lock:
                self.frame = f             # Overwrite - don't queue old frames

    def read(self):
        # Hand back a copy so the main loop can mutate freely without
        # racing against the next overwrite from the reader thread.
        with self.lock:
            return None if self.frame is None else self.frame.copy()

    def release(self):
        self.running = False
        try: self.cap.release()
        except Exception: pass

def nothing(x):
    # Required no-op callback for cv2.createTrackbar — we read values
    # by polling, not via callbacks, so this just satisfies the API.
    pass

def run_live_tracker():
    # --- LOCATE THE REFERENCE IMAGE ---
    # The "blank bed" photo is a snapshot of the printer bed with NOTHING on it.
    # Every live frame is compared against this image to find what's new.
    desktop  = os.path.expanduser("~/Desktop")
    real_dir = os.path.join(desktop, "PrinterResearch", "RealPhotos")
    blank_bed_path = os.path.join(real_dir, "blank_bed.png")

    img_b_raw = cv2.imread(blank_bed_path)
    if img_b_raw is None:
        print(f"Error: blank_bed.png missing from {real_dir}.")
        return

    # CLAHE = Contrast Limited Adaptive Histogram Equalization.
    # It boosts local contrast in small tiles across the image, which makes
    # subtle color/brightness differences much easier to detect. Crucially,
    # we apply it identically to BOTH the background and live frames so the
    # comparison stays fair.
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))

    # --- BACKGROUND PROCESSING ---
    # We wrap the background in a list (bg_hsv_ref) so the inner load_background()
    # closure can swap in a new background when the user presses 'B'. Python
    # closures can read outer variables but not rebind them; mutating a list
    # element sidesteps that limitation cleanly.
    bg_hsv_ref = [None]
    def load_background(raw):
        # Resize to standard 640x480, run CLAHE on the L (lightness) channel of
        # LAB color space, then convert back to BGR and finally to HSV. We compare
        # in HSV because saturation+value diffs are more robust to lighting shifts
        # than raw RGB diffs.
        img = cv2.resize(raw, (640, 480))
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        lab[:, :, 0] = clahe.apply(lab[:, :, 0])
        boosted = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
        bg_hsv_ref[0] = cv2.cvtColor(boosted, cv2.COLOR_BGR2HSV)
        print("[BG] Background loaded.")
    load_background(img_b_raw)

    # --- BUILD THE BED MASK ---
    # static_mask is a black 640x480 image with the pentagon filled in white.
    # Every detection step is bitwise-AND'd with this mask, so anything outside
    # the printer bed gets zeroed out and ignored.
    static_mask = np.zeros((480, 640), dtype=np.uint8)
    cv2.fillPoly(static_mask, [current_pts], 255)
    # Also cache the pentagon's axis-aligned bounding box — used later to clamp
    # any detected bounding rectangle so it can't extend past the bed.
    bed_x, bed_y, bed_w, bed_h = cv2.boundingRect(current_pts)

    # --- START THE THREADED WEBCAM GRABBER ---
    grabber = StreamGrabber(STREAM_URL)

    # --- SETUP DISPLAY WINDOWS AND TUNING SLIDERS ---
    # Two windows: one shows the annotated live feed, the other holds all the
    # tuning sliders. Splitting them keeps the video display clean.
    cv2.namedWindow("Live Tracking")
    cv2.namedWindow("Controls", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Controls", 460, 480)

    # Each slider returns an int 0..max_value. SAT_WEIGHT and area sliders are
    # scaled later (divide by 100, multiply by 100) to get useful ranges.
    cv2.createTrackbar("Thresh",        "Controls", DEFAULT_THRESH,                 255,  nothing)
    cv2.createTrackbar("Sat Weight",    "Controls", int(DEFAULT_SAT_WEIGHT * 100),  100,  nothing)
    cv2.createTrackbar("Canny Min",     "Controls", DEFAULT_CANNY_MIN,              255,  nothing)
    cv2.createTrackbar("Dilation",      "Controls", DEFAULT_DILATION,                10,  nothing)
    cv2.createTrackbar("Min Area x100", "Controls", DEFAULT_MIN_AREA,               500,  nothing)
    cv2.createTrackbar("Max Area x100", "Controls", DEFAULT_MAX_AREA,              2000,  nothing)

    print("\n--- LIVE TRACKER ACTIVE ---")
    print(f"Smoothing enabled (Alpha = {SMOOTHING}).")
    print("Use the sliders on the Controls window to tune detection.")
    print("Press 'B' to capture and update the blank bed reference.")
    print("Press 'Q' to quit.")

    # last_bbox holds the previous frame's smoothed bounding box. Used by the
    # exponential smoothing filter so the green rectangle doesn't jitter.
    last_bbox = None

    # --- WAIT FOR FIRST FRAME ---
    # The reader thread needs a moment to actually pull the first frame from the
    # network. Poll for up to ~2.5 seconds before giving up and entering the
    # main loop (which can also handle a None frame gracefully).
    for _ in range(50):
        if grabber.read() is not None: break
        time.sleep(0.05)

    # =====================================================================
    # MAIN LOOP — runs once per frame
    # =====================================================================
    while True:
        frame_raw = grabber.read()
        if frame_raw is None:
            # No frame yet (camera reconnecting, etc.) — wait briefly and retry.
            time.sleep(0.05)
            continue

        # --- READ CURRENT SLIDER VALUES ---
        # Wrapped in try/except because trackbars can briefly be unavailable
        # during window setup or destruction; we fall back to defaults instead
        # of crashing.
        try:
            THRESH     = cv2.getTrackbarPos("Thresh",        "Controls")
            SAT_WEIGHT = cv2.getTrackbarPos("Sat Weight",    "Controls") / 100.0
            CANNY_MIN  = cv2.getTrackbarPos("Canny Min",     "Controls")
            DILATION   = cv2.getTrackbarPos("Dilation",      "Controls")
            MIN_AREA   = cv2.getTrackbarPos("Min Area x100", "Controls") * 100
            MAX_AREA   = cv2.getTrackbarPos("Max Area x100", "Controls") * 100
        except cv2.error:
            THRESH, SAT_WEIGHT     = DEFAULT_THRESH, DEFAULT_SAT_WEIGHT
            CANNY_MIN, DILATION    = DEFAULT_CANNY_MIN, DEFAULT_DILATION
            MIN_AREA, MAX_AREA     = DEFAULT_MIN_AREA * 100, DEFAULT_MAX_AREA * 100

        # Normalize incoming frame to the same 640x480 size as the background.
        img_f = cv2.resize(frame_raw, (640, 480))

        # --- PREPROCESSING (CLAHE-boost for detection only) ---
        # Same CLAHE+LAB pipeline as the background. The "boosted" image is used
        # purely for detection math — the original img_f stays untouched and is
        # what eventually gets cropped and sent to Unity (so Unity sees natural
        # colors, not a contrast-amplified version).
        lab_f = cv2.cvtColor(img_f, cv2.COLOR_BGR2LAB)
        lab_f[:, :, 0] = clahe.apply(lab_f[:, :, 0])
        img_f_boosted = cv2.cvtColor(lab_f, cv2.COLOR_LAB2BGR)

        gray_f = cv2.cvtColor(img_f_boosted, cv2.COLOR_BGR2GRAY)
        hsv_f  = cv2.cvtColor(img_f_boosted, cv2.COLOR_BGR2HSV)
        hsv_b  = bg_hsv_ref[0]   # Current reference background in HSV

        # --- DETECTION PIPELINE ---
        # Step 1: Compute per-channel absolute differences in HSV.
        #   diff_s = how much saturation changed (color intensity)
        #   diff_v = how much value changed (brightness)
        # We blend them with SAT_WEIGHT to control which channel dominates.
        # Glossy/colorful objects show up better in saturation; matte objects
        # show up better in value. The slider lets you tune that balance.
        diff_s = cv2.absdiff(hsv_b[:, :, 1], hsv_f[:, :, 1])
        diff_v = cv2.absdiff(hsv_b[:, :, 2], hsv_f[:, :, 2])
        diff   = cv2.addWeighted(diff_s, SAT_WEIGHT, diff_v, (1.0 - SAT_WEIGHT), 0)
        diff   = cv2.bitwise_and(diff, static_mask)   # Restrict to bed pentagon

        # Step 2: Find edges in the live frame with Canny. Edges fire on object
        # silhouettes regardless of color, which complements the diff above —
        # diff finds "things that look different from background", edges finds
        # "things that have visible boundaries". We combine both for robustness.
        edges = cv2.Canny(gray_f, CANNY_MIN, CANNY_MIN * 3)
        edges = cv2.bitwise_and(edges, static_mask)
        if DILATION > 0:
            # Thicken thin edges so they actually overlap with the diff regions
            # in the next step. Without this, edges can be 1px wide and miss.
            edges = cv2.dilate(edges, None, iterations=DILATION)

        # Step 3: AND the diff and edges together. A pixel survives only if
        # it's BOTH visually different from the background AND on an edge.
        # This kills lighting-only changes (which lack edges) and texture
        # noise (which lacks diff).
        combined = cv2.bitwise_and(diff, edges)

        # Step 4: Threshold to a binary mask, then morphological open
        # (erode + dilate) to remove tiny speckles of noise.
        _, thresh = cv2.threshold(combined, THRESH, 255, cv2.THRESH_BINARY)
        kernel    = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        thresh    = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)
        # Hard-clip after morphology so dilation/close can't bleed outside the pentagon
        thresh    = cv2.bitwise_and(thresh, static_mask)

        # Step 5: Find contours (connected blobs) in the binary mask.
        # RETR_EXTERNAL = only outermost contours, ignore holes inside them.
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # debug_img is what the user actually sees on screen — start from the
        # natural live frame and draw the pentagon outline on top.
        debug_img = img_f.copy()
        cv2.polylines(debug_img, [current_pts], True, (0, 255, 255), 1)

        if contours:
            # Pick the single biggest blob — assumes one main object on the bed.
            cnt  = max(contours, key=cv2.contourArea)
            area = cv2.contourArea(cnt)

            # Area gate: reject blobs that are too small (noise) or too large
            # (likely a global lighting shift, shadow, or camera glitch).
            if MIN_AREA < area < MAX_AREA:
                rx, ry, rw, rh = cv2.boundingRect(cnt)
                # Hard-clamp bounding rect to pentagon's bbox so the green box
                # never extends past the bed even if a contour edge spilled out.
                rx2, ry2 = min(rx + rw, bed_x + bed_w), min(ry + rh, bed_y + bed_h)
                rx, ry   = max(rx, bed_x), max(ry, bed_y)
                rw, rh   = rx2 - rx, ry2 - ry

                if rw > 0 and rh > 0:
                    # --- TEMPORAL SMOOTHING ---
                    # Exponential moving average between the new raw box and the
                    # previous smoothed box. SMOOTHING=0.15 means each new frame
                    # only nudges the box 15% toward the new measurement, which
                    # eliminates jitter at the cost of slight lag.
                    if last_bbox is not None:
                        x = int((SMOOTHING * rx) + ((1.0 - SMOOTHING) * last_bbox[0]))
                        y = int((SMOOTHING * ry) + ((1.0 - SMOOTHING) * last_bbox[1]))
                        w = int((SMOOTHING * rw) + ((1.0 - SMOOTHING) * last_bbox[2]))
                        h = int((SMOOTHING * rh) + ((1.0 - SMOOTHING) * last_bbox[3]))
                    else:
                        # First valid detection — no previous box to smooth against.
                        x, y, w, h = rx, ry, rw, rh

                    last_bbox = (x, y, w, h)
                    cX, cY    = x + (w // 2), y + (h // 2)   # Centroid

                    # --- DRAW OVERLAY (on debug_img only — NOT on the crop) ---
                    # Green rectangle = smoothed bounding box
                    # Red dot        = centroid
                    # Text label     = current size in pixels
                    cv2.rectangle(debug_img, (x, y), (x + w, y + h), (0, 255, 0), 2)
                    cv2.circle(debug_img, (cX, cY), 5, (0, 0, 255), -1)
                    cv2.putText(debug_img, f"OBJECT: {w}x{h}", (x, max(y - 10, 14)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

                    # --- BUILD THE PACKET FOR UNITY ---
                    # Crop the natural frame (img_f, NOT debug_img) to the bbox,
                    # and grab the matching slice of the binary thresh mask to
                    # use as the alpha channel. Result: a transparent PNG of
                    # just the object, no background, no overlay annotations.
                    crop_y1, crop_y2 = max(0, y), min(480, y + h)
                    crop_x1, crop_x2 = max(0, x), min(640, x + w)
                    crop  = img_f [crop_y1:crop_y2, crop_x1:crop_x2]
                    alpha = thresh[crop_y1:crop_y2, crop_x1:crop_x2]

                    if crop.size > 0 and alpha.size > 0:
                        # Merge BGR channels with the alpha mask -> 4-channel BGRA.
                        bgra            = cv2.merge((*cv2.split(crop), alpha))
                        crop_h, crop_w  = bgra.shape[:2]
                        current_target  = MAX_SPRITE_SIZE
                        # Header is plain text: "centerX,centerY,width,height|"
                        # followed by the raw PNG bytes. Unity parses on '|'.
                        header          = f"{cX},{cY},{w},{h}|".encode()

                        # --- DYNAMIC PACKET-SIZE LIMITER ---
                        # macOS caps default UDP datagrams at ~9216 bytes. Larger
                        # packets get silently dropped. We try to encode the sprite
                        # at the current target size; if the resulting packet is
                        # too big, shrink the sprite by 15% and retry. This keeps
                        # quality as high as possible while guaranteeing delivery.
                        while current_target > 10:
                            scale_factor = min(1.0, current_target / max(crop_w, crop_h))
                            new_w = max(1, int(crop_w * scale_factor))
                            new_h = max(1, int(crop_h * scale_factor))

                            # CUBIC interpolation gives smooth up/down scaling.
                            optimized = cv2.resize(bgra, (new_w, new_h),
                                                   interpolation=cv2.INTER_CUBIC)
                            # Compression level 9 = max compression, smallest output.
                            success, enc = cv2.imencode('.png', optimized,
                                                        [cv2.IMWRITE_PNG_COMPRESSION, 9])

                            if success:
                                packet = header + enc.tobytes()
                                if len(packet) < 8500:
                                    # Fits — fire it off and stop shrinking.
                                    sock.sendto(packet, (UDP_IP, UDP_PORT))
                                    break
                                else:
                                    # Too big — shrink target dimension by 15% and retry.
                                    current_target = int(current_target * 0.85)
                            else:
                                # Encode failed entirely — bail out of the loop.
                                break
            else:
                # Contour exists but area is out of bounds. Draw it in red with
                # the rejection reason so the user can see WHY their tuning
                # isn't catching the object — invaluable for slider calibration.
                rx, ry, rw, rh = cv2.boundingRect(cnt)
                reason = "too small" if area <= MIN_AREA else "too large"
                cv2.rectangle(debug_img, (rx, ry), (rx + rw, ry + rh), (0, 0, 255), 1)
                cv2.putText(debug_img, f"rejected ({reason}) area:{int(area)}",
                            (rx, max(ry - 6, 14)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 0, 255), 1)
                # Reset smoothing since we're not tracking a valid object.
                last_bbox = None
        else:
            # No contours at all this frame — clear smoothing history so the
            # next valid detection starts fresh instead of lerping from a stale box.
            last_bbox = None

        # Render the annotated frame to the screen.
        cv2.imshow("Live Tracking", debug_img)

        # --- KEYBINDS ---
        # waitKey(1) is mandatory — it's what actually pumps the OpenCV GUI
        # event loop and lets the windows redraw.
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            # Clean exit.
            break
        elif key == ord('b'):
            # Re-capture the blank bed reference. Use this when the lighting
            # changes, the camera shifts, or you've cleared the bed and want
            # to recalibrate. Saves over the existing PNG and reloads the
            # in-memory background arrays immediately.
            os.makedirs(real_dir, exist_ok=True)
            cv2.imwrite(blank_bed_path, frame_raw)
            print(f"\n> SAVED: New blank_bed.png captured to {blank_bed_path}")
            load_background(frame_raw)
            print("> UPDATE: Background vision array re-initialized.")

    # --- CLEANUP ---
    grabber.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    run_live_tracker()