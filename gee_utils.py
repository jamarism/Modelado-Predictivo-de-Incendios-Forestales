# gee_utils.py
# ------------------------------------------------------------
# Utilidades para Google Earth Engine + exportación con caché
# Juan David Amaris · 2025
# ------------------------------------------------------------
import os, time, ee, shutil, sys
from importlib import util as _iu
import google.auth  # Import for credentials

# ============================================================
# 0.  Carpeta de caché  (Drive si existe, local en otro caso)
# ============================================================
CACHE_DIR   = "/content/gee_cache"          # fallback local
USING_DRIVE = False

try:
    from google.colab import drive, _ipython
    if _ipython.get_ipython() is not None:  # estamos dentro de un notebook
        drive.mount("/content/drive", force_remount=False)
        CACHE_DIR   = "/content/drive/My Drive/gee_cache"
        USING_DRIVE = True
        print("✅  Drive montado → caché:", CACHE_DIR)
except Exception as e:
    print("⚠️  No se montó Drive, usaré caché local:", CACHE_DIR)

os.makedirs(CACHE_DIR, exist_ok=True)

# ============================================================
# 1.  Inicializar Earth Engine
# ============================================================
def init_gee(service_acct_json: dict | None = None):
    """
    Inicializa Earth Engine con el proyecto EE_PROJECT.
      • Si se pasa un JSON de Service Account → lo usa.
      • Si no, intenta EE.Initialize(); si falla y estamos en notebook
        abre el flujo OAuth.
    """
    if service_acct_json:
        creds = ee.ServiceAccountCredentials(
            service_account=service_acct_json["client_email"],
            key_data=service_acct_json,
        )
        ee.Initialize(creds, project=EE_PROJECT)
        print("✅ Earth Engine initialized with service account.")
    else:
        try:
            ee.Initialize()
            print("✅ Earth Engine initialized with default credentials.")
        except ee.EEException as e:
            if _in_notebook():
                print("⚠️ Default initialization failed. Trying OAuth...")
                # Get application default credentials
                credentials, project = google.auth.default() 
                ee.Initialize(credentials, project=EE_PROJECT)
                print("✅ Earth Engine initialized with OAuth.")
            else:
                raise e 

# ============================================================
# 2.  Polling de tareas
# ============================================================
def wait_for_task(task, poll_interval: int = 30):
    """Bloquea hasta que la tarea termine (o falle)."""
    while task.active():
        print(f"⏳  Esperando… estado: {task.status()['state']}")
        time.sleep(poll_interval)
    status = task.status()
    if status["state"] != "COMPLETED":
        raise RuntimeError(f"Tarea falló: {status}")
    print("✅  Tarea completada")

# ============================================================
# 3.  Exportar imagen con caché
# ============================================================
def export_if_needed(img, desc: str, region, scale: int, crs: str = "EPSG:4326"):
    """
    Exporta a GeoTIFF solo si no existe en la caché.
    Devuelve la ruta local al .tif.
    """
    tif_path = os.path.join(CACHE_DIR, f"{desc}.tif")
    if os.path.exists(tif_path):
        print(f"🔁  Usando caché: {tif_path}")
        return tif_path

    print(f"🚀  Exportando {desc} a Drive…")
    task = ee.batch.Export.image.toDrive(
        image=img,
        description=desc,
        fileNamePrefix=desc,
        scale=scale,
        region=region,
        fileFormat="GeoTIFF",
        crs=crs,
    )
    task.start()
    wait_for_task(task)

    if USING_DRIVE:
        drive_path = f"/content/drive/My Drive/{desc}.tif"
        if not os.path.exists(drive_path):
            raise FileNotFoundError("Exportación terminada pero archivo no encontrado en Drive.")
        shutil.move(drive_path, tif_path)
        print(f"📥  Copiado a caché: {tif_path}")
    else:
        raise RuntimeError(
            "Exportación completada, pero sin Drive montado para copiar el archivo."
        )

    return tif_path

# ============================================================
# 4.  Funciones de dominio (regiones + medianas)
# ============================================================
def get_regions():
    """FeatureCollection con Cundinamarca y Boyacá."""
    gaul = ee.FeatureCollection("FAO/GAUL/2015/level1")
    return gaul.filter(
        ee.Filter.Or(
            ee.Filter.eq("ADM1_NAME", "Cundinamarca"),
            ee.Filter.eq("ADM1_NAME", "Boyaca"),
        )
    )

def ndvi_lst_median(start_date: str, end_date: str,
                    buffer_km: int = 10, scale: int = 250):
    """
    Devuelve (ndvi_img, lst_img, regiones).
    NDVI: MODIS/061/MOD13Q1   LST: MODIS/061/MOD11A1
    """
    regions = get_regions()
    roi = regions.geometry().buffer(buffer_km * 1000)

    ndvi = (
        ee.ImageCollection("MODIS/061/MOD13Q1")
        .filterBounds(roi)
        .filterDate(start_date, end_date)
        .select("NDVI")
        .median()
        .multiply(0.0001)
    )

    lst = (
        ee.ImageCollection("MODIS/061/MOD11A1")
        .filterBounds(roi)
        .filterDate(start_date, end_date)
        .select("LST_Day_1km")
        .median()
        .multiply(0.02)
        .subtract(273.15)
        .rename("LST")
    )

    ndvi = ndvi.reproject(crs="EPSG:4326", scale=scale).clip(regions)
    lst  = lst .reproject(crs="EPSG:4326", scale=scale).clip(regions)
    return ndvi, lst, regions
