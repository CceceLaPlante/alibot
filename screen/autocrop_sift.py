import cv2
import numpy as np
import os
import matplotlib.pyplot as plt

DEBUG = False # Keep True for tuning

# --- Parameters to Tune ---
MIN_MATCH_COUNT = 10      # Minimum number of good SIFT matches required
LOWE_RATIO = 0.75         # Ratio threshold for Lowe's ratio test (0.7-0.8 typical)
TARGET_ASPECT_RATIO = 1.5 # The known Width/Height ratio of the full window
# --- End Parameters ---

def autocrop_sift_ratio(img, template_path):
    """
    Finds a template using SIFT features, calculates the full window size
    based on the template's detected width and a target aspect ratio,
    then crops the full window. Assumes template is at the top of the full window
    and has the same width.

    Args:
        img (np.ndarray): The input image (screenshot).
        template_path (str): Path to the template image (must have same width as full window,
                             and be from the top section).

    Returns:
        np.ndarray: The cropped image, or None if no good match found or calculation fails.
    """
    if img is None:
        print("Error: Input image is None.")
        return None
    if not os.path.exists(template_path):
        print(f"Error: Template image not found at {template_path}")
        return None

    # Load images in grayscale
    img_scene_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    template = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)

    if template is None:
        print(f"Error: Could not load template image from {template_path}")
        return None

    template_h, template_w = template.shape[:2]
    scene_h, scene_w = img_scene_gray.shape[:2]

    # Basic check if template is larger than scene
    if template_h > scene_h or template_w > scene_w:
        print("Warning: Template dimensions exceed scene dimensions.")
        # Consider returning None or trying to resize

    try:
        # 1. Initialize SIFT Detector
        sift = cv2.SIFT_create()

        # 2. Find Keypoints and Descriptors
        kp_template, des_template = sift.detectAndCompute(template, None)
        kp_scene, des_scene = sift.detectAndCompute(img_scene_gray, None)

        if des_template is None or des_scene is None or len(kp_template) == 0 or len(kp_scene) == 0:
            print("Error: Could not compute SIFT descriptors or no keypoints found.")
            return None
        print(f"Found {len(kp_template)} SIFT keypoints in template, {len(kp_scene)} in scene.")

        # 3. Match Descriptors using BFMatcher (or FLANN)
        # Using Brute-Force Matcher
        bf = cv2.BFMatcher()
        matches = bf.knnMatch(des_template, des_scene, k=2) # k=2 for ratio test

    except cv2.error as e:
        print(f"OpenCV error during SIFT detection/matching: {e}")
        print("Ensure 'opencv-contrib-python' is installed.")
        return None

    # 4. Filter Matches using Lowe's Ratio Test
    good_matches = []
    # Check if matches list is valid and contains pairs
    if matches and len(matches[0]) == 2:
        for m, n in matches:
            # Check if distances are valid before comparison
            if n.distance > 1e-6: # Avoid division by zero or near-zero
                 if m.distance < LOWE_RATIO * n.distance:
                    good_matches.append(m)
            # Handle cases where n.distance is very small (potential perfect match?)
            # You might decide to keep 'm' if n.distance is effectively zero.
            # elif m.distance < 1e-6: # If m is also ~zero, it's a good match
            #    good_matches.append(m)

    else:
        print("Warning: knnMatch did not return pairs as expected.")
        # Handle cases where matching might have failed or returned single matches

    print(f"Found {len(good_matches)} good matches after ratio test.")

    # 5. Estimate Homography (if enough good matches)
    if len(good_matches) >= MIN_MATCH_COUNT:
        src_pts = np.float32([ kp_template[m.queryIdx].pt for m in good_matches ]).reshape(-1,1,2)
        dst_pts = np.float32([ kp_scene[m.trainIdx].pt for m in good_matches ]).reshape(-1,1,2)

        # RANSAC helps filter out outlier matches when calculating the transformation
        M, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0) # 5.0 is RANSAC reprojection threshold

        if M is None:
            print("Error: Could not compute Homography matrix (matches might be collinear or insufficient).")
            # Debug drawing can help diagnose why homography failed
            # ...
            return None

        matchesMask = mask.ravel().tolist()
        print(f"{sum(matchesMask)} matches were considered inliers by RANSAC.")

        # Check if enough inliers support the model
        if sum(matchesMask) < MIN_MATCH_COUNT:
             print(f"Error: Not enough inlier matches ({sum(matchesMask)}) after RANSAC to trust homography.")
             # Draw matches to see why so many were rejected
             if DEBUG:
                 img_matches_debug = cv2.drawMatches(template, kp_template, img, kp_scene, good_matches, None, matchColor=(255,0,0), singlePointColor=None, matchesMask=matchesMask, flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS)
                 plt.figure(figsize=(12, 6))
                 plt.imshow(cv2.cvtColor(img_matches_debug, cv2.COLOR_BGR2RGB))
                 plt.title(f'SIFT Matches ({len(good_matches)} good, {sum(matchesMask)} inliers) - RANSAC Failed Threshold')
                 plt.show()
             return None


        # 6. Get corners of the TEMPLATE in the scene using the homography
        h, w = template.shape # Original template dimensions
        pts_template_corners = np.float32([ [0,0],[0,h-1],[w-1,h-1],[w-1,0] ]).reshape(-1,1,2)
        dst_scene_corners = cv2.perspectiveTransform(pts_template_corners, M)

        # 7. Calculate the bounding box of the DETECTED TEMPLATE in the scene
        # This gives us the location and dimensions *as seen in the image*
        template_x, template_y, template_w_detected, template_h_detected = cv2.boundingRect(np.int32(dst_scene_corners))
        print(f"Detected template bounding box: x={template_x}, y={template_y}, w={template_w_detected}, h={template_h_detected}")

        # 8. Calculate FULL window dimensions based on DETECTED template width and aspect ratio
        if template_w_detected <= 5: # Check for a reasonably positive width
            print(f"Error: Detected template width ({template_w_detected}) is too small.")
            return None
        if TARGET_ASPECT_RATIO <= 0:
             print(f"Error: Invalid TARGET_ASPECT_RATIO ({TARGET_ASPECT_RATIO}).")
             return None

        # This is the core logic based on your constraints
        full_window_width = template_w_detected # Assumption: Template width = Full window width
        full_window_height = int(round(full_window_width / TARGET_ASPECT_RATIO))

        if full_window_height <= 0:
            print(f"Error: Calculated full window height ({full_window_height}) is invalid.")
            return None

        print(f"Calculated full window size: W={full_window_width}, H={full_window_height} (Ratio: {TARGET_ASPECT_RATIO})")

        # 9. Define final crop coordinates (assuming template is at the top)
        crop_x = template_x
        crop_y = template_y
        crop_w = full_window_width
        crop_h = full_window_height

        # 10. Boundary checks for the FULL CROP against the scene dimensions
        final_x1 = max(0, crop_x)
        final_y1 = max(0, crop_y)
        # Calculate bottom-right based on top-left and calculated dimensions
        final_x2 = final_x1 + crop_w
        final_y2 = final_y1 + crop_h
        # Clip bottom-right to scene boundaries
        final_x2 = min(scene_w, final_x2)
        final_y2 = min(scene_h, final_y2)
        # Recalculate final width/height after clipping
        final_w = final_x2 - final_x1
        final_h = final_y2 - final_y1

        print(f"Final crop region (clipped): x={final_x1}, y={final_y1}, w={final_w}, h={final_h}")

        # 11. Crop the original COLOR image
        if final_w > 0 and final_h > 0: # Ensure valid dimensions before cropping
            cropped_img = img[final_y1:final_y2, final_x1:final_x2]
        else:
            print("Warning: Final calculated crop dimensions are invalid (w<=0 or h<=0) after clipping.")
            cropped_img = None

        if DEBUG:
            img_debug = img.copy()
            # Draw polygon around the detected TEMPLATE location
            cv2.polylines(img_debug, [np.int32(dst_scene_corners)], True, (0, 255, 0), 2, cv2.LINE_AA) # Green for template detection outline
            # Draw rectangle for the calculated FULL CROP region
            cv2.rectangle(img_debug, (final_x1, final_y1), (final_x2, final_y2), (0, 0, 255), 3) # Red for final crop area

            plt.figure(figsize=(10,8))
            plt.imshow(cv2.cvtColor(img_debug, cv2.COLOR_BGR2RGB))
            plt.title(f'Green=Detected Template, Red=Calculated Full Crop ({sum(matchesMask)} inliers)')
            plt.show()

        return cropped_img

    else:
        print(f"Not enough good matches found - {len(good_matches)}/{MIN_MATCH_COUNT}")
        if DEBUG and len(good_matches) > 0: # Show poor matches if debug is on
             # Only draw the good matches, even if below threshold
             img_matches_debug = cv2.drawMatches(template, kp_template, img, kp_scene, good_matches, None, flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS)
             plt.figure(figsize=(12, 6))
             plt.imshow(cv2.cvtColor(img_matches_debug, cv2.COLOR_BGR2RGB))
             plt.title(f'SIFT Matches ({len(good_matches)} good) - Below Threshold ({MIN_MATCH_COUNT})')
             plt.show()
        return None

def autocrop (img) : 
    template_image_path = 'template_sift_top.png' 
    return autocrop_sift_ratio(img, template_image_path)


if __name__ == '__main__':

    imgs_dir = '.'
    output_dir = 'autocroped_sift_ratio'
    template_image_path = 'template_sift_top.png'

    # --- Set Target Aspect Ratio ---
    try:
        # Optionally load from a config file or args later
        target_ratio = TARGET_ASPECT_RATIO
        if target_ratio <= 0: raise ValueError("Aspect ratio must be positive")
        print(f"Using Target Aspect Ratio (W/H): {target_ratio}")
    except Exception as e:
        print(f"Error setting target aspect ratio: {e}")
        exit()


    if not os.path.exists(template_image_path):
        print(f"\nERROR: Template file '{template_image_path}' not found.")
        print("Please create this template image meeting the width and top-section criteria.")
        exit()

    imgs = os.listdir(imgs_dir)
    # Filter for common image types, excluding the template itself
    imgs = [f for f in imgs if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp')) and f != os.path.basename(template_image_path)]
    print(f"\nFound {len(imgs)} images in '{imgs_dir}' to process.")

    os.makedirs(output_dir, exist_ok=True)

    processed_count = 0
    failed_count = 0
    for img_name in imgs:
        img_path = os.path.join(imgs_dir, img_name)
        print(f"\nProcessing: {img_name}")
        img = cv2.imread(img_path)

        if img is None:
            print(f"  Warning: Could not read image {img_name}. Skipping.")
            failed_count += 1
            continue

        autocroped = autocrop_sift_ratio(img, template_image_path)

        if autocroped is not None and autocroped.size > 0:
            output_path = os.path.join(output_dir, img_name)
            try:
                cv2.imwrite(output_path, autocroped)
                print(f"  Success: Saved cropped image to {output_path}")
                processed_count += 1
            except Exception as e:
                print(f"  Error: Failed to save {output_path}: {e}")
                failed_count += 1
        else:
            print(f"  Failed: Could not robustly find/crop window in {img_name}")
            failed_count += 1

    print(f"\n--- Processing complete ---")
    print(f"Successfully cropped: {processed_count}")
    print(f"Failed/Skipped:      {failed_count}")