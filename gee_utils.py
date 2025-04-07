"""
gee_utils.py
Utilidades para autenticación en Earth Engine, descarga de NDVI y LST,
muestreo de hasta 10 000 píxeles y generación del gráfico NDVI vs. LST.
"""

import os
import time
import ee
import numpy as np
import matplotlib.pyplot as plt
import tempfile
from google.colab import auth

# ----------------------------------------------------------------------
# 1. Autenticación y arranque
# ----------------------------------------------------------------------

def init_ee():
    """Autentica al usuario en Colab y arranca Earth Engine."""
    auth.authenticate_user()
    ee.Initialize()

# ----------------------------------------------------------------------
# 2. Regiones de interés
# ----------------------------------------------------------------------

def get_regions():
    """Devuelve la geometría de Cundinamarca y Boyacá, con un buffer de 10 km."""
    fc = (ee.FeatureCollection("FAO/GAUL/2015/level1")
          .filter(ee.Filter.Or(
              ee.Filter.eq('ADM1_NAME', 'Cundinamarca'),
              ee.Filter.eq('ADM1_NAME', 'Boyaca'))))
    return fc, fc.geometry().buffer(10_000)

# ----------------------------------------------------------------------
# 3. Procesamiento de colecciones MODIS
# ----------------------------------------------------------------------

def get_ndvi(lst_start, lst_end, geom):
    coll = (ee.ImageCollection('MODIS/061/MOD13Q1')
            .filterDate(lst_start, lst_end)
            .filterBounds(geom)
            .select('NDVI'))
    return coll.median().multiply(0.0001).rename('NDVI')

def get_lst(lst_start, lst_end, geom):
    coll = (ee.ImageCollection('MODIS/061/MOD11A1')
            .filterDate(lst_start, lst_end)
            .filterBounds(geom)
            .select('LST_Day_1km'))
    return (coll.median().multiply(0.02)
            .subtract(273.15).rename('LST'))

# ----------------------------------------------------------------------
# 4. Muestreo y gráfico
# ----------------------------------------------------------------------

def sample_images(ndvi_img, lst_img, geom, scale=250, n_points=10_000):
    """Devuelve un ndarray Nx2 con valores NDVI‑LST muestreados aleatoriamente."""
    stack = ndvi_img.addBands(lst_img)
    pts = (stack.sample(region=geom,
                        scale=scale,
                        numPixels=n_points,
                        seed=42,
                        geometries=False)
                 .aggregate_array('NDVI')
                 .zip(stack.sample(region=geom,
                                   scale=scale,
                                   numPixels=n_points,
                                   seed=42,
                                   geometries=False)
                              .aggregate_array('LST')))
    # Convertir a numpy
    ndvi_lst = np.array(pts.getInfo()).reshape(-1, 2)
    # Filtrar valores nulos o negativos
    mask = (ndvi_lst[:, 0] > 0) & (ndvi_lst[:, 1] > -273.0)
    return ndvi_lst[mask]

def plot_scatter(ndvi_lst):
    """Genera y devuelve un objeto Figure con el scatter NDVI vs. LST."""
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.scatter(ndvi_lst[:, 0],
               ndvi_lst[:, 1],
               alpha=0.5, edgecolors='w', s=10)
    ax.set_xlabel('NDVI')
    ax.set_ylabel('Temperatura (°C)')
    ax.set_title('Comparación NDVI vs. Temperatura')
    ax.grid(True)
    fig.tight_layout()
    return fig

# ----------------------------------------------------------------------
# 5. Función de alto nivel que usa todo lo anterior
# ----------------------------------------------------------------------

def run_pipeline(start_date: str, end_date: str):
    """
    Ejecuta todo el flujo:
    1) autentica si es necesario
    2) descarga imágenes
    3) muestrea ≤10k píxeles
    4) devuelve figura Matplotlib
    """
    if not ee.data._credentials:
        init_ee()

    regions, expanded = get_regions()
    ndvi = get_ndvi(start_date, end_date, expanded)
    lst = get_lst(start_date, end_date, expanded)

    data = sample_images(ndvi, lst, regions)
    return plot_scatter(data)
