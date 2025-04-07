import os
import time
import zipfile
import io
import requests
from datetime import datetime

import ee
import numpy as np
import rasterio

"""
gee_utils.py
--------------
Utilidades para proyectos de Google Earth Engine en Colab.

• Autenticación flexible (usuario OAuth, cuentas de servicio, gcloud, Colab, etc.)
• Descarga perezosa de GeoTIFFs a disco
• Cálculo de medianas NDVI (Sentinel‑2) y LST (MODIS)

Ajustado para seguir las recomendaciones oficiales de autenticación de Earth Engine
(ver https://developers.google.com/earth-engine/guides/python_install).  Se llama
siempre a ``ee.Authenticate()`` cuando es necesario y se permite especificar un
``project`` de Google Cloud.
"""

# -----------------------------------------------------------------------------
# 1. Autenticación e inicialización de Earth Engine
# -----------------------------------------------------------------------------

def init_gee(
    project: str | None = None,
    auth_mode: str | None = None,
    *,
    service_account_email: str | None = None,
    private_key_path: str | None = None,
    force_reauth: bool = False,
):
    """Inicializa Google Earth Engine.

    Parámetros
    ----------
    project : str, opcional
        ID del proyecto de Google Cloud que se usará para ejecutar las tareas.
        *Muy* recomendable para evitar errores de cuota.
    auth_mode : str, opcional
        Modo de autenticación a pasar a :pyfunc:`ee.Authenticate` (``'colab'``,
        ``'gcloud'``, ``'localhost'``, ``'notebook'``).  Si es ``None`` se deja
        que la librería seleccione el modo apropiado.
    service_account_email, private_key_path : str, opcional
        Si se proporcionan, se autenticará mediante una **cuenta de servicio**.
    force_reauth : bool, default *False*
        Si ``True`` se forzará un nuevo flujo de autenticación incluso si ya hay
        credenciales almacenadas.

    Ejemplos
    --------
    >>> init_gee(project="mi‑proyecto")                # OAuth interactivo
    >>> init_gee(project="mi‑proyecto",                # cuenta de servicio
                 service_account_email="svc@proj.iam.gserviceaccount.com",
                 private_key_path="/content/key.json")
    """

    # --- Cuenta de servicio ---------------------------------------------------
    if service_account_email and private_key_path:
        print("🔑 Autenticando con cuenta de servicio …")
        credentials = ee.ServiceAccountCredentials(
            service_account_email, private_key_path
        )
        ee.Initialize(credentials, project=project)
        print("✅ Earth Engine listo (cuenta de servicio).")
        return

    # --- OAuth / gcloud / notebook / Colab -----------------------------------
    try:
        # Intentar inicializar con credenciales existentes
        ee.Initialize(project=project)
    except Exception as exc:
        # Si falla, lanzar flujo de autenticación interactiva
        msg = "⚠️  No se encontraron credenciales válidas o están caducadas. " \
              "Iniciando flujo ee.Authenticate() …"
        print(msg)
        ee.Authenticate(auth_mode=auth_mode, force=force_reauth)
        ee.Initialize(project=project)

    print("✅ Earth Engine listo.")

# -----------------------------------------------------------------------------
# 2. Regiones de interés
# -----------------------------------------------------------------------------

def _boyaca_cundinamarca_geometry():
    """Devuelve la geometría unificada de Boyacá y Cundinamarca (GAUL‑2015)."""
    adm1 = ee.FeatureCollection("FAO/GAUL/2015/level1")
    sel  = adm1.filter(ee.Filter.Or(
        ee.Filter.eq('ADM1_NAME', 'Boyacá'),
        ee.Filter.eq('ADM1_NAME', 'Cundinamarca')
    ))
    return sel.geometry().bounds()

ROI = _boyaca_cundinamarca_geometry()

# -----------------------------------------------------------------------------
# 3. Productos satelitales y pre‑procesamiento
# -----------------------------------------------------------------------------

_S2_SR   = "COPERNICUS/S2_SR_HARMONIZED"  # Sentinel‑2 nivel 2A
_MOD11A2 = "MODIS/061/MOD11A2"            # LST 8‑días 1 km


def _sentinel2_ndvi(start: str, end: str):
    start_dt, end_dt = map(lambda s: datetime.strptime(s, "%Y-%m-%d"), (start, end))
    coll = (
        ee.ImageCollection(_S2_SR)
        .filterDate(start_dt, end_dt)
        .filterBounds(ROI)
        .filter(ee.Filter.lte('CLOUDY_PIXEL_PERCENTAGE', 30))
        .map(lambda img: img.updateMask(img.select('QA60').bitwiseAnd(1 << 10).eq(0)))
    )

    def _add_ndvi(img):
        ndvi = img.normalizedDifference(['B8', 'B4']).rename('NDVI')
        return img.addBands(ndvi)

    coll = coll.map(_add_ndvi)
    return coll.select('NDVI').median()


def _modis_lst(start: str, end: str):
    start_dt, end_dt = map(lambda s: datetime.strptime(s, "%Y-%m-%d"), (start, end))
    coll = (
        ee.ImageCollection(_MOD11A2)
        .filterDate(start_dt, end_dt)
        .filterBounds(ROI)
    )
    # LST_Day_1km está en Kelvin * 0.02
    lst = (
        coll.select('LST_Day_1km')
        .median()
        .multiply(0.02)
        .subtract(273.15)
        .rename('LST')
        .resample('bilinear')
    )
    return lst


def ndvi_lst_median(start: str, end: str):
    """Calcula imágenes medianas de NDVI (Sentinel‑2) y LST (MODIS)."""
    ndvi = _sentinel2_ndvi(start, end)
    lst  = _modis_lst(start, end)
    return ndvi, lst, ROI

# -----------------------------------------------------------------------------
# 4. Exportación a GeoTIFF local (perezosa)
# -----------------------------------------------------------------------------

def _download_url_to_tif(url: str, out_tif: str):
    """Descarga y extrae el GeoTIFF desde el URL de Earth Engine (ZIP)."""
    print(f"⬇️  Descargando {os.path.basename(out_tif)} …")
    r = requests.get(url, stream=True)
    r.raise_for_status()
    z = zipfile.ZipFile(io.BytesIO(r.content))
    z.extractall(os.path.dirname(out_tif))


def export_if_needed(
    img: ee.Image,
    name: str,
    region,
    scale: int = 250,
    out_dir: str = "/content/data",
) -> str:
    """Exporta *img* a GeoTIFF si aún no existe y devuelve la ruta local."""

    os.makedirs(out_dir, exist_ok=True)
    out_tif = os.path.join(out_dir, f"{name}.tif")
    if os.path.exists(out_tif):
        print(f"✅ {name}.tif ya existe, se omite exportación.")
        return out_tif

    print(f"🚀 Exportando {name} desde Earth Engine…")

    if isinstance(region, ee.Geometry):
        region_coords = region.coordinates().getInfo()
    else:
        region_coords = region  # asume lista de coordenadas

    url = img.getDownloadURL({
        'scale': scale,
        'crs': 'EPSG:4326',
        'region': region_coords,
        'format': 'GEO_TIFF',
    })

    _download_url_to_tif(url, out_tif)

    # El ZIP incluye el tif como {name}.tif dentro de la carpeta.
    # Verificamos su existencia y retornamos ruta final.
    if not os.path.exists(out_tif):
        for root, _, files in os.walk(out_dir):
            for f in files:
                if f.lower().endswith('.tif') and name.lower() in f.lower():
                    out_tif = os.path.join(root, f)
                    break
    print(f"✅ Exportación terminada: {out_tif}")
    return out_tif

# -----------------------------------------------------------------------------
# 5. Utilidades adicionales
# -----------------------------------------------------------------------------

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
