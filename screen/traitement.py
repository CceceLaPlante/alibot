import urllib3
import discord
import numpy as np
import cv2
import logging
import time

logger = logging.getLogger(__name__)

# Assuming id_card.py is in the parent directory or accessible
# If not, adjust the import path: from ..id_card import VOCABULARY
try:
    from id_card import VOCABULARY
except ImportError:
    logger.warning("Could not import VOCABULARY from id_card. Using empty list.")
    VOCABULARY = []


from .autocrop_sift import autocrop # Assuming autocrop works or handles errors
from .EndScreen import EndScreen
from .screen_utils import distance # word_to_known is used within EndScreen.parse

# Import PaddleOCR correctly
try:
    from paddleocr import PaddleOCR
    # Initialize PaddleOCR engine - Outside the function for efficiency if called multiple times
    # Consider making language ('fr') configurable
    ocr_engine = PaddleOCR(lang='fr', use_angle_cls=True, show_log=False)
    logger.info("PaddleOCR engine initialized.")
except ImportError:
    logger.error("PaddleOCR library not found. Please install paddleocr and paddlepaddle.")
    ocr_engine = None
except Exception as e:
    logger.exception(f"Failed to initialize PaddleOCR: {e}")
    ocr_engine = None


logger = logging.getLogger(__name__)


def from_link_to_result (url: str, KNOWN_NAMES: list, nocrop: bool = False) -> EndScreen:
    """
    Downloads an image from URL, preprocesses it, performs OCR,
    and parses the result into an EndScreen object.
    """
    if ocr_engine is None:
         raise RuntimeError("PaddleOCR engine is not available or failed to initialize.")

    if not isinstance(KNOWN_NAMES, list):
        logger.warning("KNOWN_NAMES passed to from_link_to_result is not a list. Using empty list.")
        KNOWN_NAMES = []

    # --- Download Image ---
    start_time = time.time()
    http = urllib3.PoolManager()
    try:
        logger.info(f"Downloading image from: {url}")
        r = http.request('GET', url, timeout=10.0) # Added timeout
        if r.status != 200:
             logger.error(f"Failed to download image. Status code: {r.status}, URL: {url}")
             raise ValueError(f"Échec du téléchargement de l'image (Code: {r.status}).")
        logger.info(f"Image downloaded successfully ({len(r.data)} bytes).")
        img_data = r.data
    except urllib3.exceptions.MaxRetryError as e:
         logger.error(f"Network error downloading image: {e}, URL: {url}")
         raise ValueError(f"Erreur réseau lors du téléchargement: {e}")
    except urllib3.exceptions.TimeoutError:
         logger.error(f"Timeout error downloading image: {url}")
         raise ValueError("Le téléchargement de l'image a expiré.")
    except Exception as e:
         logger.exception(f"Unexpected error downloading image: {e}, URL: {url}")
         raise ValueError(f"Erreur inconnue lors du téléchargement: {e}")
    finally:
        # Release connection back to the pool
        if 'r' in locals() and hasattr(r, 'release_conn'):
            r.release_conn()


    # --- Decode Image ---
    try:
        arr = np.asarray(bytearray(img_data), dtype=np.uint8)
        # Decode as color image
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            logger.error("Failed to decode image data.")
            raise ValueError("Échec du décodage de l'image.")
        logger.info(f"Image decoded, initial shape: {img.shape}")
    except Exception as e:
        logger.exception(f"Error decoding image: {e}")
        raise ValueError(f"Erreur lors du décodage de l'image: {e}")

    # --- Image Preprocessing ---
    preprocessed_img = img
    # 1. Cropping (Optional)
    if not nocrop:
        logger.info("Applying autocrop...")
        try:
            autocroped_result = autocrop(preprocessed_img) # Assuming autocrop takes and returns numpy array
            if isinstance(autocroped_result, np.ndarray) and autocroped_result.size > 0:
                # Basic check: ensure cropped area isn't ridiculously small
                if autocroped_result.shape[0] > 10 and autocroped_result.shape[1] > 10:
                    preprocessed_img = autocroped_result
                    logger.info(f"Autocrop successful, new shape: {preprocessed_img.shape}")
                else:
                    logger.warning(f"Autocrop resulted in very small image ({autocroped_result.shape}). Using image before crop.")
            else:
                logger.warning("Autocrop did not return a valid/non-empty image. Using image before crop.")
        except Exception as e:
             logger.exception(f"Error during autocrop: {e}. Using image before crop.")
             # Continue with the uncropped image

    if preprocessed_img is None or preprocessed_img.size == 0:
         logger.error("Image is empty after potential crop stage.")
         raise ValueError("L'image est vide après le recadrage.")

    # 2. Resizing (Consider if necessary - OCR might work better on original/larger size)
    # Resizing can sometimes hurt OCR accuracy, especially if text becomes too small.
    # Let's make resizing optional or conditional. Maybe resize only if image is huge?
    # Target width for consistency might still be good.
    resized_img = preprocessed_img
    try:
        target_width = 1200 # Increased target width, might help OCR
        h, w = resized_img.shape[:2]
        if w > 0 and h > 0:
            # Only resize if width is significantly different from target?
            # Or always resize for consistency? Let's resize for consistency for now.
            target_height = int(h * target_width / w)
            resized_img = cv2.resize(resized_img, (target_width, target_height), interpolation=cv2.INTER_CUBIC)
            logger.info(f"Image resized to: {resized_img.shape}")
        else:
            logger.warning("Invalid dimensions for resizing. Using image as is.")
    except Exception as e:
        logger.exception(f"Error during resize: {e}. Using image before resize.")
        resized_img = preprocessed_img # Fallback to pre-resize state


    if resized_img is None or resized_img.size == 0:
         logger.error("Image is empty after potential resize stage.")
         raise ValueError("L'image est vide après le redimensionnement.")

    # 3. Ensure RGB format (PaddleOCR often expects RGB, OpenCV uses BGR)
    try:
        # Check if image is grayscale first
        if len(resized_img.shape) == 2 or resized_img.shape[2] == 1:
            img_for_ocr = cv2.cvtColor(resized_img, cv2.COLOR_GRAY2BGR) # Convert grayscale to BGR
            img_for_ocr = cv2.cvtColor(img_for_ocr, cv2.COLOR_BGR2RGB) # Then BGR to RGB
            logger.info("Converted grayscale image to RGB for PaddleOCR.")
        elif resized_img.shape[2] == 3: # BGR
             img_for_ocr = cv2.cvtColor(resized_img, cv2.COLOR_BGR2RGB)
             logger.info("Converted BGR image to RGB for PaddleOCR.")
        elif resized_img.shape[2] == 4: # BGRA
            img_for_ocr = cv2.cvtColor(resized_img, cv2.COLOR_BGRA2RGB)
            logger.info("Converted BGRA image to RGB for PaddleOCR.")
        else:
            logger.warning(f"Unexpected image channels ({resized_img.shape[2]}). Using as is for OCR.")
            img_for_ocr = resized_img

    except cv2.error as e:
        logger.exception(f"OpenCV error during color conversion: {e}. Using image as is.")
        img_for_ocr = resized_img # Fallback

    # --- PaddleOCR Call ---
    logger.info("Running PaddleOCR...")
    start_ocr = time.time()
    ocr_result = None
    try:
        ocr_result = ocr_engine.ocr(img_for_ocr, cls=True)
    except Exception as e:
        logger.exception(f"PaddleOCR execution failed: {e}")
        raise ValueError(f"Erreur lors de l'exécution de PaddleOCR: {e}") from e

    ocr_duration = time.time() - start_ocr
    logger.info(f"PaddleOCR finished in {ocr_duration:.2f}s")

    # --- Process PaddleOCR Output ---
    all_words = []
    all_word_positions = [] # Store approximated (center_x, center_y) for each word
    raw_ocr_lines = []      # <-- STORE RAW LINES FOR PRISM CHECK

    if not ocr_result or not ocr_result[0]:
         logger.warning("PaddleOCR returned no results.")
    else:
        logger.info(f"PaddleOCR detected {len(ocr_result[0])} lines.")
        line_count = 0
        word_count = 0
        for line_data in ocr_result[0]:
            line_count += 1
            try:
                box = line_data[0]
                text = line_data[1][0]
                confidence = line_data[1][1]

                raw_ocr_lines.append(text) # <-- STORE RAW LINE

                confidence_threshold = 0.6
                if confidence < confidence_threshold:
                    continue

                center_x = sum(p[0] for p in box) / 4
                center_y = sum(p[1] for p in box) / 4

                words_in_line = text.split()
                if not words_in_line: continue

                for word in words_in_line:
                    word_count += 1
                    all_words.append(word)
                    all_word_positions.append((center_x, center_y))

            except (IndexError, TypeError, Exception) as e:
                logger.warning(f"Error processing line {line_count} from PaddleOCR results: {e}. Line data: {line_data}", exc_info=True)
                continue

        logger.info(f"Extracted {word_count} words from {line_count} lines after confidence filtering.")


    # --- Parse using the EndScreen class ---
    endscreen = EndScreen()
    logger.info("Passing extracted words, positions, and raw lines to EndScreen parser.")
    try:
        # Pass the raw OCR lines as well
        endscreen.parse(all_words, all_word_positions, raw_ocr_lines, KNOWN_NAMES, VOCABULARY)
        logger.info("EndScreen parsing completed.")
    except ValueError as e:
         logger.error(f"Known error during EndScreen parsing: {e}", exc_info=True)
         raise
    except Exception as e:
         logger.exception(f"Unexpected error during EndScreen parsing: {e}")
         raise ValueError(f"Erreur inattendue lors de l'analyse des résultats OCR: {e}") from e

    total_duration = time.time() - start_time
    logger.info(f"Total processing time for {url}: {total_duration:.2f}s")
    return endscreen