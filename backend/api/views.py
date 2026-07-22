import datetime
import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.utils.dateparse import parse_datetime

from .routing_helper import geocode_location, get_route_details
from .hos_engine import run_trip_simulation, partition_activities_into_days
from .log_drawer import draw_daily_log

def api_root(request):
    return JsonResponse({
        "message": "API is working!",
        "endpoints": {
            "route_planner": "/api/route",
        }
    })

import logging
logger = logging.getLogger(__name__)

@csrf_exempt
@require_POST
def route_planner(request):
    """
    Endpoint: POST /api/route
    Takes trip locations, current cycle used, speed, and carrier information.
    Validates inputs, plans route, simulates HOS, draws daily logs, and returns results.
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({
            "success": False,
            "error": "Invalid JSON in request body."
        }, status=400)

    # --- Input Validation ---
    current_loc = data.get("current_location", "").strip()
    pickup_loc = data.get("pickup_location", "").strip()
    dropoff_loc = data.get("dropoff_location", "").strip()

    if not current_loc or not pickup_loc or not dropoff_loc:
        return JsonResponse({
            "success": False,
            "error": "Current location, pickup location, and dropoff location are all required fields."
        }, status=400)

    # Cycle Used hours validation
    try:
        cycle_used = float(data.get("cycle_used", 0.0))
        if cycle_used < 0.0 or cycle_used > 70.0:
            return JsonResponse({
                "success": False,
                "error": "Current cycle used must be between 0 and 70 hours."
            }, status=400)
    except (ValueError, TypeError):
        return JsonResponse({
            "success": False,
            "error": "Current cycle used must be a numeric value."
        }, status=400)

    # Speed validation
    try:
        speed_mph = float(data.get("speed_mph", 55.0))
        if speed_mph < 20.0 or speed_mph > 85.0:
            return JsonResponse({
                "success": False,
                "error": "Average speed must be between 20 and 85 mph."
            }, status=400)
    except (ValueError, TypeError):
        return JsonResponse({
            "success": False,
            "error": "Average speed must be a numeric value."
        }, status=400)

    # Start Time validation
    start_time_str = data.get("start_time")
    if start_time_str:
        start_time = parse_datetime(start_time_str)
        if not start_time:
            return JsonResponse({
                "success": False,
                "error": "Invalid start time format. Use ISO format (YYYY-MM-DDTHH:MM)."
            }, status=400)
    else:
        # Default to 08:00 AM on the current date
        today = datetime.date.today()
        start_time = datetime.datetime.combine(today, datetime.time(8, 0))

    # Carrier Details (optional with defaults)
    carrier_info = {
        "carrier_name": data.get("carrier_name", "").strip() or "Spotter Logistics LLC",
        "main_office": data.get("main_office", "").strip() or "123 Main St, Dallas, TX",
        "home_terminal": data.get("home_terminal", "").strip() or "456 Safety Rd, Dallas, TX",
        "truck_trailer": data.get("truck_trailer", "").strip() or "Truck #101 / Trailer #202"
    }

    # --- Geocoding & Routing ---
    try:
        lat_curr, lon_curr, display_curr = geocode_location(current_loc)
        lat_pick, lon_pick, display_pick = geocode_location(pickup_loc)
        lat_drop, lon_drop, display_drop = geocode_location(dropoff_loc)
    except Exception as e:
        logger.exception("Geocoding failed")
        return JsonResponse({
            "success": False,
            "error": f"Geocoding failed: {str(e)}"
        }, status=500)

    try:
        # Leg 1: Current to Pickup
        leg1 = get_route_details(lat_curr, lon_curr, lat_pick, lon_pick, speed_mph)
        # Leg 2: Pickup to Dropoff
        leg2 = get_route_details(lat_pick, lon_pick, lat_drop, lon_drop, speed_mph)
    except Exception as e:
        logger.exception("Routing failed")
        return JsonResponse({
            "success": False,
            "error": f"Route planning failed: {str(e)}"
        }, status=500)

    # --- HOS Simulation ---
    try:
        # Run HOS Simulation
        activities = run_trip_simulation(
            start_time=start_time,
            initial_cycle_used=cycle_used,
            speed_mph=speed_mph,
            current_name=display_curr,
            pickup_name=display_pick,
            dropoff_name=display_drop,
            leg1_dist=leg1["distance_miles"],
            leg2_dist=leg2["distance_miles"]
        )
        
        # Partition activities into 24h days
        day_partitions = partition_activities_into_days(activities, start_time)
    except Exception as e:
        logger.exception("HOS Simulation failed")
        return JsonResponse({
            "success": False,
            "error": f"HOS Simulation failed: {str(e)}"
        }, status=500)

    # --- Rolling Recap Calculations & Log Sheet Drawing ---
    # Setup initial 7-day history for the rolling HOS recap.
    # We distribute the initial cycle_used hours evenly over the preceding 7 days.
    daily_history = [cycle_used / 7.0] * 7
    
    days_response = []
    
    for idx, day in enumerate(day_partitions):
        day_date = day["date"]
        day_activities = day["activities"]
        
        # Calculate daily status totals
        totals = {"OFF": 0.0, "SB": 0.0, "D": 0.0, "ON": 0.0}
        for act in day_activities:
            # Clamp duration to day boundaries if needed, already done in partition
            totals[act["status"]] += act["duration_hours"]

        # Calculate daily distance
        miles_driven = totals["D"] * speed_mph
        
        # Determine from/to location for the day
        from_loc_day = day_activities[0]["location"] if day_activities else display_curr
        to_loc_day = day_activities[-1]["location"] if day_activities else display_curr
        
        # On duty hours today
        on_duty_today = totals["D"] + totals["ON"]
        
        # Add to history and calculate rolling recap
        # Recap A: Total on duty hours last 7 days including today
        # Recap B: Available tomorrow (70 - A)
        daily_history.append(on_duty_today)
        # Sum last 7 elements of daily_history (which includes today)
        recap_a = sum(daily_history[-7:])
        recap_b = max(0.0, 70.0 - recap_a)
        
        carrier_info["recap_a"] = recap_a
        carrier_info["recap_b"] = recap_b
        
        # Draw the log sheet PNG
        try:
            image_b64 = draw_daily_log(
                day_activities=day_activities,
                date_obj=day_date,
                carrier_info=carrier_info,
                from_loc=from_loc_day,
                to_loc=to_loc_day,
                total_miles=miles_driven,
                day_index=idx + 1
            )
        except Exception as e:
            logger.exception(f"Drawing log sheet failed for day {idx+1}")
            image_b64 = ""

        # Format activities for UI timeline
        formatted_activities = []
        for act in day_activities:
            formatted_activities.append({
                "start": act["start"].strftime("%I:%M %p"),
                "end": act["end"].strftime("%I:%M %p"),
                "duration": f"{act['duration_hours']:.2f} hrs",
                "status": act["status"],
                "description": act["description"],
                "location": act["location"]
            })

        days_response.append({
            "day_index": idx + 1,
            "date": day_date.strftime("%Y-%m-%d"),
            "totals": {
                "off_duty": round(totals["OFF"], 2),
                "sleeper": round(totals["SB"], 2),
                "driving": round(totals["D"], 2),
                "on_duty": round(totals["ON"], 2),
            },
            "miles_driven": round(miles_driven, 1),
            "from_location": from_loc_day,
            "to_location": to_loc_day,
            "recap": {
                "hours_on_duty_today": round(on_duty_today, 2),
                "on_duty_last_7_days": round(recap_a, 2),
                "available_tomorrow": round(recap_b, 2),
            },
            "remarks": [
                f"{act['start'].strftime('%I:%M %p')} - {act['description']} ({act['location']})"
                for act in day_activities if act["description"] != "Off Duty / Rest"
            ],
            "activities": formatted_activities,
            "image_b64": image_b64
        })

    # Prepare complete global trip timeline
    global_timeline = []
    for act in activities:
        # Determine status colors for UI
        color = "#ef4444" # red
        if act["status"] == "OFF":
            color = "#10b981" # green
        elif act["status"] == "SB":
            color = "#3b82f6" # blue
        elif act["status"] == "D":
            color = "#f59e0b" # amber
        elif act["status"] == "ON":
            color = "#8b5cf6" # purple
            
        global_timeline.append({
            "date": act["start"].strftime("%a, %b %d"),
            "start": act["start"].strftime("%I:%M %p"),
            "end": act["end"].strftime("%I:%M %p"),
            "duration": f"{act['duration_hours']:.2f} hrs",
            "status": act["status"],
            "description": act["description"],
            "location": act["location"],
            "color": color
        })

    return JsonResponse({
        "success": True,
        "route": {
            "leg1": {
                "from": display_curr,
                "to": display_pick,
                "distance_miles": round(leg1["distance_miles"], 1),
                "driving_time_hours": round(leg1["driving_time_hours"], 2),
                "path": leg1["route_path"]
            },
            "leg2": {
                "from": display_pick,
                "to": display_drop,
                "distance_miles": round(leg2["distance_miles"], 1),
                "driving_time_hours": round(leg2["driving_time_hours"], 2),
                "path": leg2["route_path"]
            },
            "total_distance_miles": round(leg1["distance_miles"] + leg2["distance_miles"], 1),
            "total_driving_time_hours": round(leg1["driving_time_hours"] + leg2["driving_time_hours"], 2)
        },
        "days": days_response,
        "timeline": global_timeline
    })
