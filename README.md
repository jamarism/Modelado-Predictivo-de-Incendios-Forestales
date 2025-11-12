# Modelado Predictivo de Incendios Forestales Relacionados con Sequías en Boyacá y Cundinamarca usando Análisis de Sensoramiento Remoto y Datos Climáticos

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/) [![Earth Engine](https://img.shields.io/badge/Google%20Earth%20Engine-JS%20%26%20Python-red)](https://earthengine.google.com/) [![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

Código y recursos de la tesis **“Modelado Predictivo de Incendios Forestales Relacionados con Sequías en Boyacá y Cundinamarca usando Análisis de Sensoramiento Remoto y Datos Climáticos”**. El repositorio integra:

* **App/Script GEE** para cálculo diario de **SPEI‑3** y un índice **FDCI** (combina LST, NDVI, TVDI y hazard por cobertura) con visualización de *hot spots* (FIRMS).
* **Suite Python** para **SPI, SPEI y NIFT** (10 parámetros de sequía + métricas), exportes GeoTIFF y análisis **GWSS** (correlación espacialmente ponderada SPEI incendios).

---

## 🔗 Enlaces

- **Repositorio (GEE):** https://earthengine.googlesource.com/users/jamarism/Remote_Sensing_Fire  
- **Asset SPEI-3 (parámetros):** https://code.earthengine.google.com/?asset=projects/ee-jamarism/assets/SPEI_Params_TS3

---

## 📁 Estructura del repositorio

```
.
├─ gee/
│  └─ daily_spei3_fdci.js        # Script GEE
├─ python/
│  ├─ SPI_SPEI_NIFT.py           # Suite unificada (SPI, SPEI, NIFT, exportes, GWSS)
│  ├─ FDCI.py                    # Dependencias Python
│  └─ README_python.md           # Guía de ejecución y ejemplos
├─ data/
│  └─ SPEI_Params_TS3            # Asset para ejecución de SPEI3 sin recalculo en GEE
├─ LICENSE
└─ README.md                     # Este archivo
```

---

## 🛰️ Script GEE (SPEI‑3, FDCI y Hotspots)

**Resumen funcional:**

* Carga colecciones **CHIRPS** (precip diaria), **MODIS LST** (Terra+Aqua), **MODIS PET** (MOD16A2), **MODIS NDVI** (MOD13Q1), **MCD12Q1** (cobertura). ROI = Cundinamarca + Boyacá (GAUL).
* Calcula **PET mensual ponderado** por solape de compuestos 8‑días y **balance hídrico** `D=P−PET` → **SPEI‑3** con **parámetros precalibrados** (imagen de 36 bandas: `xi, alpha, kappa`, por mes).
* Construye mosaicos con *gap‑fill* (ventanas **30/45/730 d** según variable) y deriva **TVDI** por líneas seca/húmeda parametrizadas por NDVI.
* **FDCI** (calibrado) = combinación ponderada:

  [\mathrm{FDCI} = \frac{w_{LST},LST_{SER}+ w_{NDVI},NDVI + w_{TVDI},TVDI + w_{HAZ},HAZ + 1}{4}]

  con pesos calibrados: `w_lst=0.918, w_ndvi=0.017, w_tvdi=0.465, w_haz=0.411`. **LST_SER** se normaliza con percentiles fijos (P02, P98) definidos regionalmente.
* Detección **Hot Spots** por umbrales: **FDCI ≥ 0.62** ∧ **SPEI‑3 ≤ 0.1** el mismo día. FIRMS (VIIRS 375 m) se usa como capa de referencia (confianza 0–100).
* UI en GEE con **textbox de fecha**, botón “Actualizar” y **leyendas**.

**Visualización propuesta:**

* `FDCI`: `min=0.25, max=0.75, palette=['green','yellow','orange','red']` (la alerta práctica empieza en ~0.62).
* `SPEI‑3`: paleta centrada en 0 (`-2.5..2.5`).
* `HotSpots`: magenta.

> **Assets requeridos**
>
> * `projects/ee-jamarism/assets/SPEI_Params_TS3` (36 bandas: `xi_01..12, alpha_01..12, kappa_01..12`), con **−9999** como *nodata* enmascarado.

---

## 🐍 Suite SPI–SPEI–NIFT (Python)

Archivo: `python/SPI_SPEI_NIFT.py`

### Dependencias

* Python 3.10+
* `earthengine-api`, `geemap==0.30.2`, `pandas`, `numpy`, `scipy`, `matplotlib`, `geopandas`, `rasterio`, `shapely`, `fiona`, `pyproj`, `scikit-learn`, `rpy2`, `gradio`.

> **R**: la suite llama paquetes `SPEI`, `zoo`, `data.table` y `GWmodel` mediante **rpy2**.

### Flujo típico (resumen)

1. **Exportes mensuales** desde GEE (hechos vía API desde el script Python):

   * `PR mensual (CHIRPS)` → `Grid5k_Mean_Prec.csv`
   * `(PR − PET) mensual (CHIRPS − MODIS)` → `Grid5k_WaterBalance_PRmPET.csv`
2. **SPI** (k = 1,3,6,12):

   * Convierte la tabla grilla×tiempo y ejecuta `SPEI::spi()` → `SPI_k_month.csv` (formato largo).
3. **SPEI** (k = 1,3,6,12):

   * Ejecuta `SPEI::spei()` sobre `PR−PET` y **exporta** además **coeficientes** (xi, alpha, kappa) por mes.
   * Genera **GeoTIFF multibanda (36 bandas)**: `SPEI_Params_TS{k}.tif` (alineado a la grilla CHIRPS), para subirlo a tu Asset y usarlo en GEE.
4. **NIFT** (10 parámetros + NIFT 0–100):

   * Calcula duración, severidad, porcentajes por clase de sequía, tendencias (Theil–Sen), precip media anual, normaliza y compone **NIFT** con pesos **editables**.
   * Exporta **GeoTIFF** por parámetro (P1..P10, normalizados y NIFT) para cada k.
5. **Validación y análisis**:

   * **SPEI Local vs CSIC/GEE** (serie temporal y métricas).
   * **SPEI vs ENSO (ONI)** con *lag* configurable.
   * **GWSS**: correlación local SPEI ↔ incendios (usar CSV mensual FIRMS y filtros por ENSO/años).
   * Paneles anuales (ρ local, significancia FDR, pendiente y resúmenes ECDF/Histogramas).

### Ejecución mínima (pseudopasos)

```bash
# 0) Autenticación EE (más de vez según Transport endpoint)
earthengine authenticate

# 1) SPI/SPEI desde CSVs exportados
python python/SPI_SPEI_NIFT.py

# 2) Subir SPEI_Params_TS{k}.tif como Asset en EE
#    y/o actualizar la ruta en el script GEE (PAR3 = ee.Image('projects/...'))

# 3) Ejecutar NIFT + GWSS
a) compute_nift(k_list_str="1,3,6,12")
b) gw_correlation_yearly_panels(k=3, lag=0, firms_csv_path=".../FIRMS_MONTH_*.csv", ...)
```

> **ROI y grilla**: el código usa la grilla **nativa CHIRPS (~0.05°)** para rasterizar salidas y garantizar consistencia con las exportaciones.

---

## 📜 Cómo citar

Trabajo final de maestría en curso:

```
@thesis{Amaris2026,
  author  = {Juan David Amaris Martínez},
  title   = {Modelado Predictivo de Incendios Forestales Relacionados con Sequías en Boyacá y Cundinamarca usando Análisis de Sensoramiento Remoto y Datos Climáticos},
  school  = {Universidad Nacional de Colombia},
  year    = {2026}
}

```
---

## ⚖️ Licencia

Este trabajo se distribuye bajo licencia **MIT**:

```
MIT License

Copyright (c) 2025 Juan David Amaris Martínez

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:
...
```

---

## 📝 Notas de reproducción

* Modificar rutas y renombrar Cloud Project
* Verifica que el Asset `SPEI_Params_TS3` exista.
* Ajustar percentiles **LST_P02/LST_P98** y pesos `w_*` si cambias la región.
* **FIRMS**: usa confianza ≥80 (editable). Las exportaciones mensuales se alinean a la **grilla CHIRPS**.
* **GWSS**: se usa `GWmodel::gwss` con **kernel bi-square** y **vecindario adaptativo** por defecto; el código calcula FDR con Benjamini–Hochberg.

---

## 📫 Contacto

* **Juan David Amaris Martínez**
  Universidad Nacional de Colombia, Sede Bogotá
  ✉️ [jamarism@unal.edu.co](mailto:jamarism@unal.edu.co)

---

