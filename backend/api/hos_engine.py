import datetime
import math
import logging

logger = logging.getLogger(__name__)

class HOSSimulator:
    def __init__(self, start_datetime, initial_cycle_used_hours, speed_mph=55.0):
        self.current_time = start_datetime
        self.cycle_used_seconds = initial_cycle_used_hours * 3600.0
        self.speed_mph = speed_mph
        
        self.driving_since_10h_break = 0.0
        self.on_duty_since_10h_break = 0.0
        self.window_start_time = None
        
        self.driving_since_30m_break = 0.0
        self.miles_since_fuel = 0.0
        
        self.activities = []
        self.current_location = "Start"
        self.last_location = "Start"

    def get_on_duty_window_elapsed(self):
        if self.window_start_time is None:
            return 0.0
        return (self.current_time - self.window_start_time).total_seconds()

    def start_on_duty_window_if_needed(self):
        if self.window_start_time is None:
            self.window_start_time = self.current_time
            logger.info(f"[{self.current_time}] Started new 14-hour window.")

    def add_activity(self, duration_seconds, status, description, location):
        """Add a single continuous activity without splitting into 15-min blocks."""
        if duration_seconds <= 0:
            return
            
        start = self.current_time
        end = self.current_time + datetime.timedelta(seconds=duration_seconds)
        
        self.activities.append({
            "start": start,
            "end": end,
            "duration_hours": duration_seconds / 3600.0,
            "status": status,
            "description": description,
            "location": location
        })
        
        self.current_time = end
        self.last_location = location
        
        if status in ["D", "ON"]:
            self.cycle_used_seconds += duration_seconds
            self.start_on_duty_window_if_needed()
            self.on_duty_since_10h_break += duration_seconds
            
            if status == "D":
                self.driving_since_10h_break += duration_seconds
                self.driving_since_30m_break += duration_seconds
                self.miles_since_fuel += (duration_seconds / 3600.0) * self.speed_mph

    def insert_break_10h(self, reason, location):
        logger.info(f"[{self.current_time}] Inserting 10-hour rest break due to {reason} at {location}.")
        self.add_activity(10 * 3600, "OFF", f"10-hour Rest Break ({reason})", location)
        self.driving_since_10h_break = 0.0
        self.on_duty_since_10h_break = 0.0
        self.window_start_time = None
        self.driving_since_30m_break = 0.0

    def insert_restart_34h(self, location):
        logger.info(f"[{self.current_time}] Inserting 34-hour restart at {location}.")
        self.add_activity(34 * 3600, "OFF", "34-hour Cycle Restart Break", location)
        self.driving_since_10h_break = 0.0
        self.on_duty_since_10h_break = 0.0
        self.window_start_time = None
        self.driving_since_30m_break = 0.0
        self.cycle_used_seconds = 0.0

    def insert_break_30m(self, location):
        logger.info(f"[{self.current_time}] Inserting 30-minute break at {location}.")
        self.add_activity(30 * 60, "OFF", "30-minute Rest Break", location)
        self.driving_since_30m_break = 0.0

    def insert_fueling(self, location):
        logger.info(f"[{self.current_time}] Fueling truck at {location}.")
        self.add_activity(15 * 60, "ON", "Fueling Truck", location)
        self.miles_since_fuel = 0.0

    def simulate_driving_leg(self, distance_miles, start_location, end_location):
        """Simulate driving - creates a single continuous driving block when possible."""
        self.current_location = start_location
        
        if distance_miles <= 0:
            return
            
        total_driving_seconds = (distance_miles / self.speed_mph) * 3600.0
        
        logger.info(f"Driving from {start_location} to {end_location}: {distance_miles:.1f} miles, {total_driving_seconds/3600:.2f} hours")
        
        # Track how much we've driven
        remaining_seconds = total_driving_seconds
        current_segment_start = self.current_time
        
        while remaining_seconds > 0:
            # Check 70-hour cycle limit
            if self.cycle_used_seconds + remaining_seconds > 70 * 3600:
                # Can only drive up to the limit
                max_drive = 70 * 3600 - self.cycle_used_seconds
                if max_drive > 0:
                    # Drive as much as possible before hitting the limit
                    drive_time = max_drive
                    self.add_activity(drive_time, "D", 
                                     f"Driving from {start_location} to {end_location}", 
                                     start_location if self.miles_since_fuel < 100 else "En Route")
                    remaining_seconds -= drive_time
                self.insert_restart_34h(self.current_location)
                continue
            
            # Check 11-hour driving limit
            if self.driving_since_10h_break + remaining_seconds > 11 * 3600:
                # Drive until hitting the 11-hour limit
                max_drive = 11 * 3600 - self.driving_since_10h_break
                if max_drive > 0:
                    self.add_activity(max_drive, "D", 
                                     f"Driving from {start_location} to {end_location}",
                                     start_location if self.miles_since_fuel < 100 else "En Route")
                    remaining_seconds -= max_drive
                self.insert_break_10h("11-Hour Driving Limit Reached", "En Route")
                continue
            
            # Check 14-hour window
            if self.window_start_time is not None:
                elapsed_window = self.get_on_duty_window_elapsed()
                if elapsed_window + remaining_seconds > 14 * 3600:
                    max_drive = 14 * 3600 - elapsed_window
                    if max_drive > 0:
                        self.add_activity(max_drive, "D", 
                                         f"Driving from {start_location} to {end_location}",
                                         start_location if self.miles_since_fuel < 100 else "En Route")
                        remaining_seconds -= max_drive
                    self.insert_break_10h("14-Hour Window Limit Reached", "En Route")
                    continue
            
            # Check 30-minute break requirement (8-hour rule)
            if self.driving_since_30m_break + remaining_seconds > 8 * 3600:
                max_drive = 8 * 3600 - self.driving_since_30m_break
                if max_drive > 0:
                    self.add_activity(max_drive, "D", 
                                     f"Driving from {start_location} to {end_location}",
                                     start_location if self.miles_since_fuel < 100 else "En Route")
                    remaining_seconds -= max_drive
                self.insert_break_30m("En Route")
                continue
            
            # Check fueling (every 1,000 miles)
            miles_remaining = (remaining_seconds / 3600.0) * self.speed_mph
            if self.miles_since_fuel + miles_remaining > 1000.0:
                # Drive until we hit 1000 miles
                miles_to_fuel = 1000.0 - self.miles_since_fuel
                drive_to_fuel = (miles_to_fuel / self.speed_mph) * 3600.0
                if drive_to_fuel > 0:
                    self.add_activity(drive_to_fuel, "D", 
                                     f"Driving from {start_location} to {end_location}",
                                     start_location)
                    remaining_seconds -= drive_to_fuel
                self.insert_fueling("En Route")
                continue
            
            # All checks passed - drive the remaining distance
            self.add_activity(remaining_seconds, "D", 
                             f"Driving from {start_location} to {end_location}",
                             end_location)
            remaining_seconds = 0
        
        self.current_location = end_location

    def simulate_on_duty_task(self, duration_hours, description, location):
        """Simulate a single continuous on-duty task."""
        if duration_hours <= 0:
            return
            
        total_seconds = int(duration_hours * 3600.0)
        
        # Check if we need to split due to 70-hour limit
        if self.cycle_used_seconds + total_seconds > 70 * 3600:
            max_on_duty = 70 * 3600 - self.cycle_used_seconds
            if max_on_duty > 0:
                self.add_activity(max_on_duty, "ON", description, location)
            self.insert_restart_34h(location)
            # Recursively handle remaining time
            remaining = total_seconds - max_on_duty
            if remaining > 0:
                self.simulate_on_duty_task(remaining / 3600.0, description, location)
        else:
            self.add_activity(total_seconds, "ON", description, location)


def run_trip_simulation(start_time, initial_cycle_used, speed_mph, 
                        current_name, pickup_name, dropoff_name, 
                        leg1_dist, leg2_dist):
    """Run the full end-to-end trip HOS simulation."""
    sim = HOSSimulator(start_time, initial_cycle_used, speed_mph)
    
    # 1. Pre-trip inspection (15 mins, ON)
    sim.simulate_on_duty_task(0.25, "Pre-trip Inspection", current_name)
    
    # 2. Drive Leg 1 (Current Location to Pickup)
    sim.simulate_driving_leg(leg1_dist, current_name, pickup_name)
    
    # 3. Pickup operations (1 hour loading, ON) - single continuous block
    sim.simulate_on_duty_task(1.0, "Loading Cargo (Pickup)", pickup_name)
    
    # 4. Drive Leg 2 (Pickup to Dropoff)
    sim.simulate_driving_leg(leg2_dist, pickup_name, dropoff_name)
    
    # 5. Dropoff operations (1 hour unloading, ON) - single continuous block
    sim.simulate_on_duty_task(1.0, "Unloading Cargo (Dropoff)", dropoff_name)
    
    # 6. Post-trip inspection (15 mins, ON)
    sim.simulate_on_duty_task(0.25, "Post-trip Inspection", dropoff_name)
    
    return sim.activities


def partition_activities_into_days(activities, start_time):
    """Partition activities into 24-hour calendar days with proper OFF duty filling."""
    if not activities:
        return []
    
    # Prepend OFF duty activity if first activity doesn't start at midnight
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
    current_date = start_time.date()
    day_activities = []
    
    i = 0
    while i < len(activities):
        act = activities[i]
        act_start = act["start"]
        act_end = act["end"]
        
        # If activity starts on a future date, fill the gap with OFF duty
        if act_start.date() > current_date:
            # Fill remaining time with OFF duty
            filled_seconds = sum(a["duration_hours"] * 3600.0 for a in day_activities)
            remaining_seconds = 24 * 3600.0 - filled_seconds
            
            if remaining_seconds > 0:
                last_loc = day_activities[-1]["location"] if day_activities else "Start"
                # Calculate the start time of the OFF activity
                off_start = datetime.datetime.combine(current_date, datetime.time.min) + datetime.timedelta(seconds=filled_seconds)
                off_end = datetime.datetime.combine(current_date, datetime.time.min) + datetime.timedelta(seconds=24*3600)
                off_activity = {
                    "start": off_start,
                    "end": off_end,
                    "duration_hours": remaining_seconds / 3600.0,
                    "status": "OFF",
                    "description": "Off Duty / Rest",
                    "location": last_loc
                }
                day_activities.append(off_activity)
            
            days.append({
                "date": current_date,
                "activities": day_activities
            })
            
            current_date = current_date + datetime.timedelta(days=1)
            day_activities = []
            continue
        
        next_midnight = datetime.datetime.combine(current_date, datetime.time.min) + datetime.timedelta(days=1)
        
        if act_end > next_midnight:
            duration_before = (next_midnight - act_start).total_seconds()
            duration_after = (act_end - next_midnight).total_seconds()
            
            day_activities.append({
                "start": act_start,
                "end": next_midnight,
                "duration_hours": duration_before / 3600.0,
                "status": act["status"],
                "description": act["description"],
                "location": act["location"]
            })
            
            # Check if the day is complete (24 hours)
            filled_seconds = sum(a["duration_hours"] * 3600.0 for a in day_activities)
            if filled_seconds < 24 * 3600:
                # Fill remaining with OFF duty
                remaining = 24 * 3600 - filled_seconds
                last_loc = day_activities[-1]["location"] if day_activities else "Start"
                off_start = datetime.datetime.combine(current_date, datetime.time.min) + datetime.timedelta(seconds=filled_seconds)
                off_activity = {
                    "start": off_start,
                    "end": next_midnight,
                    "duration_hours": remaining / 3600.0,
                    "status": "OFF",
                    "description": "Off Duty / Rest",
                    "location": last_loc
                }
                day_activities.append(off_activity)
            
            days.append({
                "date": current_date,
                "activities": day_activities
            })
            
            current_date = current_date + datetime.timedelta(days=1)
            day_activities = []
            
            new_act = act.copy()
            new_act["start"] = next_midnight
            new_act["end"] = act_end
            new_act["duration_hours"] = duration_after / 3600.0
            activities[i] = new_act
            continue
        
        day_activities.append(act)
        i += 1
    
    # Final day - fill remaining with OFF duty
    if day_activities:
        filled_seconds = sum(a["duration_hours"] * 3600.0 for a in day_activities)
        remaining_seconds = 24 * 3600.0 - filled_seconds
        if remaining_seconds > 0:
            last_loc = day_activities[-1]["location"] if day_activities else "Start"
            last_end = day_activities[-1]["end"] if day_activities else datetime.datetime.combine(current_date, datetime.time.min)
            
            # If last_end is already at midnight, don't add more
            if last_end.time() != datetime.time.min or last_end.date() != current_date + datetime.timedelta(days=1):
                off_activity = {
                    "start": last_end,
                    "end": last_end + datetime.timedelta(seconds=remaining_seconds),
                    "duration_hours": remaining_seconds / 3600.0,
                    "status": "OFF",
                    "description": "Off Duty / Rest",
                    "location": last_loc
                }
                day_activities.append(off_activity)
        
        days.append({
            "date": current_date,
            "activities": day_activities
        })
    
    return days