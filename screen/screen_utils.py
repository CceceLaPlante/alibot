# screen_utils.py
import jellyfish
import string
import logging
import math # For isnan

logger = logging.getLogger(__name__)

def word_to_known (distance_func, word, vocab, threshold=3) :
    """
    Finds the closest word in vocab to the input word using distance_func,
    if the distance is below the threshold. Handles numbers and punctuation/whitespace.
    """
    # Ignore if word is purely punctuation or whitespace
    if all(c in string.punctuation or c.isspace() for c in word):
        return word, float('inf') # Return original, indicate not a match

    # Check if it's a number (handle potential variations)
    if isnumber(word) :
        return word, -1 # Return original, indicate it's a number

    if not vocab: # Check if vocab is empty
        logger.warning("word_to_known called with empty vocab, returning original word.")
        return word, float('inf')

    best_word = ""
    best_distance = float("inf")

    # Preprocess the input word once for comparison
    processed_word = preprocess(word)
    if not processed_word: # Handle cases where preprocessing empties the word
        return word, float('inf')

    # Compare against preprocessed words in vocab (assuming vocab contains already processed words)
    # If vocab is raw, preprocess w inside the loop: processed_w = preprocess(w)
    for w in vocab :
        # Assuming vocab words are already preprocessed. If not, preprocess here:
        # processed_w = preprocess(w)
        # d = distance_func(processed_word, processed_w)
        d = distance_func(processed_word, w) # Assumes vocab is preprocessed
        if d <= threshold and d < best_distance : # Use < to prefer earlier matches in case of ties
            best_word = w
            best_distance = d

    # Return the *original* vocab word if found, otherwise the original input word
    if best_word:
        # logger.debug(f"Mapped '{word}' (processed: '{processed_word}') to '{best_word}' with distance {best_distance}")
        return best_word, best_distance
    else:
        # logger.debug(f"No close match found for '{word}' (processed: '{processed_word}') in vocab (threshold {threshold}).")
        return word, float('inf') # Return original word, indicate no match found


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