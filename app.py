import gradio as gr
import geopandas as gpd
import rasterio
import numpy as np
import matplotlib.pyplot as plt
import tempfile, os

from gee_utils import init_gee, ndvi_lst_median

init_gee()  # autentica una sola vez

def run(start_date, end_date):
    ndvi, lst, regions = ndvi_lst_median(start_date, end_date)

    # Exportación temporal a GeoTIFF dentro de Colab
    tmp = tempfile.mkdtemp()
    ndvi_path = os.path.join(tmp, 'ndvi.tif')
    lst_path  = os.path.join(tmp, 'lst.tif')

    region_coords = regions.geometry().bounds().getInfo()['coordinates']

    task1 = ee.batch.Export.image.toDrive(
        image=ndvi, description='tmp_ndvi',
        scale=250, region=region_coords, fileFormat='GeoTIFF')
    task2 = ee.batch.Export.image.toDrive(
        image=lst,  description='tmp_lst',
        scale=250, region=region_coords, fileFormat='GeoTIFF')
    task1.start(); task2.start()
    task1.status(); task2.status()  # en prod añadir polling

    # Aquí leerías los tiffs cuando estén listos…
    # Para demo, devolvemos una figura vacía
    fig, ax = plt.subplots()
    ax.set_title("Exportación en progreso…")
    return fig

demo = gr.Interface(
    fn=run,
    inputs=[gr.Text(value='2023-01-01', label='Fecha inicio'),
            gr.Text(value='2023-12-31', label='Fecha fin')],
    outputs=gr.Plot(label='NDVI vs LST'),
    title="Herramienta NDVI‑LST Boyacá / Cundinamarca",
    description="Calcula medianas MODIS y genera la gráfica de dispersión")

if __name__ == '__main__':
    demo.launch(share=True)   # genera URL pública en Colab :contentReference[oaicite:0]{index=0}

