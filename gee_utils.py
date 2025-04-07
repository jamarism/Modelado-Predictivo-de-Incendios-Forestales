# gee_utils.py
# ------------------------------------------------------------
import os, time, ee, shutil

# ---------- 0. Caché en Drive o local ----------
CACHE_DIR = "/content/gee_cache"
USING_DRIVE = False
try:
    from google.colab import drive, _ipython
    if _ipython.get_ipython() is not None:
        drive.mount("/content/drive", force_remount=False)
        CACHE_DIR = "/content/drive/My Drive/gee_cache"
        USING_DRIVE = True
        print("✅  Drive montado, usando caché en Drive:", CACHE_DIR)
except Exception:
    print("⚠️  No se montó Drive; usaré caché local:", CACHE_DIR)
os.makedirs(CACHE_DIR, exist_ok=True)

# ---------- 1. Inicializar Earth Engine ----------
def init_gee(service_acct_json=None):
    if service_acct_json:
        creds = ee.ServiceAccountCredentials(
            service_account=service_acct_json["client_email"],
            key_data=service_acct_json
        )
        ee.Initialize(creds)
        print("🔑  GEE inicializado con cuenta de servicio")
    else:
        try:
            ee.Initialize()
            print("🔑  GEE ya estaba inicializado")
        except Exception:
            print("🔐  Autenticando con OAuth…")
            ee.Authenticate()
            ee.Initialize()

# ---------- 2. Polling ----------
def wait_for_task(task, poll_interval=30):
    while task.active():
        print(f"⏳  Esperando… estado: {task.status()['state']}")
        time.sleep(poll_interval)
    if task.status()["state"] != "COMPLETED":
        raise RuntimeError(f"Tarea falló: {task.status()}")
    print("✅  Tarea completada")

# ---------- 3. Exportar con caché ----------
def export_if_needed(img, desc, region, scale, crs="EPSG:4326"):
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
        raise RuntimeError("Exportado, pero sin Drive montado para copiar el archivo.")
    return tif_path

# ---------- 4. Funciones de dominio (faltaban) ----------
def get_regions():
    """Devuelve FeatureCollection con Cundinamarca y Boyacá."""
    gaul = ee.FeatureCollection("FAO/GAUL/2015/level1")
    return gaul.filter(
        ee.Filter.Or(
            ee.Filter.eq("ADM1_NAME", "Cundinamarca"),
            ee.Filter.eq("ADM1_NAME", "Boyaca"),
        )
    )

def ndvi_lst_median(start_date, end_date, buffer_km=10, scale=250):
    """
    Calcula las medianas de NDVI y LST MODIS para las fechas indicadas
    y devuelve (ndvi_img, lst_img, regiones_featureCollection).
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
