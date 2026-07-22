import os
import base64
import datetime
from io import BytesIO
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

def time_to_hours(dt):
    """Convert datetime object to hours from midnight (0.0 to 24.0)."""
    return dt.hour + dt.minute / 60.0 + dt.second / 3600.0

def draw_daily_log(day_activities, date_obj, carrier_info, from_loc, to_loc, total_miles, day_index):
    """
    Draw HOS lines, text fields, remarks, and recap table on blank-paper-log.png.
    Returns the image as a base64 encoded PNG string.
    """
    # =========================================================================
    # LOAD TEMPLATE IMAGE
    # =========================================================================
    try:
        # Get the directory where this file is located
        current_dir = Path(__file__).resolve().parent
        
        # Look for template in multiple locations
        possible_paths = [
            current_dir / 'templates' / 'blank-paper-log.png',  # api/templates/
            current_dir.parent / 'blank-paper-log.png',         # backend root
            current_dir / 'blank-paper-log.png',                # api folder
            Path('blank-paper-log.png'),                        # current working directory
        ]
        
        template_path = None
        for path in possible_paths:
            if path.exists():
                template_path = path
                break
        
        if template_path:
            img = Image.open(template_path).convert('RGB')
            print(f"Loaded template from: {template_path}")
        else:
            print("Template not found, creating blank image")
            img = Image.new('RGB', (513, 518), color='white')
            
    except Exception as e:
        print(f"Error loading template: {e}")
        img = Image.new('RGB', (513, 518), color='white')
        
    draw = ImageDraw.Draw(img)
    
    # Load fonts
    try:
        font_sm = ImageFont.truetype("arial.ttf", 8)
        font = ImageFont.truetype("arial.ttf", 9)
        bold_font = ImageFont.truetype("arialbd.ttf", 10)
    except Exception:
        try:
            font_sm = ImageFont.truetype("arial.ttf", 8)
            font = ImageFont.truetype("arial.ttf", 9)
            bold_font = ImageFont.truetype("arial.ttf", 10)
        except Exception:
            font_sm = ImageFont.load_default()
            font = ImageFont.load_default()
            bold_font = ImageFont.load_default()

    # =========================================================================
    # HEADER TEXT FIELDS — calibrated to the blank-paper-log.png (513x518)
    # =========================================================================
    
    # Date: (month) / (day) / (year) — positioned on the line after "Drivers Daily Log"
    # The underscores for month/day/year are at roughly x=195, x=225, x=260 at y~18
    draw.text((198, 12), date_obj.strftime("%m"), fill='black', font=bold_font)
    draw.text((232, 12), date_obj.strftime("%d"), fill='black', font=bold_font)
    draw.text((260, 12), date_obj.strftime("%Y"), fill='black', font=bold_font)
    
    # From: field — the line is at y~44, text area starts at x~60
    draw.text((60, 44), from_loc[:35], fill='black', font=font)
    
    # To: field — at y~44, text area starts at x~280
    draw.text((280, 44), to_loc[:35], fill='black', font=font)

    # Total Miles Driving Today — box at approximately x=30, y=82
    draw.text((35, 82), f"{total_miles:.0f}", fill='black', font=font)
    
    # Total Mileage Today — box at approximately x=110, y=82
    draw.text((115, 82), f"{total_miles:.0f}", fill='black', font=font)

    # Name of Carrier or Carriers — at approximately x=305, y=72
    carrier_name = carrier_info.get("carrier_name", "Spotter Logistics LLC")
    draw.text((305, 72), carrier_name[:30], fill='black', font=font)

    # Main Office Address — at approximately x=305, y=92
    main_office = carrier_info.get("main_office", "123 Main St, Dallas, TX")
    draw.text((305, 92), main_office[:30], fill='black', font=font)

    # Truck/Tractor and Trailer Numbers — at approximately x=35, y=118
    truck_trailer = carrier_info.get("truck_trailer", "Truck #101 / Trailer #202")
    draw.text((35, 118), truck_trailer[:30], fill='black', font=font)

    # Home Terminal Address — at approximately x=305, y=112
    home_terminal = carrier_info.get("home_terminal", "456 Safety Rd, Dallas, TX")
    draw.text((305, 112), home_terminal[:30], fill='black', font=font)

    # =========================================================================
    # GRID DRAWING — the 24-hour HOS duty status grid
    # =========================================================================
    # Based on pixel analysis of blank-paper-log.png (513x518):
    # The grid area runs from the "Midnight" left label to "Midnight" right label
    # X: left edge ~x=60, right edge ~x=472  (before "Total Hours" column)
    # The grid has 24 columns (one per hour)
    
    x_grid_left = 60
    x_grid_right = 472
    grid_width = x_grid_right - x_grid_left

    # Y positions for the CENTER of each status row:
    # 1. Off Duty:      y ~ 192
    # 2. Sleeper Berth:  y ~ 208
    # 3. Driving:        y ~ 224
    # 4. On Duty:        y ~ 240
    y_off_duty = 192
    y_sleeper = 208
    y_driving = 224
    y_on_duty = 240

    status_y_map = {
        "OFF": y_off_duty,
        "SB": y_sleeper,
        "D": y_driving,
        "ON": y_on_duty
    }

    def hr_to_x(hr):
        """Convert hour (0-24) to pixel X coordinate on the grid."""
        return int(x_grid_left + (hr / 24.0) * grid_width)

    # Use pre-computed duration_hours from activities for accurate totals
    totals = {"OFF": 0.0, "SB": 0.0, "D": 0.0, "ON": 0.0}

    # Sort activities by start time
    day_activities = sorted(day_activities, key=lambda a: a["start"])

    prev_x = None
    prev_y = None

    for act in day_activities:
        status = act["status"]
        y_val = status_y_map.get(status, y_off_duty)
        
        # Use duration_hours for totals (avoids midnight wraparound bugs)
        totals[status] += act.get("duration_hours", 0.0)
        
        # Calculate pixel positions from time
        start_hr = time_to_hours(act["start"])
        
        # For end time: if end is midnight (00:00), treat as 24.0
        end_dt = act["end"]
        if end_dt.hour == 0 and end_dt.minute == 0 and end_dt.second == 0:
            # Check if end is the start of the next day (midnight)
            if end_dt.date() > act["start"].date():
                end_hr = 24.0
            else:
                end_hr = 0.0
        else:
            end_hr = time_to_hours(end_dt)
        
        # If end_hr < start_hr, the activity wraps midnight — cap at 24
        if end_hr < start_hr:
            end_hr = 24.0
        
        start_hr = max(0.0, min(24.0, start_hr))
        end_hr = max(0.0, min(24.0, end_hr))
        
        x1 = hr_to_x(start_hr)
        x2 = hr_to_x(end_hr)
        
        # Don't draw zero-width segments
        if x1 == x2:
            prev_x = x2
            prev_y = y_val
            continue
        
        # Draw horizontal line for this duty status
        draw.line([(x1, y_val), (x2, y_val)], fill='blue', width=2)
        
        # Draw vertical connecting line from previous status
        if prev_x is not None and abs(prev_x - x1) <= 1:
            y_min = min(prev_y, y_val)
            y_max = max(prev_y, y_val)
            draw.line([(x1, y_min), (x1, y_max)], fill='blue', width=2)
            
        prev_x = x2
        prev_y = y_val

    # =========================================================================
    # TOTAL HOURS COLUMN — right side of the grid
    # =========================================================================
    # The "Total Hours" column is at the far right, approximately x=483
    x_totals = 483
    draw.text((x_totals, 186), f"{totals['OFF']:.1f}", fill='black', font=bold_font)
    draw.text((x_totals, 202), f"{totals['SB']:.1f}", fill='black', font=bold_font)
    draw.text((x_totals, 218), f"{totals['D']:.1f}", fill='black', font=bold_font)
    draw.text((x_totals, 234), f"{totals['ON']:.1f}", fill='black', font=bold_font)

    # Total of all hours (should be 24.0)
    grand_total = sum(totals.values())
    draw.text((x_totals, 250), f"{grand_total:.1f}", fill='black', font=bold_font)

    # =========================================================================
    # REMARKS SECTION — below the grid
    # =========================================================================
    # "Remarks" section starts around y=263. We'll draw our remarks below y=275
    y_remark = 280
    
    # Filter to show only meaningful status changes (not filler off-duty)
    remark_lines = []
    for act in day_activities:
        desc = act["description"]
        if desc == "Off Duty / Rest":
            continue
        start_str = act["start"].strftime("%I:%M %p")
        loc = act["location"]
        remark_lines.append(f"{start_str} - {desc} ({loc})")

    # Draw remarks in two columns to fit the space
    col_x = 18
    for idx, remark in enumerate(remark_lines[:14]):
        if idx == 7:
            col_x = 265
            y_remark = 280
        draw.text((col_x, y_remark), remark[:42], fill='black', font=font_sm)
        y_remark += 10

    # =========================================================================
    # RECAP SECTION — bottom of the form
    # =========================================================================
    # "Recap" area is at the very bottom of the form
    on_duty_today = totals["D"] + totals["ON"]
    
    # On duty hours today
    draw.text((85, 442), f"{on_duty_today:.1f}", fill='black', font=font)
    
    # Recap A: total on duty last 7 days
    recap_a = carrier_info.get("recap_a", on_duty_today)
    draw.text((155, 442), f"{recap_a:.1f}", fill='black', font=font)
    
    # Recap B: hours available tomorrow (70 - A)
    recap_b = carrier_info.get("recap_b", max(0.0, 70.0 - recap_a))
    draw.text((215, 442), f"{recap_b:.1f}", fill='black', font=font)

    # =========================================================================
    # ENCODE TO BASE64
    # =========================================================================
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    img_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
    
    return f"data:image/png;base64,{img_b64}"
