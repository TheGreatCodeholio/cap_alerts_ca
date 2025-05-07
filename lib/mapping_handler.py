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
    desired_width_px = 800
    desired_height_px = 800
    dpi = 300

    width_in = desired_width_px / dpi
    height_in = desired_height_px / dpi

    # Initialize min and max values with the first point
    first_point = polygons[0].split()[0]
    min_lat, max_lon = map(float, first_point.split(','))
    max_lat = min_lat
    min_lon = max_lon

    for polygon in polygons:
        points = polygon.split()
        for point in points:
            lat, lon = map(float, point.split(','))
            min_lat = min(min_lat, lat)
            max_lat = max(max_lat, lat)
            min_lon = min(min_lon, lon)
            max_lon = max(max_lon, lon)

    # Create the figure and axis with Cartopy projection
    fig, ax = plt.subplots(figsize=(width_in, height_in), subplot_kw={'projection': ccrs.PlateCarree()})
    tiles = GoogleTiles()
    # tiles = OSM()  # Uncomment if using OSM tiles
    ax.add_image(tiles, 7)

    # Minimum ranges for latitude and longitude
    min_lat_range = 5
    min_lon_range = 5

    lat_range = max(max_lat - min_lat, min_lat_range)
    lon_range = max(max_lon - min_lon, min_lon_range)

    center_lat = (max_lat + min_lat) / 2
    center_lon = (max_lon + min_lon) / 2

    ax.set_extent([center_lon - lon_range / 2, center_lon + lon_range / 2,
                   center_lat - lat_range / 2, center_lat + lat_range / 2])

    for polygon in polygons:
        plot_polygon(ax, polygon, line_width=0.3, alpha=0.3)

    plt.subplots_adjust(left=0, right=1, top=1, bottom=0)

    buf = None
    try:
        if config_data["canada_cap_stream"].get("save_map", 0) == 1:
            map_file_name = f"{alert_file_name}_map.png"
            plt.savefig(os.path.join(alert_folder_path, map_file_name), dpi=dpi, bbox_inches='tight', pad_inches=0)

        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=dpi, bbox_inches='tight', pad_inches=0)
        buf.seek(0)
        image_base64 = base64.b64encode(buf.read()).decode('utf-8')
    except Exception as e:
        print(f"An error occurred while creating the map image: {e}")
        image_base64 = None
    finally:
        if buf:
            buf.close()
        plt.close(fig)

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
