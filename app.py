import gradio as gr, rasterio, numpy as np, matplotlib.pyplot as plt
from gee_utils import init_gee, ndvi_lst_median, export_if_needed

init_gee()   # usa OAuth; para cuenta de servicio ver sección 4

def run(start_date, end_date, capas):
    ndvi_img, lst_img, regions = ndvi_lst_median(start_date, end_date)
    region = regions.geometry().bounds().getInfo()['coordinates']
    scale  = 250

    rutas = {}
    if "NDVI" in capas:
        rutas['NDVI'] = export_if_needed(ndvi_img, f"NDVI_{start_date}_{end_date}", region, scale)
    if "LST" in capas:
        rutas['LST']  = export_if_needed(lst_img,  f"LST_{start_date}_{end_date}",  region, scale)

    if len(rutas) < 2:
        return "Selecciona al menos dos capas", None

    # Leer rasters y graficar
    with rasterio.open(rutas['NDVI']) as src: ndvi = src.read(1).flatten()
    with rasterio.open(rutas['LST'])  as src: lst  = src.read(1).flatten()

    mask = (ndvi > 0) & (lst > 0)
    fig, ax = plt.subplots(figsize=(7,5))
    ax.scatter(ndvi[mask], lst[mask], s=4, alpha=0.4, edgecolors='none')
    ax.set_xlabel("NDVI"); ax.set_ylabel("°C"); ax.set_title("NDVI vs LST")
    ax.grid(True)
    return "Gráfico listo", fig

demo = gr.Interface(
    fn=run,
    inputs=[
        gr.Text(value="2023-01-01", label="Inicio"),
        gr.Text(value="2023-12-31", label="Fin"),
        gr.CheckboxGroup(choices=["NDVI", "LST"], value=["NDVI","LST"],
                         label="Capas a procesar")  # ✔ selección múltiple :contentReference[oaicite:1]{index=1}
    ],
    outputs=[gr.Textbox(), gr.Plot()],
    title="NDVI‑LST Boyacá / Cundinamarca",
    allow_flagging="never"
)

if __name__ == '__main__':
    demo.launch(share=True, debug=True, block=True)
