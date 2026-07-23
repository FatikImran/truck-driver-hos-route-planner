import os
import base64
import datetime
import logging
from io import BytesIO
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# Set up logging
logger = logging.getLogger(__name__)

def time_to_pixel_x(time_obj, grid_left, grid_width):
    """Convert time to pixel X coordinate."""
    hours = time_obj.hour + time_obj.minute / 60.0 + time_obj.second / 3600.0
    return int(grid_left + (hours / 24.0) * grid_width)

def draw_diagonal_line(draw, x1, y1, x2, y2, color='black', width=1):
    """Draw a diagonal line between two points."""
    draw.line([(x1, y1), (x2, y2)], fill=color, width=width)

def draw_bucket(draw, x_left, x_right, y_line, y_bottom, color='black', fill_color=None):
    """
    Draw a bucket/flag shape extending from the diagonal line.
    The bucket goes from the diagonal line down to the bottom of the status row.
    """
    if fill_color:
        draw.polygon([(x_left, y_line), (x_right, y_line), (x_right, y_bottom), (x_left, y_bottom)], 
                     outline=color, fill=fill_color)
    else:
        draw.polygon([(x_left, y_line), (x_right, y_line), (x_right, y_bottom), (x_left, y_bottom)], 
                     outline=color)

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
        
        # Row boundaries (top and bottom of each status row)
        row_height = 14
        y_off_top = y_off_duty - row_height // 2
        y_off_bottom = y_off_duty + row_height // 2
        y_sb_top = y_sleeper - row_height // 2
        y_sb_bottom = y_sleeper + row_height // 2
        y_d_top = y_driving - row_height // 2
        y_d_bottom = y_driving + row_height // 2
        y_on_top = y_on_duty - row_height // 2
        y_on_bottom = y_on_duty + row_height // 2
        
        status_y_map = {
            "OFF": (y_off_duty, y_off_top, y_off_bottom),
            "SB": (y_sleeper, y_sb_top, y_sb_bottom),
            "D": (y_driving, y_d_top, y_d_bottom),
            "ON": (y_on_duty, y_on_top, y_on_bottom),
        }
 
        # Color mapping for statuses
        status_colors = {
            "OFF": "#10b981",
            "SB": "#3b82f6",
            "D": "#f59e0b",
            "ON": "#8b5cf6",
        }
        
        # Sort activities by start time
        sorted_activities = sorted(day_activities, key=lambda a: a["start"])
        
        # Group consecutive activities by status and location
        grouped_activities = []
        current_group = None
        
        for act in sorted_activities:
            status = act["status"]
            location = act["location"]
            
            if current_group is None or current_group["status"] != status or current_group["location"] != location:
                if current_group is not None:
                    grouped_activities.append(current_group)
                current_group = {
                    "status": status,
                    "location": location,
                    "start": act["start"],
                    "end": act["end"],
                    "duration_hours": act["duration_hours"],
                    "description": act["description"],
                    "activities": [act]
                }
            else:
                current_group["end"] = act["end"]
                current_group["duration_hours"] += act["duration_hours"]
                current_group["activities"].append(act)
        
        if current_group is not None:
            grouped_activities.append(current_group)
        
        # Draw horizontal lines for each group
        for i, group in enumerate(grouped_activities):
            status = group["status"]
            y_center, y_top, y_bottom = status_y_map.get(status, (y_off_duty, y_off_top, y_off_bottom))
            
            start_x = time_to_pixel_x(group["start"], x_grid_left, grid_width)
            end_x = time_to_pixel_x(group["end"], x_grid_left, grid_width)
            
            # Draw horizontal line
            draw.line([(start_x, y_center), (end_x, y_center)], fill='blue', width=2)
            
            # Draw bucket (vertical lines at start and end of the status block)
            # This creates the "bucket" effect - vertical lines at status boundaries
            if i == 0:
                # First group - only draw right boundary
                draw.line([(end_x, y_top), (end_x, y_bottom)], fill='blue', width=1)
            elif i == len(grouped_activities) - 1:
                # Last group - only draw left boundary
                draw.line([(start_x, y_top), (start_x, y_bottom)], fill='blue', width=1)
            else:
                # Middle group - draw both boundaries
                draw.line([(start_x, y_top), (start_x, y_bottom)], fill='blue', width=1)
                draw.line([(end_x, y_top), (end_x, y_bottom)], fill='blue', width=1)
        
        # Draw diagonal lines between status changes
        for i in range(len(grouped_activities) - 1):
            current_group = grouped_activities[i]
            next_group = grouped_activities[i + 1]
            
            # Get the Y positions for the two statuses
            _, curr_top, curr_bottom = status_y_map.get(current_group["status"], (y_off_duty, y_off_top, y_off_bottom))
            _, next_top, next_bottom = status_y_map.get(next_group["status"], (y_off_duty, y_off_top, y_off_bottom))
            
            # The transition point is at the end of the current group's X position
            transition_x = time_to_pixel_x(current_group["end"], x_grid_left, grid_width)
            
            # Current status Y (center of the row)
            curr_y = status_y_map.get(current_group["status"], (y_off_duty, y_off_top, y_off_bottom))[0]
            next_y = status_y_map.get(next_group["status"], (y_off_duty, y_off_top, y_off_bottom))[0]
            
            # Draw diagonal line from current status to next status
            draw_diagonal_line(draw, transition_x, curr_y, transition_x + 15, next_y, color='blue', width=2)
            
            # Draw the reverse diagonal from next status to current status
            draw_diagonal_line(draw, transition_x, next_y, transition_x + 15, curr_y, color='blue', width=2)
            
            # Draw vertical lines at the transition (bucket effect)
            draw.line([(transition_x, curr_top), (transition_x, curr_bottom)], fill='blue', width=1)
            draw.line([(transition_x + 15, next_top), (transition_x + 15, next_bottom)], fill='blue', width=1)
            
            # Draw "bucket" shape - a flag extending from the diagonal
            # This creates the visual effect of a bucket/flag at the transition point
            draw.polygon([
                (transition_x, curr_top),
                (transition_x, curr_bottom),
                (transition_x + 15, next_bottom),
                (transition_x + 15, next_top)
            ], outline='blue', width=1)
            
            # Add remark text along the diagonal
            remark_text = f"{current_group['description']} → {next_group['description']}"
            if len(remark_text) > 25:
                remark_text = remark_text[:22] + "..."
            
            # Position the remark at the diagonal
            remark_x = transition_x + 20
            remark_y = (curr_y + next_y) // 2 - 4
            
            # Draw the remark with a small background for readability
            draw.text((remark_x, remark_y), remark_text, fill='black', font=font_remark)

    except Exception as e:
        logger.error(f"Error drawing grid: {e}")

    # =========================================================================
    # TOTAL HOURS COLUMN — right side of the grid
    # =========================================================================
    try:
        totals = {"OFF": 0.0, "SB": 0.0, "D": 0.0, "ON": 0.0}
        for act in sorted_activities:
            totals[act["status"]] += act["duration_hours"]
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
    # REMARKS SECTION - Listed remarks at bottom
    # =========================================================================
    # "Remarks" section starts around y=263. We'll draw our remarks below y=275
    try:
        y_remark = 275
        remark_lines = []
        
        for act in sorted_activities:
            desc = act["description"]
            if desc == "Off Duty / Rest":
                continue
            start_str = act["start"].strftime("%I:%M %p")
            loc = act["location"]
            remark_lines.append(f"{start_str} - {desc} ({loc})")
        
        col_x = 15
        for idx, remark in enumerate(remark_lines[:14]):
            if idx == 7:
                col_x = 262
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
