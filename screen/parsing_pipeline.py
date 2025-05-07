# parsing_pipeline.py
from .screen_utils import word_to_known, preprocess, distance, isnumber, ymean, ystd # Use ymean/ystd

import os
import logging

logger = logging.getLogger(__name__)

def stage0(words, positions):
    """
    Stage 0: Preprocess words and filter empty results.
    Returns new lists of words and corresponding positions.
    """
    logger.info("Stage 0: Preprocessing words and positions.")
    if not words:
        logger.warning("Stage 0 received empty words list.")
        return [], []

    new_words = []
    new_positions = []
    # logger.debug(f"Stage 0 Input words: {words}") # Can be verbose

    for i, word in enumerate(words):
        processed_word = preprocess(word)
        if processed_word: # Only keep non-empty words after preprocessing
            new_words.append(processed_word)
            # Ensure position exists and is valid before adding
            if i < len(positions) and positions[i]:
                new_positions.append(positions[i])
            else:
                logger.warning(f"Missing or invalid position for word '{word}' at index {i}. Skipping word.")
                new_words.pop() # Remove the word added if position is invalid

    logger.info(f"Stage 0: Reduced words from {len(words)} to {len(new_words)} after preprocessing.")
    # logger.debug(f"Stage 0 Output words: {new_words}")
    return new_words, new_positions

def stage1 (words, positions, vocab, threshold=3):
    """
    Stage 1: Map words to known vocabulary words using Levenshtein distance.
    Keeps original word if no close match is found or if it's a number.
    Assumes vocab contains preprocessed words.
    Returns new list of mapped words and original positions.
    """
    logger.info("Stage 1: Mapping words to vocabulary.")
    if not words:
        logger.warning("Stage 1 received empty words list.")
        return [], []

    mapped_words = []
    # Assuming vocab contains preprocessed words for efficiency
    preprocessed_vocab = set(preprocess(v) for v in vocab) # Ensure vocab is preprocessed and unique

    for i, word in enumerate(words):
        # word_to_known expects the *unprocessed* word for number/punctuation checks
        # but compares its *processed* version against the vocab
        # Let's adjust word_to_known or how we call it.
        # Option: Pass the raw word from stage0 if needed, but stage0 already preprocesses.
        # Let's trust stage0 preprocessing and pass the already processed word.
        # Re-check word_to_known logic - it preprocesses again internally. Redundant.

        # --- Call word_to_known with the word already processed in stage0 ---
        # We need the original distance function from screen_utils
        known_word, dist = word_to_known(distance, word, preprocessed_vocab, threshold=threshold)

        # word_to_known returns the *vocab word* if matched, or the *original input word* otherwise.
        # It also returns -1 distance for numbers.
        if dist == -1: # Is a number
            mapped_words.append(word) # Keep the number as is
            # logger.debug(f"Stage 1: Kept number '{word}'")
        elif dist <= threshold: # Matched a vocab word
            mapped_words.append(known_word) # Use the matched vocab word
            # logger.debug(f"Stage 1: Mapped '{word}' to vocab '{known_word}' (dist {dist})")
        else: # Not a number, no close match in vocab
            mapped_words.append(word) # Keep the original (unmatched) word
            # logger.debug(f"Stage 1: Kept original word '{word}' (no match, dist {dist})")

    logger.info("Stage 1: Finished mapping words.")
    # logger.debug(f"Stage 1 Output words: {mapped_words}")
    return mapped_words, positions # Return original positions

def stage2 (words, positions, known_names, vocabulary, std_factor=4): # std_factor is no longer used here
    """
    Stage 2: Classify words into potential names (known or unknown) vs
             other vocabulary words/numbers. More inclusive of unknown names.
    Returns a dictionary containing lists of 'potential_names', 'potential_name_positions',
    'non_name_words', 'non_name_positions'.
    """
    logger.info("Stage 2: Classifying words into potential names and non-names (Relaxed).")
    if not words:
        logger.warning("Stage 2 received empty words list.")
        return {"potential_names": [], "potential_name_positions": [], "non_name_words": [], "non_name_positions": []}

    known_names_set = set(known_names) # Assumes known_names are already preprocessed if needed
    # Ensure vocabulary words are preprocessed for comparison
    vocabulary_set = set(preprocess(v) for v in vocabulary)

    potential_names = []
    potential_name_positions = []
    non_name_words = [] # Words identified as vocabulary or numbers
    non_name_positions = []

    for i, word in enumerate(words):
        pos = positions[i]
        if not (isinstance(pos, (list, tuple)) and len(pos) >= 2):
             logger.warning(f"Stage 2: Skipping word '{word}' due to invalid position format: {pos}")
             continue

        # Classification Logic:
        if word in known_names_set:
            # It's a known name
            potential_names.append(word)
            potential_name_positions.append(pos)
            # logger.debug(f"Stage 2: Classified '{word}' as Potential Name (Known)")
        elif word in vocabulary_set or isnumber(word):
            # It's a vocabulary word (like 'perdants', 'niveau') or a number
            non_name_words.append(word)
            non_name_positions.append(pos)
            # logger.debug(f"Stage 2: Classified '{word}' as Non-Name Word (Vocab/Number)")
        else:
            # It's not known, not vocab, not a number -> Assume it's a potential unknown name
            # Add simple filter? e.g., length > 1 or contains letters? Let's skip filters for now.
            potential_names.append(word)
            potential_name_positions.append(pos)
            # logger.debug(f"Stage 2: Classified '{word}' as Potential Name (Unknown)")

    logger.info(f"Stage 2: Classified into {len(potential_names)} potential names and {len(non_name_words)} non-name words.")

    # Return using consistent keys for stage 3
    return {"names": potential_names, # Keep 'names' key for compatibility with stage3 expectations
            "name_positions": potential_name_positions,
            "nonames": non_name_words, # Keep 'nonames' key
            "noname_positions": non_name_positions}


def stage3 (word_dict):
    """
    Stage 3: Separate potential names into winners and losers based on their Y-position
             relative to the 'perdants' keyword found in 'nonames'.
             CORRECTED LOGIC: Winners are ABOVE 'perdants' (lower Y),
                              Losers are BELOW 'perdants' (higher Y).
    Returns lists: winners, losers. (Corrected order)
    """
    logger.info("Stage 3: Separating winners and losers based on 'perdants' keyword position (Corrected Logic).")
    winners = [] # Swapped
    losers = []  # Swapped

    potential_names = word_dict.get("names", [])
    potential_name_positions = word_dict.get("name_positions", [])
    non_names = word_dict.get("nonames", [])
    non_name_positions = word_dict.get("noname_positions", [])

    if not potential_names:
        logger.warning("Stage 3: No potential names found to classify.")
        return [], [] # Return empty winners, losers

    frontier_y = -1

    try:
        perdants_indices = [i for i, word in enumerate(non_names) if word == "perdants"]
        if not perdants_indices:
            logger.warning("Stage 3: Keyword 'perdants' not found in non-name words. Cannot determine winner/loser split.")
            # Handle this case: maybe assume all potential names are winners if 'perdants' isn't found?
            # Or return all as unclassified? For now, return empty lists.
            return [], []

        perdants_index = perdants_indices[0] # Use first occurrence
        if perdants_index < len(non_name_positions):
            perdants_pos = non_name_positions[perdants_index]
            if isinstance(perdants_pos, (list, tuple)) and len(perdants_pos) >= 2:
                 frontier_y = perdants_pos[1] # Get the Y-coordinate of 'perdants'
                 logger.info(f"Stage 3: Found 'perdants' keyword at Y-position: {frontier_y:.2f}")
            else:
                 logger.warning(f"Stage 3: Found 'perdants' but its position '{perdants_pos}' is invalid. Cannot determine frontier.")
                 return [], []
        else:
            logger.warning(f"Stage 3: Found 'perdants' at index {perdants_index} but corresponding position is missing.")
            return [], []

    except Exception as e:
         logger.exception(f"Stage 3: Error finding 'perdants' position: {e}")
         return [], []


    # Classify names based on their Y-position relative to the frontier
    for i, name in enumerate(potential_names):
        if i < len(potential_name_positions):
             pos = potential_name_positions[i]
             if isinstance(pos, (list, tuple)) and len(pos) >= 2:
                 name_y = pos[1]

                 # --- CORRECTED LOGIC ---
                 # Winners are ABOVE 'perdants' (lower Y value)
                 # Losers are BELOW 'perdants' (higher Y value)
                 if name_y < frontier_y:
                     winners.append(name) # Name is ABOVE 'perdants'
                     # logger.debug(f"Stage 3: Classified '{name}' as WINNER (y={name_y:.2f} < frontier={frontier_y:.2f})")
                 else: # name_y >= frontier_y
                     losers.append(name) # Name is BELOW 'perdants'
                     # logger.debug(f"Stage 3: Classified '{name}' as LOSER (y={name_y:.2f} >= frontier={frontier_y:.2f})")
                 # --- END CORRECTED LOGIC ---

             else:
                 logger.warning(f"Stage 3: Skipping name '{name}' due to invalid position: {pos}")
        else:
             logger.warning(f"Stage 3: Skipping name '{name}' due to missing position data.")

    logger.info(f"Stage 3: Classified {len(winners)} winners and {len(losers)} losers.")
    # logger.debug(f"Stage 3 Winners: {winners}") # Should now be correct
    # logger.debug(f"Stage 3 Losers: {losers}")   # Should now be correct

    # Return in the order: winners, losers
    return winners, losers