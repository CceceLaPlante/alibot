import easyocr
import cv2
import time

# Use the EXACT SAME image file path on both systems
# (copy the known-good debug image from step 1)
image_path = 'last_img.png'
img = cv2.imread(image_path) # Read directly, skip download/preprocess

# Ensure image is RGB if needed (cv2 reads BGR by default)
img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

print("Initializing reader...")
start_init = time.time()
# Simplest reader, explicitly CPU
reader = easyocr.Reader(['fr'], gpu=False)
print(f"Reader initialized in {time.time() - start_init:.2f}s")


print("Running readtext...")
start_read = time.time()
result = reader.readtext(img_rgb)
print(f"readtext finished in {time.time() - start_read:.2f}s")

print("\n--- Results ---")
for (bbox, text, prob) in result:
    print(f'Text: "{text}", Probability: {prob:.4f}, BBox: {bbox}')
print("---------------")
