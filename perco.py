# perco.py
import logging
import os

logger = logging.getLogger(__name__)

class Perco () :
    def __init__ (self, locations_file="localisations.txt", tableau_file="tableau.txt") :
        self.locations_file = locations_file
        self.tableau_file = tableau_file
        self.localisations = []
        self.tableau: list[list[str]] | None = None # Type hint for clarity

        # Load data on initialization
        self.load_data()

    def load_data(self):
        """Loads both locations and tableau data."""
        if not self._load_localisations():
            logger.error(f"Failed to load essential locations from {self.locations_file}. Perco manager may be unusable.")
            if self.tableau is None: # Ensure tableau is at least an empty list if locations failed
                self.tableau = [[] for _ in range(7)] # List of 7 empty lists
            return False

        if not self._load_tableau():
            logger.warning(f"{self.tableau_file} not found or failed to load. Initializing empty schedule.")
            self._initialize_empty_tableau()
        return True


    def _load_localisations (self) -> bool:
        """Loads locations from the file. Returns True on success, False on error."""
        try:
            if not os.path.exists(self.locations_file):
                 logger.error(f"Locations file not found: {self.locations_file}")
                 self.localisations = []
                 return False
            with open(self.locations_file, "r", encoding='utf-8') as file:
                self.localisations = [line.strip() for line in file.readlines() if line.strip()]
            logger.info(f"Loaded {len(self.localisations)} locations from {self.locations_file}.")
            return True
        except Exception as e:
            logger.exception(f"Error loading locations from {self.locations_file}: {e}")
            self.localisations = [] # Ensure it's empty on error
            return False

    def _initialize_empty_tableau(self):
        """Creates an empty tableau (list of lists) based on current locations."""
        num_locs = len(self.localisations)
        # Create a list containing 7 inner lists (days), each with num_locs empty strings
        self.tableau = [["" for _ in range(num_locs)] for _ in range(7)]
        logger.info(f"Initialized empty tableau with shape (7 days, {num_locs} locations).")

    def _load_tableau (self) -> bool:
        """Loads schedule from the file into a list of lists. Returns True on success, False on error."""
        num_expected_locs = len(self.localisations)
        if num_expected_locs == 0:
            logger.warning("Cannot load tableau: No locations loaded.")
            self.tableau = [[] for _ in range(7)] # Ensure list structure
            return False

        loaded_rows: list[list[str]] = []
        try:
            if not os.path.exists(self.tableau_file):
                 logger.warning(f"Tableau file not found: {self.tableau_file}")
                 return False # Signal that we need to initialize

            with open(self.tableau_file, "r", encoding='utf-8') as file:
                lines = file.readlines()
                if len(lines) != 7:
                     logger.warning(f"Expected 7 lines (days) in {self.tableau_file}, found {len(lines)}. Adjusting.")

                for i, line in enumerate(lines):
                    if i >= 7: break # Only load max 7 days
                    values = [val.strip() for val in line.split(",")]
                    # Pad row if too short, truncate if too long (based on expected locations)
                    if len(values) < num_expected_locs:
                         values.extend([""] * (num_expected_locs - len(values)))
                         logger.warning(f"Padded row {i+1} in {self.tableau_file}")
                    elif len(values) > num_expected_locs:
                         values = values[:num_expected_locs]
                         logger.warning(f"Truncated row {i+1} in {self.tableau_file}")
                    loaded_rows.append(values)

            # Pad with empty rows if fewer than 7 lines were read
            while len(loaded_rows) < 7:
                loaded_rows.append([""] * num_expected_locs)

            self.tableau = loaded_rows
            logger.info(f"Loaded tableau data ({len(self.tableau)} days, {num_expected_locs} locations) from {self.tableau_file}.")
            return True

        except Exception as e:
            logger.exception(f"Error loading tableau from {self.tableau_file}: {e}")
            self.tableau = None # Indicate load failure
            return False


    def save_tableau (self) -> bool:
        """Saves the current schedule (list of lists) to the file."""
        if self.tableau is None:
            logger.error("Cannot save tableau: Data is not loaded or initialized.")
            return False
        if not isinstance(self.tableau, list):
             logger.error(f"Cannot save tableau: self.tableau is not a list (Type: {type(self.tableau)}).")
             return False

        num_locs = len(self.localisations)

        try:
            with open(self.tableau_file, "w", encoding='utf-8') as file:
                for day_index, day_list in enumerate(self.tableau):
                    if not isinstance(day_list, list):
                         logger.error(f"Cannot save: Day {day_index+1} data is not a list.")
                         return False
                    # Ensure row has correct length before saving
                    if len(day_list) != num_locs:
                         logger.warning(f"Correcting row {day_index+1} length before saving (Expected {num_locs}, got {len(day_list)}).")
                         # Pad or truncate the row in memory just before saving
                         if len(day_list) < num_locs:
                             day_list.extend([""] * (num_locs - len(day_list)))
                         else:
                             day_list = day_list[:num_locs]
                         self.tableau[day_index] = day_list # Update in-memory list too

                    line = ",".join(day_list) # Join elements of the inner list (day's data)
                    file.write(line + "\n")
            logger.info(f"Tableau data saved successfully to {self.tableau_file}.")
            return True
        except Exception as e:
            logger.exception(f"Error saving tableau to {self.tableau_file}: {e}")
            return False

    def raz (self) -> bool:
        """Resets the schedule to empty based on current locations."""
        logger.warning("Resetting Perco schedule (RAZ).")
        if not self._load_localisations():
             logger.error("Cannot RAZ: Failed to load locations.")
             return False
        self._initialize_empty_tableau()
        return self.save_tableau()

    def refresh (self) -> bool:
        """Reloads locations and schedule data from files."""
        logger.info("Refreshing Perco data from files.")
        return self.load_data()

    def reserve (self, localisation: str, name: str, date_str: str) -> tuple[bool, int]:
        """
        Attempts to reserve a spot. Uses list indexing.
        Error Codes: 0: OK, 1: Invalid date, 2: Limit reached, 3: Invalid location, 5: Slot taken, -1: System error
        """
        if self.tableau is None or not isinstance(self.tableau, list):
             logger.error("Reservation failed: Tableau not initialized or not a list.")
             return False, -1

        # --- Validation ---
        loc_lower = localisation.lower()
        try:
            idx = next(i for i, loc in enumerate(self.localisations) if loc.lower() == loc_lower)
            actual_localisation = self.localisations[idx]
        except StopIteration:
             logger.warning(f"Reservation failed: Invalid location '{localisation}'.")
             return False, 3

        try:
            # Check if tableau has days before accessing len
            if not self.tableau:
                 raise ValueError("Tableau is empty")
            num_days = len(self.tableau)
            date_idx = int(date_str) - 1
            if not (0 <= date_idx < num_days):
                raise ValueError("Date out of bounds")
            # Check if day row has locations before accessing len
            if date_idx >= len(self.tableau) or not self.tableau[date_idx]:
                 raise IndexError(f"Day {date_idx} data is missing or invalid.")
            num_locs_this_day = len(self.tableau[date_idx])
            if idx >= num_locs_this_day:
                 raise IndexError(f"Location index {idx} out of bounds for day {date_idx} (len={num_locs_this_day})")

        except (ValueError, TypeError):
            logger.warning(f"Reservation failed: Invalid date '{date_str}'.")
            return False, 1
        except IndexError as ie:
             logger.error(f"Reservation failed: Index error accessing tableau. {ie}")
             return False, -1 # Internal data structure problem

        day_reservation_count = 0
        donjon_reservation_count = 0

        # --- Check Limits and Availability ---
        for i,day_list in enumerate(self.tableau):
            if name in day_list and i==date_idx:
                day_reservation_count += 1 
            
            for loc in day_list:
                if loc == name and loc == localisation:
                    donjon_reservation_count += 1

            if day_reservation_count >= 2:
                logger.warning(f"Reservation limit reached for user '{name}' (has {day_reservation_count}).")
                return False, 2
            elif donjon_reservation_count >= 2:
                logger.warning(f"Reservation limit reached for user '{name}' (has {donjon_reservation_count}).")
                return False, 2
            
            donjon_reservation_count = 0 # Reset for next day

        # Use list indexing [day][location]
        current_occupant = self.tableau[date_idx][idx]

        if current_occupant != "" and current_occupant != name:
            logger.warning(f"Reservation failed: Slot {actual_localisation} day {date_idx+1} already taken by '{current_occupant}'.")
            return False, 5

        # --- Make Reservation & Save ---
        self.tableau[date_idx][idx] = name
        if self.save_tableau():
            logger.info(f"Reservation successful for '{name}' at {actual_localisation} day {date_idx+1}.")
            return True, 0
        else:
            logger.error("Reservation failed: Could not save tableau after update.")
            # Revert change in memory on save failure
            self.tableau[date_idx][idx] = current_occupant # Revert to original value
            return False, -1

    def cancel (self, localisation: str, name: str, date_str: str) -> tuple[bool, int]:
        """
        Attempts to cancel a reservation. Uses list indexing.
        Error Codes: 0: OK, 1: Invalid date, 2: Invalid location, 3: Slot empty, 4: Not user's booking, -1: System error
        """
        if self.tableau is None or not isinstance(self.tableau, list):
             logger.error("Cancellation failed: Tableau not initialized or not a list.")
             return False, -1

        # --- Validation ---
        loc_lower = localisation.lower()
        try:
            idx = next(i for i, loc in enumerate(self.localisations) if loc.lower() == loc_lower)
            actual_localisation = self.localisations[idx]
        except StopIteration:
             logger.warning(f"Cancellation failed: Invalid location '{localisation}'.")
             return False, 2

        try:
            if not self.tableau: raise ValueError("Tableau is empty")
            num_days = len(self.tableau)
            date_idx = int(date_str) - 1
            if not (0 <= date_idx < num_days): raise ValueError("Date out of bounds")
            if date_idx >= len(self.tableau) or not self.tableau[date_idx]: raise IndexError(f"Day {date_idx} invalid.")
            num_locs_this_day = len(self.tableau[date_idx])
            if idx >= num_locs_this_day: raise IndexError(f"Loc index {idx} invalid for day {date_idx}.")

        except (ValueError, TypeError):
            logger.warning(f"Cancellation failed: Invalid date '{date_str}'.")
            return False, 1
        except IndexError as ie:
             logger.error(f"Cancellation failed: Index error accessing tableau. {ie}")
             return False, -1

        # --- Check Reservation Status ---
        current_reservation = self.tableau[date_idx][idx]
        if current_reservation == "":
            logger.warning(f"Cancellation failed: Slot {actual_localisation} day {date_idx+1} is already empty.")
            return False, 3
        if current_reservation != name:
            logger.warning(f"Cancellation failed: Slot {actual_localisation} day {date_idx+1} reserved by '{current_reservation}', not '{name}'.")
            return False, 4

        # --- Cancel Reservation & Save ---
        self.tableau[date_idx][idx] = ""
        if self.save_tableau():
            logger.info(f"Cancellation successful for '{name}' at {actual_localisation} day {date_idx+1}.")
            return True, 0
        else:
            logger.error("Cancellation failed: Could not save tableau after update.")
            # Revert change in memory
            self.tableau[date_idx][idx] = current_reservation
            return False, -1


    def get_resa (self, localisation: str) -> tuple[bool, list | int]:
        """
        Gets reservations for a specific location.
        Error Codes: 1: Invalid location, -1: System error
        Returns: (True, list_of_tuples) or (False, error_code)
        """
        if self.tableau is None or not isinstance(self.tableau, list): return False, -1

        loc_lower = localisation.lower()
        try:
            idx = next(i for i, loc in enumerate(self.localisations) if loc.lower() == loc_lower)
        except StopIteration:
             return False, 1 # Invalid location

        reservations = []
        try:
            for day_index, day_list in enumerate(self.tableau):
                 # Check if day_list is valid and index is within bounds
                 if isinstance(day_list, list) and idx < len(day_list):
                     name = day_list[idx]
                     if name != "":
                         reservations.append((name, day_index + 1)) # (Name, Day Number)
                 elif isinstance(day_list, list): # Index out of bounds for this specific day
                     logger.warning(f"Inconsistency found: Location index {idx} out of bounds for day {day_index+1} list (len={len(day_list)}).")
                 # else: day_list is not a list, skip or log error?

        except Exception as e:
             logger.exception(f"Error retrieving reservations for location index {idx}: {e}")
             return False, -1

        return True, reservations