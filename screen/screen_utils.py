# screen_utils.py
import jellyfish
import string
import logging
import math # For isnan

logger = logging.getLogger(__name__)

def word_to_known (distance_func, original_word_from_ocr, preprocessed_vocab_set, threshold=3):
    """
    Finds the closest word in preprocessed_vocab_set to the preprocessed version
    of original_word_from_ocr using distance_func, if the distance is below the threshold.
    Handles numbers and punctuation/whitespace.

    Args:
        distance_func: Function to calculate distance (e.g., Levenshtein).
        original_word_from_ocr: The raw word string as obtained from OCR.
        preprocessed_vocab_set: A set of already preprocessed vocabulary strings.
        threshold: Maximum distance to consider a match.

    Returns:
        tuple: (matched_word, distance)
               - matched_word: The word from preprocessed_vocab_set if a match is found within threshold,
                               OR the original_word_from_ocr if it's a number,
                               OR the original_word_from_ocr if no suitable vocab match.
               - distance: The calculated distance for the match, -1 for numbers, float('inf') for no match.
    """
    # 1. Handle pure punctuation/whitespace based on the original OCR word
    if all(c in string.punctuation or c.isspace() for c in original_word_from_ocr):
        # logger.debug(f"'{original_word_from_ocr}' is all punctuation/space. Returning as is.")
        return original_word_from_ocr, float('inf')

    # 2. Check if the original OCR word is a number
    if isnumber(original_word_from_ocr):
        # logger.debug(f"'{original_word_from_ocr}' is a number. Returning as is with dist -1.")
        return original_word_from_ocr, -1

    # 3. Preprocess the input word from OCR for comparison against preprocessed vocabulary
    processed_ocr_word = preprocess(original_word_from_ocr)
    if not processed_ocr_word: # If preprocessing results in an empty string
        # logger.debug(f"Preprocessing '{original_word_from_ocr}' resulted in empty string. Returning original.")
        return original_word_from_ocr, float('inf')

    # 4. Check if vocab is empty
    if not preprocessed_vocab_set:
        logger.warning("word_to_known called with empty preprocessed_vocab_set, returning original word.")
        return original_word_from_ocr, float('inf')

    # 5. Find the best match in the preprocessed vocabulary
    best_vocab_match = "" # This will be a word from preprocessed_vocab_set
    min_distance = float("inf")

    for vocab_w in preprocessed_vocab_set:
        # Both processed_ocr_word and vocab_w are preprocessed at this point
        d = distance_func(processed_ocr_word, vocab_w)
        if d < min_distance: # Update if this distance is strictly better
            min_distance = d
            best_vocab_match = vocab_w
        # If d == min_distance, we keep the first one encountered (arbitrary tie-break)

    # 6. Decide what to return based on the threshold
    if min_distance <= threshold:
        # A good match was found in the vocabulary. Return the matched *vocabulary word*.
        # logger.debug(f"Mapped OCR word '{original_word_from_ocr}' (processed: '{processed_ocr_word}') to vocab '{best_vocab_match}' with distance {min_distance}")
        return best_vocab_match, min_distance
    else:
        # No close match found in vocabulary. Return the *original OCR word*.
        # logger.debug(f"No close vocab match for OCR word '{original_word_from_ocr}' (processed: '{processed_ocr_word}'). Min dist: {min_distance} > threshold: {threshold}. Returning original.")
        return original_word_from_ocr, min_distance # Return actual min_distance for potential logging/use, even if > threshold

def _no_accent(word) :
    # Simplified accent removal
    no_accent_map = str.maketrans("éèêàâîïôùûç", "eeeaaioouuc")
    return word.translate(no_accent_map)

def _strip_whitelist(letter) :
    # Consider adding uppercase if needed, although preprocess lowercases it
    whitelist = "0123456789abcdefghijklmnopqrstuvwxyz_-:()#"
    return letter if letter in whitelist else ""

def preprocess (word)  :
    word = word.lower()
    word = _no_accent(word)
    # Apply whitelist character by character
    word = "".join(_strip_whitelist(c) for c in word)

    # Remove single characters unless they are numbers? Dofus names are usually longer.
    # if len(word) == 1 and not word.isdigit():
    #     word = ""
    # Keep single chars for now, filter later if needed based on context

    return word

def isnumber (word) :
    """Checks if a string represents a number, allowing for common formats."""
    if not isinstance(word, str):
        return False
    # Allow for negative, decimal points, commas, colons (like time?), percentage
    cleaned_word = word.replace('.', '', 1).replace(",", '', 1).replace("-", '', 1).replace(":", '', 1).replace("%", '', 1)
    return cleaned_word.isdigit()

def distance(text1, text2) :
    """Calculates Levenshtein distance."""
    # Ensure inputs are strings
    text1 = str(text1)
    text2 = str(text2)
    return jellyfish.levenshtein_distance(text1, text2)

def ymean (positions) :
    """
    Compute the mean of the Y coordinates (index 1) of the positions.
    Assumes positions is a list of tuples/lists like (x, y) or [[x1,y1], [x2,y2]...].
    Uses the second element (index 1) as the Y coordinate.
    """
    if not positions:
        return 0
    # Filter out potential None or invalid entries if necessary
    valid_y = [p[1] for p in positions if isinstance(p, (list, tuple)) and len(p) > 1 and isinstance(p[1], (int, float))]
    if not valid_y:
        return 0
    return sum(valid_y) / len(valid_y)

def ystd (positions) :
    """
    Compute the standard deviation of the Y coordinates (index 1) of the positions.
    Uses the second element (index 1) as the Y coordinate.
    """
    if not positions or len(positions) < 2: # Std dev requires at least 2 points
        return 0

    valid_y = [p[1] for p in positions if isinstance(p, (list, tuple)) and len(p) > 1 and isinstance(p[1], (int, float))]
    if len(valid_y) < 2:
        return 0

    mean = sum(valid_y) / len(valid_y)
    variance = sum([(y - mean)**2 for y in valid_y]) / len(valid_y)
    std_dev = math.sqrt(variance)
    # Handle potential NaN if variance is negative due to float issues (unlikely here)
    return std_dev if not math.isnan(std_dev) else 0

# Keep xmean/xstd if you need X-coordinate analysis elsewhere, otherwise remove
def xmean (positions) :
    """Compute the mean of the X coordinates (index 0)."""
    if not positions: return 0
    valid_x = [p[0] for p in positions if isinstance(p, (list, tuple)) and len(p) > 0 and isinstance(p[0], (int, float))]
    if not valid_x: return 0
    return sum(valid_x) / len(valid_x)

def xstd (positions) :
    """Compute the standard deviation of the X coordinates (index 0)."""
    if not positions or len(positions) < 2: return 0
    valid_x = [p[0] for p in positions if isinstance(p, (list, tuple)) and len(p) > 0 and isinstance(p[0], (int, float))]
    if len(valid_x) < 2: return 0
    mean = sum(valid_x) / len(valid_x)
    variance = sum([(x - mean)**2 for x in valid_x]) / len(valid_x)
    std_dev = math.sqrt(variance)
    return std_dev if not math.isnan(std_dev) else 0