"""
app.py
Interfaz Gradio para ejecutar la tubería NDVI‑LST con selección de fechas.
"""

import gradio as gr
from gee_utils import run_pipeline

with gr.Blocks(title="NDVI vs. LST – Cundinamarca & Boyacá") as demo:
    gr.Markdown(
        """
        # NDVI vs. Temperatura (MODIS)
        Selecciona el periodo de estudio y pulsa **Ejecutar**.
        El sistema muestrea hasta 10 000 píxeles para evitar sobrecargar Earth Engine.
        """
    )

    with gr.Row():
        start = gr.DateTime(label="Fecha inicial", value="2023-01-01")
        end   = gr.DateTime(label="Fecha final",   value="2023-12-31")
    run_btn = gr.Button("Ejecutar")

    output_plot = gr.Plot(label="Dispersión NDVI vs. LST")

    run_btn.click(fn=run_pipeline,
                  inputs=[start, end],
                  outputs=output_plot)

if __name__ == "__main__":
    demo.launch()
