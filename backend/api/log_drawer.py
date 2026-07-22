import os
import base64
import datetime
import logging
from io import BytesIO
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# Set up logging
logger = logging.getLogger(__name__)

def time_to_hours(dt):
    """Convert datetime object to hours from midnight (0.0 to 24.0)."""
    return dt.hour + dt.minute / 60.0 + dt.second / 3600.0

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
    # HEADER TEXT FIELDS — calibrated to the blank-paper-log.png (513x518)
    # =========================================================================
    try:
        # Date
        draw.text((168, 0), date_obj.strftime("%m"), fill='black', font=bold_font)
        draw.text((202, 0), date_obj.strftime("%d"), fill='black', font=bold_font)
        draw.text((230, 0), date_obj.strftime("%Y"), fill='black', font=bold_font)
        
        # From/To - adjusted to fit "Dallas" properly
        draw.text((100, 24), from_loc[:30], fill='black', font=font)  # Moved left
        draw.text((275, 24), to_loc[:30], fill='black', font=font)   # Adjusted
        
        # Total Miles - adjusted for better alignment
        draw.text((65, 75), f"{total_miles:.0f}", fill='black', font=font)
        draw.text((145, 75), f"{total_miles:.0f}", fill='black', font=font)
        
        # Carrier Info
        carrier_name = carrier_info.get("carrier_name", "Spotter Logistics LLC")
        draw.text((305, 65), carrier_name[:30], fill='black', font=font)  # Moved up
        
        main_office = carrier_info.get("main_office", "123 Main St, Dallas, TX")
        draw.text((305, 89), main_office[:30], fill='black', font=font)   # Adjusted
        
        truck_trailer = carrier_info.get("truck_trailer", "Truck #101 / Trailer #202")
        draw.text((65, 100), truck_trailer[:30], fill='black', font=font) # Adjusted
        
        home_terminal = carrier_info.get("home_terminal", "456 Safety Rd, Dallas, TX")
        draw.text((305, 113), home_terminal[:30], fill='black', font=font) # Adjusted
        
    except Exception as e:
        logger.error(f"Error drawing header: {e}")

    # =========================================================================
    # GRID DRAWING — the 24-hour HOS duty status grid
    # =========================================================================
    # Based on pixel analysis of blank-paper-log.png (513x518):
    # The grid area runs from the "Midnight" left label to "Midnight" right label
    # X: left edge ~x=60, right edge ~x=472  (before "Total Hours" column)
    # The grid has 24 columns (one per hour)
    try:
        # Slightly adjusted grid positions
        x_grid_left = 55  # Moved left slightly
        x_grid_right = 472
        grid_width = x_grid_right - x_grid_left
        
        # Adjusted Y positions based on template
        y_off_duty = 190   # Slightly up
        y_sleeper = 206    # Slightly up
        y_driving = 222    # Slightly up
        y_on_duty = 238    # Slightly up
        
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
    except Exception as e:
        logger.error(f"Error drawing grid: {e}")

    # =========================================================================
    # TOTAL HOURS COLUMN — right side of the grid
    # =========================================================================
    # The "Total Hours" column is at the far right, approximately x=483
    try:
        x_totals = 460  # Slightly right
        y_off_duty = 197
        y_sleeper = 217
        y_driving = 227
        y_on_duty = 244
        
        draw.text((x_totals, y_off_duty - 6), f"{totals['OFF']:.1f}", fill='black', font=bold_font)
        draw.text((x_totals, y_sleeper - 6), f"{totals['SB']:.1f}", fill='black', font=bold_font)
        draw.text((x_totals, y_driving - 6), f"{totals['D']:.1f}", fill='black', font=bold_font)
        draw.text((x_totals, y_on_duty - 6), f"{totals['ON']:.1f}", fill='black', font=bold_font)
        
        grand_total = sum(totals.values())
        draw.text((x_totals, 254), f"{grand_total:.1f}", fill='black', font=bold_font)
    except Exception as e:
        logger.error(f"Error drawing totals: {e}")

    # =========================================================================
    # REMARKS SECTION — below the grid
    # =========================================================================
    # "Remarks" section starts around y=263. We'll draw our remarks below y=275
    try:
        y_remark = 275  # Slightly up
        remark_lines = []
        for act in day_activities:
            desc = act["description"]
            if desc == "Off Duty / Rest":
                continue
            start_str = act["start"].strftime("%I:%M %p")
            loc = act["location"]
            remark_lines.append(f"{start_str} - {desc} ({loc})")
        
        col_x = 15  # Moved left
        for idx, remark in enumerate(remark_lines[:14]):
            if idx == 7:
                col_x = 262  # Moved left
                y_remark = 275
            draw.text((col_x, y_remark), remark[:42], fill='black', font=font_sm)
            y_remark += 10
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
        draw.text((85, 440), f"{on_duty_today:.1f}", fill='black', font=font)
        draw.text((155, 440), f"{recap_a:.1f}", fill='black', font=font)
        draw.text((215, 440), f"{recap_b:.1f}", fill='black', font=font)
        
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
