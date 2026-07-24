import os
import base64
import datetime
import logging
import math
from io import BytesIO
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# Set up logging
logger = logging.getLogger(__name__)

def time_to_hours(dt):
    """Convert datetime object to hours from midnight (0.0 to 24.0)."""
    return dt.hour + dt.minute / 60.0 + dt.second / 3600.0

def _draw_rotated_remark_text(img, anchor_xy, location_text, activity_text, font, fill, angle_deg, line_spacing=2):
    """
    Draw a two-line remark (truck location on top, activity/duty performed on
    the bottom) onto `img`, slanted at angle_deg so it reads along a diagonal
    leader line.

    anchor_xy is the point where the leader line's bend ends. It's treated as
    the RIGHT-MIDDLE of the (two-line) text block and used as the rotation
    pivot, so with a gentle upward-right angle_deg the text always trails
    down-and-to-the-left of anchor_xy — i.e. away from the grid above it,
    regardless of which side of its bucket the leader line approaches from.

    angle_deg follows the same convention as elsewhere in this module: 0
    points right, positive is downward-right, in standard image pixel space
    (atan2(dy, dx) with y growing downward).
    """
    text = f"{location_text}\n{activity_text}"

    dummy = ImageDraw.Draw(Image.new('RGBA', (1, 1)))
    bbox = dummy.multiline_textbbox((0, 0), text, font=font, spacing=line_spacing, align='right')
    tw = max(bbox[2] - bbox[0], 1)
    th = max(bbox[3] - bbox[1], 1)

    # Oversized square canvas, centered on the pivot, so the rotated text
    # never gets clipped regardless of angle.
    half = int(math.hypot(tw, th)) + 8
    canvas = Image.new('RGBA', (half * 2, half * 2), (255, 255, 255, 0))
    cdraw = ImageDraw.Draw(canvas)
    cdraw.multiline_text((half, half), text, font=font, fill=fill, anchor='rm', align='right', spacing=line_spacing)

    # PIL's rotate() is counter-clockwise-positive in pixel space, which is
    # the opposite sense of our atan2(dy, dx) (y grows downward), so negate.
    rotated = canvas.rotate(-angle_deg, resample=Image.BICUBIC, expand=False)
    img.paste(rotated, (int(anchor_xy[0] - half), int(anchor_xy[1] - half)), rotated)

def get_template_path():
    """Find the template image in multiple possible locations."""
    current_dir = Path(__file__).resolve().parent
    
    possible_paths = [
        current_dir / 'templates' / 'blank-paper-log.png',  # api/templates/
        current_dir.parent / 'templates' / 'blank-paper-log.png',  # backend/templates/
        current_dir.parent / 'blank-paper-log.png',         # backend root
        current_dir / 'blank-paper-log.png',                # api folder
        Path('/app/blank-paper-log.png'),                   # Docker container root
        Path('/app/backend/api/templates/blank-paper-log.png'),  # Railway absolute path
    ]
    
    for path in possible_paths:
        if path.exists():
            logger.info(f"Found template at: {path}")
            return path
    
    logger.warning("Template not found in any location")
    return None

def draw_daily_log(day_activities, date_obj, carrier_info, from_loc, to_loc, total_miles, day_index):
    """
    Draw HOS lines, text fields, remarks, and recap table on blank-paper-log.png.
    Returns the image as a base64 encoded PNG string.
    """
    # =========================================================================
    # LOAD TEMPLATE IMAGE
    # =========================================================================
    try:
        template_path = get_template_path()
        
        if template_path and template_path.exists():
            img = Image.open(template_path).convert('RGB')
            logger.info(f"Loaded template from: {template_path}")
        else:
            logger.warning("Template not found, creating blank image")
            img = Image.new('RGB', (513, 518), color='white')
            # Draw a simple border
            draw = ImageDraw.Draw(img)
            draw.rectangle([(0, 0), (512, 517)], outline='black')
            draw.text((150, 10), f"HOS Daily Log - Day {day_index}", fill='black')
            
    except Exception as e:
        logger.error(f"Error loading template: {e}")
        img = Image.new('RGB', (513, 518), color='white')
        
    draw = ImageDraw.Draw(img)
    
    # =========================================================================
    # LOAD FONTS
    # =========================================================================
    fonts = {
        'small': None,
        'normal': None,
        'bold': None
    }
    
    # Try different font files
    font_files = [
        ('arial.ttf', 'arialbd.ttf'),
        ('DejaVuSans.ttf', 'DejaVuSans-Bold.ttf'),
        ('FreeSans.ttf', 'FreeSansBold.ttf'),
    ]
    
    for normal_font, bold_font in font_files:
        try:
            fonts['normal'] = ImageFont.truetype(normal_font, 9)
            fonts['bold'] = ImageFont.truetype(bold_font, 10)
            fonts['small'] = ImageFont.truetype(normal_font, 8)
            break
        except:
            continue
    
    # Fallback to default fonts
    if fonts['normal'] is None:
        try:
            fonts['normal'] = ImageFont.load_default()
            fonts['bold'] = ImageFont.load_default()
            fonts['small'] = ImageFont.load_default()
        except:
            fonts['normal'] = ImageFont.load_default()
            fonts['bold'] = ImageFont.load_default()
            fonts['small'] = ImageFont.load_default()
    
    font_sm = fonts['small']
    font = fonts['normal']
    bold_font = fonts['bold']

    # =========================================================================
    # HEADER TEXT FIELDS
    # =========================================================================
    try:
        # Date
        draw.text((182, 6), date_obj.strftime("%m"), fill='black', font=bold_font)
        draw.text((222, 6), date_obj.strftime("%d"), fill='black', font=bold_font)
        draw.text((262, 6), date_obj.strftime("%Y"), fill='black', font=bold_font)
        
        # From/To - adjusted to fit "Dallas" properly
        draw.text((100, 34), from_loc[:30], fill='black', font=font)  # Moved left
        draw.text((275, 34), to_loc[:30], fill='black', font=font)   # Adjusted
        
        # Total Miles - adjusted for better alignment
        draw.text((65, 75), f"{total_miles:.0f}", fill='black', font=font)
        draw.text((165, 75), f"{total_miles:.0f}", fill='black', font=font)
        
        # Carrier Info
        carrier_name = carrier_info.get("carrier_name", "Spotter Logistics LLC")
        draw.text((305, 65), carrier_name[:30], fill='black', font=font)
        
        main_office = carrier_info.get("main_office", "123 Main St, Dallas, TX")
        draw.text((305, 89), main_office[:30], fill='black', font=font)   # Adjusted
        
        truck_trailer = carrier_info.get("truck_trailer", "Truck #101 / Trailer #202")
        draw.text((65, 105), truck_trailer[:30], fill='black', font=font) # Adjusted
        
        home_terminal = carrier_info.get("home_terminal", "456 Safety Rd, Dallas, TX")
        draw.text((305, 110), home_terminal[:30], fill='black', font=font) # Adjusted
        
    except Exception as e:
        logger.error(f"Error drawing header: {e}")

    # =========================================================================
    # GRID DRAWING — the 24-hour HOS duty status grid
    # =========================================================================
    try:
        # Grid dimensions
        x_grid_left = 65  
        x_grid_right = 456
        grid_width = x_grid_right - x_grid_left
        
        # Y positions for status rows (center of each row)
        y_off_duty = 190
        y_sleeper = 206
        y_driving = 222
        y_on_duty = 245   
        
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

        # Stationary (non-driving) duty periods get a remark bracket + leader
        # line later on. Collected here, alongside the grid line, so both use
        # the exact same x1/x2/y_val coordinates.
        remark_targets = []

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

            # Any period where the truck isn't moving (i.e. not "D") and isn't
            # just generic filler is a "stop" that should get a remark.
            if status != "D" and act.get("description") != "Off Duty / Rest":
                remark_targets.append({"x1": x1, "x2": x2, "y_val": y_val, "act": act})

            # Draw vertical connecting line from previous status
            if prev_x is not None and abs(prev_x - x1) <= 1:
                y_min = min(prev_y, y_val)
                y_max = max(prev_y, y_val)
                draw.line([(x1, y_min), (x1, y_max)], fill='blue', width=2)
                
            prev_x = x2
            prev_y = y_val
    except Exception as e:
        logger.error(f"Error drawing grid: {e}")

    # =========================================================================
    # TOTAL HOURS COLUMN — right side of the grid
    # =========================================================================
    # The "Total Hours" column is at the far right, approximately x=483
    try:
        x_totals = 469
        y_off_duty = 198
        y_sleeper = 212
        y_driving = 230
        y_on_duty = 246
        
        draw.text((x_totals, y_off_duty - 6), f"{totals['OFF']:.1f}", fill='black', font=bold_font)
        draw.text((x_totals, y_sleeper - 6), f"{totals['SB']:.1f}", fill='black', font=bold_font)
        draw.text((x_totals, y_driving - 6), f"{totals['D']:.1f}", fill='black', font=bold_font)
        draw.text((x_totals, y_on_duty - 6), f"{totals['ON']:.1f}", fill='black', font=bold_font)
        
        grand_total = sum(totals.values())
        draw.text((x_totals, 254), f"{grand_total:.1f}", fill='black', font=bold_font)
    except Exception as e:
        logger.error(f"Error drawing totals: {e}")

    # =========================================================================
    # REMARKS SECTION — bucket brackets + drop-then-bend leaders below the grid
    # =========================================================================
    # For every stop (any period the truck isn't moving, other than plain OFF
    # duty filler), draw a bracket ("bucket") that hugs the exact start/end
    # boundaries of that stop on the grid. From the point where the driver's
    # status changed into the stop, a leader line drops straight down, then
    # bends slightly just before the remark itself — the truck's location on
    # top, the activity performed underneath, both slanted to read along that
    # bend.
    try:
        grid_bottom = 256   # common bottom rim every bucket hangs down to
        bucket_gap = 2      # small clearance so ticks don't touch the duty line

        # The bend near the remark: measured from vertical, so a SMALLER value
        # here means the leader stays straighter/more vertical for longer,
        # which keeps back-to-back stops from merging into each other.
        bend_angle_from_vertical_deg = 18
        bend_len = 17
        diag_dx = bend_len * math.sin(math.radians(bend_angle_from_vertical_deg))
        diag_dy = bend_len * math.cos(math.radians(bend_angle_from_vertical_deg))
        text_slant_deg = -25  # fixed, gentle slant so remarks stay legible

        num_lanes = 3
        lane_row_height = 34
        first_row_y = 286
        lane_reach = [-1e9] * num_lanes  # leftmost x each lane's text currently extends to

        def estimate_text_width(s):
            return int(len(s) * 5.2) + 6  # rough px width for font_sm-sized text

        for target in remark_targets:
            x1, y_val, act = target["x1"], target["y_val"], target["act"]

            # --- Bucket: brackets the stop's exact time span on the grid ---
            top_y = y_val + bucket_gap
            draw.line([(x1, top_y), (x1, grid_bottom)], fill='blue', width=1)
            draw.line([(target["x2"], top_y), (target["x2"], grid_bottom)], fill='blue', width=1)
            draw.line([(x1, grid_bottom), (target["x2"], grid_bottom)], fill='blue', width=1)

            # --- Remark content ---
            location_text = act["location"][:22]
            activity_text = act["description"][:22]
            est_width = max(estimate_text_width(location_text), estimate_text_width(activity_text))

            # --- Pick the first lane whose previous remark won't collide ---
            # (a lane is free if its last text doesn't reach as far right as
            # this stop's start)
            lane = next(
                (l for l in range(num_lanes) if lane_reach[l] < x1 - 15),
                min(range(num_lanes), key=lambda l: lane_reach[l]),
            )

            target_y = first_row_y + lane * lane_row_height
            mid_y = target_y - diag_dy
            target_x = x1 - diag_dx
            lane_reach[lane] = target_x - est_width

            # --- Leader line: straight down, then a short 45-degree bend ---
            draw.line([(x1, grid_bottom), (x1, mid_y)], fill='blue', width=1)
            draw.line([(x1, mid_y), (target_x, target_y)], fill='blue', width=1)

            # --- The remark itself: location above, activity below ---
            _draw_rotated_remark_text(
                img, (target_x, target_y), location_text, activity_text,
                font_sm, 'black', text_slant_deg
            )

        # --- Total hours driven today: the last remark, plain text only ---
        # No bucket and no leader line for this one, per spec.
        total_driven_hours = totals.get("D", 0.0)
        draw.text((15, 405), f"{total_driven_hours:.1f}", fill='black', font=font)
    except Exception as e:
        logger.error(f"Error drawing remarks: {e}")

    # =========================================================================
    # RECAP SECTION — bottom of the form
    # =========================================================================
    # "Recap" area is at the very bottom of the form
    try:
        on_duty_today = totals["D"] + totals["ON"]
        recap_a = carrier_info.get("recap_a", on_duty_today)
        recap_b = carrier_info.get("recap_b", max(0.0, 70.0 - recap_a))
        
        # Recap fields - adjusted based on template
        draw.text((80, 440), f"{on_duty_today:.1f}", fill='black', font=font)
        draw.text((157, 440), f"{recap_a:.1f}", fill='black', font=font)
        draw.text((206, 440), f"{recap_b:.1f}", fill='black', font=font)
        
    except Exception as e:
        logger.error(f"Error drawing recap: {e}")

    # =========================================================================
    # ENCODE TO BASE64
    # =========================================================================
    try:
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        img_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
        
        return f"data:image/png;base64,{img_b64}"
    except Exception as e:
        logger.error(f"Error encoding image: {e}")
        return ""
