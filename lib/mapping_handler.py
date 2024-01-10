import base64
import io
import logging
import cartopy.crs as ccrs
from cartopy.io.img_tiles import GoogleTiles
import os
import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt


module_logger = logging.getLogger("icad_cap_alerts.mapping")


def create_map_image(config_data, alert_file_name, polygons, alert_folder_path):
    desired_width_px = 1000  # Desired width in pixels
    desired_height_px = 1000  # Desired height in pixels
    dpi = 400

    # Calculate the size in inches
    width_in = desired_width_px / dpi
    height_in = desired_height_px / dpi

    # Initialize min and max values with the first point
    first_point = polygons[0].split()[0]
    min_lat, max_lon = map(float, first_point.split(','))
    max_lat, min_lon = min_lat, max_lon

    # Iterate through each polygon and each point to find the min and max values
    for polygon in polygons:
        points = polygon.split()
        for point in points:
            lat, lon = map(float, point.split(','))
            min_lat = min(min_lat, lat)
            max_lat = max(max_lat, lat)
            min_lon = min(min_lon, lon)
            max_lon = max(max_lon, lon)

    # Create a plot with a specific projection
    fig, ax = plt.subplots(figsize=(width_in, height_in), subplot_kw={'projection': ccrs.PlateCarree()})
    # tiles = OSM()
    tiles = GoogleTiles()
    ax.add_image(tiles, 7)

    # Minimum ranges for latitude and longitude
    min_lat_range = 5  # Adjust as needed
    min_lon_range = 5  # Adjust as needed

    # Calculate ranges
    lat_range = max(max_lat - min_lat, min_lat_range)
    lon_range = max(max_lon - min_lon, min_lon_range)

    # Calculate the center of the bounding box
    center_lat = (max_lat + min_lat) / 2
    center_lon = (max_lon + min_lon) / 2

    # Set the extent with minimum ranges
    ax.set_extent([center_lon - lon_range / 2, center_lon + lon_range / 2, center_lat - lat_range / 2,
                   center_lat + lat_range / 2])

    # Plot each polygon
    for polygon in polygons:
        plot_polygon(ax, polygon, line_width=0.3, alpha=0.3)

    # ax.set_title(alert_description.title())

    plt.subplots_adjust(left=0, right=1, top=1, bottom=0)
    if config_data["canada_cap_stream"].get("save_map", 0) == 1:
        map_file_name = f"{alert_file_name}_map.png"

        plt.savefig(os.path.join(alert_folder_path, map_file_name), dpi=dpi, bbox_inches='tight', pad_inches=0)

    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=dpi, bbox_inches='tight', pad_inches=0)
    plt.close()
    buf.seek(0)
    image_base64 = base64.b64encode(buf.read()).decode('utf-8')
    return image_base64


def plot_polygon(ax, polygon, line_width=0.5, fill_color='red', alpha=0.5):
    # Split the string into pairs of lat, lon and reverse the order
    points = polygon.split(' ')
    lats, lons = zip(*[map(float, point.split(',')) for point in points[::-1]])  # Note the [::-1] to reverse

    # Plot the polygon outline
    ax.plot(lons, lats, marker='o', color=fill_color, markersize=1, linestyle='-', linewidth=line_width,
            transform=ccrs.Geodetic())

    # Fill the polygon with the specified color and transparency
    ax.fill(lons, lats, color=fill_color, alpha=alpha, transform=ccrs.Geodetic())
