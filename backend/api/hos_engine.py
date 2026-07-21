import datetime
import math
import logging

logger = logging.getLogger(__name__)

class HOSSimulator:
    def __init__(self, start_datetime, initial_cycle_used_hours, speed_mph=55.0):
        self.current_time = start_datetime
        # Initial status variables
        self.cycle_used_seconds = initial_cycle_used_hours * 3600.0
        self.speed_mph = speed_mph
        
        # State tracking since last 10-hour break
        self.driving_since_10h_break = 0.0      # in seconds
        self.on_duty_since_10h_break = 0.0       # in seconds (driving + on duty not driving)
        self.window_start_time = None            # datetime when current 14h window started
        
        # State tracking for 30-minute break
        self.driving_since_30m_break = 0.0       # in seconds
        
        # Fueling tracking
        self.miles_since_fuel = 0.0
        
        # Output activities
        # Each activity: {"start": datetime, "end": datetime, "status": str, "desc": str, "location": str}
        self.activities = []
        
        # Current location name (gets updated as we progress)
        self.current_location = "Start"

    def get_on_duty_window_elapsed(self):
        """Returns the elapsed seconds in the current 14-hour window."""
        if self.window_start_time is None:
            return 0.0
        return (self.current_time - self.window_start_time).total_seconds()

    def start_on_duty_window_if_needed(self):
        """Starts the 14-hour window if not already active."""
        if self.window_start_time is None:
            self.window_start_time = self.current_time
            logger.info(f"[{self.current_time}] Started new 14-hour window.")

    def add_activity(self, duration_seconds, status, description, location):
        """
        Record an activity. If the activity spans across multiple statuses,
        it should be split beforehand. This method appends to self.activities,
        handling time updates and cycle tracking.
        """
        start = self.current_time
        end = self.current_time + datetime.timedelta(seconds=duration_seconds)
        
        # Add activity record
        self.activities.append({
            "start": start,
            "end": end,
            "duration_hours": duration_seconds / 3600.0,
            "status": status,
            "description": description,
            "location": location
        })
        
        # Update time
        self.current_time = end
        
        # Update HOS accumulators
        if status in ["D", "ON"]:
            self.cycle_used_seconds += duration_seconds
            self.start_on_duty_window_if_needed()
            self.on_duty_since_10h_break += duration_seconds
            
            if status == "D":
                self.driving_since_10h_break += duration_seconds
                self.driving_since_30m_break += duration_seconds
                self.miles_since_fuel += (duration_seconds / 3600.0) * self.speed_mph
        
        elif status in ["OFF", "SB"]:
            # If off-duty or sleeper, we do not accumulate cycle hours.
            # We don't update driving/on-duty accumulators here.
            # However, if this break is at least 30 consecutive minutes (1800s),
            # it resets the 30-minute break driving timer.
            pass

    def insert_break_10h(self, reason, location):
        """Insert a 10-hour consecutive off-duty break."""
        logger.info(f"[{self.current_time}] Inserting 10-hour rest break due to {reason} at {location}.")
        self.add_activity(10 * 3600, "OFF", f"10-hour Rest Break ({reason})", location)
        # Reset HOS window and limits
        self.driving_since_10h_break = 0.0
        self.on_duty_since_10h_break = 0.0
        self.window_start_time = None
        self.driving_since_30m_break = 0.0

    def insert_restart_34h(self, location):
        """Insert a 34-hour cycle restart break."""
        logger.info(f"[{self.current_time}] Inserting 34-hour restart at {location}.")
        self.add_activity(34 * 3600, "OFF", "34-hour Cycle Restart Break", location)
        # Reset all limits and cycle hours
        self.driving_since_10h_break = 0.0
        self.on_duty_since_10h_break = 0.0
        self.window_start_time = None
        self.driving_since_30m_break = 0.0
        self.cycle_used_seconds = 0.0

    def insert_break_30m(self, location):
        """Insert a 30-minute rest break."""
        logger.info(f"[{self.current_time}] Inserting 30-minute break at {location}.")
        self.add_activity(30 * 60, "OFF", "30-minute Rest Break", location)
        self.driving_since_30m_break = 0.0

    def insert_fueling(self, location):
        """Insert a 15-minute fueling activity."""
        logger.info(f"[{self.current_time}] Fueling truck at {location}.")
        self.add_activity(15 * 60, "ON", "Fueling Truck", location)
        self.miles_since_fuel = 0.0

    def simulate_driving_leg(self, distance_miles, start_location, end_location):
        """
        Simulate driving a specific distance between two locations.
        Calculates driving blocks and inserts HOS breaks as required.
        """
        self.current_location = start_location
        # Total driving seconds needed
        total_driving_seconds = (distance_miles / self.speed_mph) * 3600.0
        
        # Round driving seconds to the nearest 15-minute block (900 seconds)
        # to ensure alignment on the log grid, but must drive at least 15 mins if distance > 0
        if distance_miles > 0:
            blocks = max(1, int(round(total_driving_seconds / 900.0)))
        else:
            blocks = 0
            
        logger.info(f"Driving from {start_location} to {end_location}: {distance_miles:.1f} miles, requires {blocks} blocks of 15-mins.")
        
        block_duration = 900 # 15 minutes in seconds
        miles_per_block = (block_duration / 3600.0) * self.speed_mph
        
        blocks_driven = 0
        while blocks_driven < blocks:
            # 1. Check 70-hour / 8-day cycle limit
            # If we are close to 70 hours (e.g. within 15 minutes), trigger a 34-hour restart
            if self.cycle_used_seconds + block_duration > 70 * 3600:
                self.insert_restart_34h(self.current_location)
                continue
                
            # 2. Check 14-hour window
            # If our 14-hour window is active, check how much time is left.
            # The 14-hour window is consecutive, so it includes breaks.
            # If taking this 15-minute drive block exceeds the 14-hour limit:
            if self.window_start_time is not None:
                elapsed_window = self.get_on_duty_window_elapsed()
                if elapsed_window + block_duration > 14 * 3600:
                    self.insert_break_10h("14-Hour Window Limit Reached", self.current_location)
                    continue

            # 3. Check 11-hour driving limit
            if self.driving_since_10h_break + block_duration > 11 * 3600:
                self.insert_break_10h("11-Hour Driving Limit Reached", self.current_location)
                continue

            # 4. Check 8-hour driving since break rule (30-minute break required)
            if self.driving_since_30m_break + block_duration > 8 * 3600:
                self.insert_break_30m(self.current_location)
                continue

            # 5. Check Fueling Limit (every 1,000 miles)
            # If driving the next block would cross the 1,000-mile mark, fuel first
            if self.miles_since_fuel + miles_per_block > 1000.0:
                self.insert_fueling(self.current_location)
                continue

            # All checks passed! Perform 15-min driving block
            desc = f"Driving from {start_location} to {end_location}"
            self.add_activity(block_duration, "D", desc, self.current_location)
            blocks_driven += 1

        self.current_location = end_location

    def simulate_on_duty_task(self, duration_hours, description, location):
        """
        Simulate an on-duty non-driving task like loading, unloading, or inspections.
        Inserts cycle restarts if we hit the 70-hour limit.
        """
        self.current_location = location
        total_seconds = int(round(duration_hours * 3600.0))
        block_duration = 900 # 15 minutes
        
        seconds_completed = 0
        while seconds_completed < total_seconds:
            # Check 70-hour cycle limit
            if self.cycle_used_seconds + block_duration > 70 * 3600:
                self.insert_restart_34h(self.current_location)
                continue
            
            # Note: We can complete on-duty tasks past the 14-hour window, 
            # but we cannot drive afterwards. So we just perform the task.
            # We will start the window if it wasn't active.
            self.add_activity(block_duration, "ON", description, self.current_location)
            seconds_completed += block_duration

def run_trip_simulation(start_time, initial_cycle_used, speed_mph, 
                        current_name, pickup_name, dropoff_name, 
                        leg1_dist, leg2_dist):
    """
    Run the full end-to-end trip HOS simulation.
    """
    # Initialize simulator
    sim = HOSSimulator(start_time, initial_cycle_used, speed_mph)
    
    # 1. Pre-trip inspection (15 mins, ON)
    sim.simulate_on_duty_task(0.25, "Pre-trip Inspection", current_name)
    
    # 2. Drive Leg 1 (Current Location to Pickup)
    sim.simulate_driving_leg(leg1_dist, current_name, pickup_name)
    
    # 3. Pickup operations (1 hour loading, ON)
    sim.simulate_on_duty_task(1.0, "Loading Cargo (Pickup)", pickup_name)
    
    # 4. Drive Leg 2 (Pickup to Dropoff)
    sim.simulate_driving_leg(leg2_dist, pickup_name, dropoff_name)
    
    # 5. Dropoff operations (1 hour unloading, ON)
    sim.simulate_on_duty_task(1.0, "Unloading Cargo (Dropoff)", dropoff_name)
    
    # 6. Post-trip inspection (15 mins, ON)
    sim.simulate_on_duty_task(0.25, "Post-trip Inspection", dropoff_name)
    
    # Fill remaining time of the final day with OFF-duty time
    # so that the final day has a complete timeline.
    # Actually, we partition into daily logs in a separate function.
    return sim.activities

def partition_activities_into_days(activities, start_time):
    """
    Partition the linear list of activities into 24-hour calendar days (00:00 to 24:00).
    Splits any activity that crosses a midnight boundary.
    Returns a list of days, where each day contains a list of activities.
    """
    if not activities:
        return []
        
    # Prepend OFF duty activity if the first activity doesn't start at midnight of its day
    first_act_start = activities[0]["start"]
    first_day_midnight = datetime.datetime.combine(first_act_start.date(), datetime.time.min)
    if first_act_start > first_day_midnight:
        gap_duration = (first_act_start - first_day_midnight).total_seconds()
        off_activity = {
            "start": first_day_midnight,
            "end": first_act_start,
            "duration_hours": gap_duration / 3600.0,
            "status": "OFF",
            "description": "Off Duty / Rest",
            "location": activities[0]["location"]
        }
        activities.insert(0, off_activity)
        
    days = []
    
    # Let's group activities by date.
    # Since activities are sequential, we can scan and split.
    current_date = start_time.date()
    day_activities = []
    
    i = 0
    while i < len(activities):
        act = activities[i]
        act_start = act["start"]
        act_end = act["end"]
        
        # Check if the activity starts on a different date than current_date.
        # If it starts on a later date, it means we have a gap of off-duty time.
        # Let's fill the gap up to midnight of current_date, and then transition.
        if act_start.date() > current_date:
            # Fill the rest of current_date with OFF duty
            midnight = datetime.datetime.combine(current_date, datetime.time.max)
            # Add a small fraction to reach exactly midnight (00:00 of next day)
            midnight = midnight + datetime.timedelta(microseconds=999999)
            
            gap_seconds = (midnight - datetime.datetime.combine(current_date, datetime.time.min)).total_seconds()
            # Calculate how much is already filled in day_activities
            filled_seconds = sum(a["duration_hours"] * 3600.0 for a in day_activities)
            remaining_seconds = 24 * 3600.0 - filled_seconds
            
            if remaining_seconds > 0:
                day_activities.append({
                    "start": datetime.datetime.combine(current_date, datetime.time.min) + datetime.timedelta(seconds=filled_seconds),
                    "end": datetime.datetime.combine(current_date, datetime.time.min) + datetime.timedelta(seconds=24*3600),
                    "duration_hours": remaining_seconds / 3600.0,
                    "status": "OFF",
                    "description": "Off Duty / Rest",
                    "location": day_activities[-1]["location"] if day_activities else "Start"
                })
            
            days.append({
                "date": current_date,
                "activities": day_activities
            })
            
            # Move to next date
            current_date = current_date + datetime.timedelta(days=1)
            day_activities = []
            continue
            
        # Check if activity crosses midnight of the current date
        next_midnight = datetime.datetime.combine(current_date, datetime.time.min) + datetime.timedelta(days=1)
        
        if act_end > next_midnight:
            # Split the activity at midnight
            duration_before_midnight = (next_midnight - act_start).total_seconds()
            duration_after_midnight = (act_end - next_midnight).total_seconds()
            
            # Activity before midnight
            day_activities.append({
                "start": act_start,
                "end": next_midnight,
                "duration_hours": duration_before_midnight / 3600.0,
                "status": act["status"],
                "description": act["description"],
                "location": act["location"]
            })
            
            days.append({
                "date": current_date,
                "activities": day_activities
            })
            
            # Set up next day
            current_date = current_date + datetime.timedelta(days=1)
            day_activities = []
            
            # The remaining part of the activity goes into the next iteration
            # We modify the start of the activity to be the midnight and queue it
            new_act = act.copy()
            new_act["start"] = next_midnight
            new_act["end"] = act_end
            new_act["duration_hours"] = duration_after_midnight / 3600.0
            
            activities[i] = new_act # Replace and rerun for this index
            continue
            
        else:
            # Fits in the current day
            day_activities.append(act)
            i += 1
            
    # Handle the final day: fill remaining hours with OFF duty
    if day_activities:
        filled_seconds = sum(a["duration_hours"] * 3600.0 for a in day_activities)
        remaining_seconds = 24 * 3600.0 - filled_seconds
        if remaining_seconds > 0:
            last_location = day_activities[-1]["location"] if day_activities else "Start"
            day_activities.append({
                "start": day_activities[-1]["end"],
                "end": day_activities[-1]["end"] + datetime.timedelta(seconds=remaining_seconds),
                "duration_hours": remaining_seconds / 3600.0,
                "status": "OFF",
                "description": "Off Duty / Rest",
                "location": last_location
            })
        days.append({
            "date": current_date,
            "activities": day_activities
        })
        
    return days
