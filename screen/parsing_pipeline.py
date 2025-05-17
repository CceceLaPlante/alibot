# parsing_pipeline.py
# Ensure screen_utils is correctly importable. If it's in the same directory:
try:
    from .screen_utils import word_to_known, preprocess, distance, isnumber, ymean, ystd
except ImportError:
    # Fallback for direct execution or different project structure
    from screen_utils import word_to_known, preprocess, distance, isnumber, ymean, ystd
    print("Warning: Using fallback import for screen_utils in parsing_pipeline.py")


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

    for i, word in enumerate(words):
        processed_word = preprocess(word) # preprocess from screen_utils
        if processed_word:
            new_words.append(processed_word)
            if i < len(positions) and positions[i] and isinstance(positions[i], (list, tuple)) and len(positions[i]) >= 2:
                new_positions.append(positions[i])
            else:
                logger.warning(f"Stage 0: Missing or invalid position for word '{word}' (original) at index {i}. Processed: '{processed_word}'. Position: {positions[i] if i < len(positions) else 'N/A'}. Skipping word.")
                if new_words and new_words[-1] == processed_word: # Ensure we pop the correct one
                    new_words.pop()


    logger.info(f"Stage 0: Reduced words from {len(words)} to {len(new_words)} after preprocessing.")
    return new_words, new_positions

def stage1 (words_from_stage0, positions, raw_vocab_list, threshold=3): # raw_vocab_list is id_card.VOCABULARY
    """
    Stage 1: Maps words (already preprocessed by stage0) to known vocabulary words.
    Keeps original word from stage0 if no close match is found or if it's a number.
    """
    logger.info("Stage 1: Mapping words to vocabulary.")
    if not words_from_stage0:
        logger.warning("Stage 1 received empty words list.")
        return [], []

    mapped_words_output = []

    # Preprocess the raw vocabulary list ONCE for this stage
    preprocessed_vocab_set = set(preprocess(v) for v in raw_vocab_list if v)
    if not preprocessed_vocab_set:
        logger.warning("Stage 1: Vocabulary became empty after preprocessing. All words will be kept as original.")

    for i, ocr_word_processed_in_stage0 in enumerate(words_from_stage0):
        # Note: word_to_known expects the "original_word_from_ocr" as its second argument.
        # However, stage0 already did preprocessing. If word_to_known *needs* the truly raw OCR word
        # for its punctuation/isnumber checks, stage0 would need to pass that along.
        # Assuming for now that the `isnumber` and punctuation checks in `word_to_known`
        # are fine even if the input `ocr_word_processed_in_stage0` has undergone basic cleaning by `preprocess`.
        # If `preprocess` strips away what `isnumber` relies on, this could be an issue.
        # For simplicity, let's pass the output of stage0 as the "original" for word_to_known's perspective.

        # The `ocr_word_processed_in_stage0` is ALREADY preprocessed by stage0.
        # `word_to_known` will preprocess it AGAIN. This is slightly redundant but usually harmless.
        # If performance is critical, you could have two versions of word_to_known,
        # or modify it to optionally skip internal preprocessing.

        # For the current word_to_known, we pass the output of stage0 as `original_word_from_ocr`
        # and it will be preprocessed again internally by word_to_known.
        matched_word, dist = word_to_known(distance, ocr_word_processed_in_stage0, preprocessed_vocab_set, threshold=threshold)

        # `matched_word` will be:
        # 1. A word from `preprocessed_vocab_set` if a good match.
        # 2. The `ocr_word_processed_in_stage0` itself if it was a number.
        # 3. The `ocr_word_processed_in_stage0` itself if no good vocab match.
        mapped_words_output.append(matched_word)

    logger.info("Stage 1: Finished mapping words.")
    return mapped_words_output, positions

def stage2 (words, positions, known_names_and_aliases, vocabulary, std_factor=4):
    """
    Stage 2: Classify words into potential names (known primary names, known aliases, or unknown)
             vs other vocabulary words/numbers.
    'known_names_and_aliases' is the comprehensive list of preprocessed primary IdCard names and all their preprocessed aliases.
    Returns a dictionary.
    """
    logger.info(f"Stage 2: Classifying words. Using {len(known_names_and_aliases)} known names/aliases.")
    if not words:
        logger.warning("Stage 2 received empty words list.")
        return {"names": [], "name_positions": [], "nonames": [], "noname_positions": []}

    # Ensure known_names_and_aliases are preprocessed and in a set for efficient lookup.
    # This list comes from DataManagementCog.get_all_recognizable_names(), which should return cleaned (preprocessed) names.
    known_names_aliases_set = set(known_names_and_aliases)

    # Ensure vocabulary words are preprocessed for comparison
    # vocab is passed from EndScreen.parse -> id_card.VOCABULARY
    vocabulary_set = set(preprocess(v) for v in vocabulary if v)

    potential_names = []
    potential_name_positions = []
    non_name_words = []
    non_name_positions = []

    for i, word in enumerate(words): # 'word' is preprocessed from stage0, potentially mapped in stage1
        pos = positions[i]
        if not (isinstance(pos, (list, tuple)) and len(pos) >= 2):
             logger.warning(f"Stage 2: Skipping word '{word}' due to invalid position format: {pos}")
             continue

        # Classification Logic:
        if word in known_names_aliases_set:
            # It's a known primary name or a known alias
            potential_names.append(word)
            potential_name_positions.append(pos)
            # logger.debug(f"Stage 2: Classified '{word}' as Potential Name (Known Name/Alias)")
        elif word in vocabulary_set or isnumber(word):
            # It's a specific vocabulary word (like 'perdants', 'niveau') or a number
            non_name_words.append(word)
            non_name_positions.append(pos)
            # logger.debug(f"Stage 2: Classified '{word}' as Non-Name Word (Vocab/Number)")
        else:
            # It's not a known name/alias, not specific vocab, not a number -> Assume it's a potential unknown name
            # Add filters here if needed (e.g., length, character types)
            # For now, keeping it inclusive:
            if len(word) > 1 and any(char.isalpha() for char in word): # Basic filter: at least 2 chars and one letter
                potential_names.append(word)
                potential_name_positions.append(pos)
                # logger.debug(f"Stage 2: Classified '{word}' as Potential Name (Unknown but plausible)")
            else:
                # Words that don't fit other categories and are too short or non-alpha might be noise
                non_name_words.append(word) # Or discard, or put in a 'noise' category
                non_name_positions.append(pos)
                # logger.debug(f"Stage 2: Classified '{word}' as Non-Name Word (Likely Noise/Junk)")


    logger.info(f"Stage 2: Classified into {len(potential_names)} potential names and {len(non_name_words)} non-name/noise words.")
    return {"names": potential_names,
            "name_positions": potential_name_positions,
            "nonames": non_name_words,
            "noname_positions": non_name_positions}


def stage3 (word_dict):
    """
    Stage 3: Separate potential names into winners and losers based on their Y-position
             relative to the 'perdants' keyword found in 'nonames'.
    Returns lists: winners, losers.
    """
    logger.info("Stage 3: Separating winners and losers based on 'perdants' keyword position.")
    winners = []
    losers = []

    potential_names = word_dict.get("names", [])
    potential_name_positions = word_dict.get("name_positions", [])
    non_names = word_dict.get("nonames", []) # These are words classified as non-player-names by stage2
    non_name_positions = word_dict.get("noname_positions", [])

    if not potential_names:
        logger.warning("Stage 3: No potential names found to classify into winners/losers.")
        return [], []

    frontier_y = -1
    perdants_keyword_found = False

    # Find 'perdants' keyword in the non_names list (words from stage1 mapped to vocab)
    # Ensure 'perdants' is preprocessed if it was in original vocab. It should be "perdants".
    target_keyword = preprocess("perdants") # Should just be "perdants"

    for i, nn_word in enumerate(non_names):
        if nn_word == target_keyword: # nn_word is already preprocessed from stage1 or kept as is
            if i < len(non_name_positions):
                perdants_pos = non_name_positions[i]
                if isinstance(perdants_pos, (list, tuple)) and len(perdants_pos) >= 2:
                    frontier_y = perdants_pos[1] # Y-coordinate of 'perdants'
                    perdants_keyword_found = True
                    logger.info(f"Stage 3: Found '{target_keyword}' keyword at Y-position: {frontier_y:.2f}")
                    break # Use the first occurrence
                else:
                    logger.warning(f"Stage 3: Found '{target_keyword}' but its position '{perdants_pos}' is invalid.")
            else:
                logger.warning(f"Stage 3: Found '{target_keyword}' word but its position data is missing.")

    if not perdants_keyword_found:
        logger.warning(f"Stage 3: Keyword '{target_keyword}' not found or its position invalid. Cannot reliably determine winner/loser split based on Y-position.")
        # Fallback: If 'victoire' or 'défaite' keywords are present, could try to use them.
        # Or, if 'perdants' is missing, it might imply everyone listed is a winner (if it's a victory screen without clear team separation).
        # This is a complex heuristic. For now, if no 'perdants', we can't split by Y.
        # One option: return all potential_names as unclassified or in a single list.
        # For now, returning empty as per original if 'perdants' not found for split.
        return [], []


    for i, name in enumerate(potential_names):
        if i < len(potential_name_positions):
             pos = potential_name_positions[i]
             if isinstance(pos, (list, tuple)) and len(pos) >= 2:
                 name_y = pos[1]
                 # Winners are ABOVE 'perdants' (lower Y value)
                 # Losers are BELOW 'perdants' (higher Y value)
                 if name_y < frontier_y:
                     winners.append(name)
                 else: # name_y >= frontier_y
                     losers.append(name)
             else:
                 logger.warning(f"Stage 3: Skipping name '{name}' due to invalid position: {pos}")
        else:
             logger.warning(f"Stage 3: Skipping name '{name}' due to missing position data for it.")

    logger.info(f"Stage 3: Classified {len(winners)} winners and {len(losers)} losers.")
    return winners, losers