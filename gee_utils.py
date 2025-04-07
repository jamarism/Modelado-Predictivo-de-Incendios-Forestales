import os
import time
import zipfile
import io
import requests
from datetime import datetime

import ee
import numpy as np
import rasterio

# --------------------------------------------------
# 1. Autenticación e inicialización de Google Earth Engine
# --------------------------------------------------

def init_gee(service_account_email: str | None = None, private_key_path: str | None = None):
    """Inicializa Earth Engine.

    Si no se proporciona cuenta de servicio, intenta autenticación OAuth
    interactiva (útil en Colab).  Si ya existen credenciales guardadas
    simplemente se reutilizan.
    """
    try:
        if service_account_email and private_key_path:
            credentials = ee.ServiceAccountCredentials(service_account_email, private_key_path)
            ee.Initialize(credentials)
        else:
            # Inicialización típica para Colab / OAuth.
            ee.Initialize()
    except Exception:
        # Si falló (p. ej. primera vez) se autentica de forma interactiva.
        print("⚠️  No se encontraron credenciales válidas, iniciando flujo OAuth…")
        ee.Authenticate()
        ee.Initialize()
    print("✅ Earth Engine listo.")

# --------------------------------------------------
# 2. Regiones de interés
# --------------------------------------------------

def _boyaca_cundinamarca_geometry():
    """Devuelve la geometría unificada de Boyacá y Cundinamarca (GAUL‑2015)."""
    adm1 = ee.FeatureCollection("FAO/GAUL/2015/level1")
    sel  = adm1.filter(ee.Filter.Or(
        ee.Filter.eq('ADM1_NAME', 'Boyacá'),
        ee.Filter.eq('ADM1_NAME', 'Cundinamarca')
    ))
    return sel.geometry().bounds()

ROI = _boyaca_cundinamarca_geometry()

# --------------------------------------------------
# 3. Productos satelitales y pre‑procesamiento
# --------------------------------------------------

_S2_SR   = "COPERNICUS/S2_SR_HARMONIZED"  # Sentinel‑2 nivel 2A
_MOD11A2 = "MODIS/061/MOD11A2"            # LST 8‑días 1 km


def _sentinel2_ndvi(start: str, end: str):
    start_dt, end_dt = map(lambda s: datetime.strptime(s, "%Y-%m-%d"), (start, end))
    coll = (ee.ImageCollection(_S2_SR)
            .filterDate(start_dt, end_dt)
            .filterBounds(ROI)
            .filter(ee.Filter.lte('CLOUDY_PIXEL_PERCENTAGE', 30))
            .map(lambda img: img.updateMask(img.select('QA60').bitwiseAnd(1 << 10).eq(0)))  # quitar saturación
           )
    def _add_ndvi(img):
        ndvi = img.normalizedDifference(['B8', 'B4']).rename('NDVI')
        return img.addBands(ndvi)
    coll = coll.map(_add_ndvi)
    return coll.select('NDVI').median()


def _modis_lst(start: str, end: str):
    start_dt, end_dt = map(lambda s: datetime.strptime(s, "%Y-%m-%d"), (start, end))
    coll = (ee.ImageCollection(_MOD11A2)
            .filterDate(start_dt, end_dt)
            .filterBounds(ROI))
    # La banda LST_Day_1km está en Kelvin * 0.02
    lst  = coll.select('LST_Day_1km').median().multiply(0.02).subtract(273.15).rename('LST')
    return lst.resample('bilinear')


def ndvi_lst_median(start: str, end: str):
    """Calcula imágenes medianas de NDVI (Sentinel‑2) y LST (MODIS).

    Retorna (ndvi_img, lst_img, region) donde *region* es la geometría de exportación.
    """
    ndvi = _sentinel2_ndvi(start, end)
    lst  = _modis_lst(start, end)
    return ndvi, lst, ROI

# --------------------------------------------------
# 4. Exportación a GeoTIFF local (solo si no existe)
# --------------------------------------------------

def _download_url_to_tif(url: str, out_tif: str):
    """Descarga y extrae el GeoTIFF desde el URL de Earth Engine (zip)."""
    print(f"⬇️  Descargando {os.path.basename(out_tif)} …")
    r = requests.get(url, stream=True)
    r.raise_for_status()
    z = zipfile.ZipFile(io.BytesIO(r.content))
    z.extractall(os.path.dirname(out_tif))


def export_if_needed(img: ee.Image, name: str, region, scale: int = 250, out_dir: str = "/content/data") -> str:
    """Exporta *img* a GeoTIFF si aún no existe y devuelve la ruta local.

    *img*      ‑ Imagen de Earth Engine
    *name*     ‑ Nombre base del archivo (sin extensión)
    *region*   ‑ Lista de coords [[lon,lat], …] o ee.Geometry
    *scale*    ‑ Resolución en metros
    *out_dir*  ‑ Carpeta de salida local
    """
    os.makedirs(out_dir, exist_ok=True)
    out_tif = os.path.join(out_dir, f"{name}.tif")
    if os.path.exists(out_tif):
        print(f"✅ {name}.tif ya existe, se omite exportación.")
        return out_tif

    # Solicitar URL de descarga (Earth Engine genera ZIP)
    print(f"🚀 Exportando {name} desde Earth Engine…")
    if isinstance(region, ee.Geometry):
        region_coords = region.coordinates().getInfo()
    else:
        region_coords = region  # asume lista

    url = img.getDownloadURL({
        'scale': scale,
        'crs': 'EPSG:4326',
        'region': region_coords,
        'format': 'GEO_TIFF'
    })

    # Descargar y extraer
    _download_url_to_tif(url, out_tif)

    # El ZIP incluye el tif como {name}.tif dentro de la carpeta.
    # Verificamos su existencia y retornamos ruta final.
    if not os.path.exists(out_tif):
        # Buscar el archivo dentro del directorio
        for root, _, files in os.walk(out_dir):
            for f in files:
                if f.lower().endswith('.tif') and name.lower() in f.lower():
                    out_tif = os.path.join(root, f)
                    break
    print(f"✅ Exportación terminada: {out_tif}")
    return out_tif

# --------------------------------------------------
# 5. Utilidades extra
# --------------------------------------------------

def read_flat_array(path: str):
    """Lee un raster en un array 1‑D (ignora nodata)."""
    with rasterio.open(path) as src:
        arr = src.read(1)
        nodata = src.nodata if src.nodata is not None else np.nan
    return arr.flatten(), nodata

__all__ = [
    'init_gee',
    'ndvi_lst_median',
    'export_if_needed',
]
