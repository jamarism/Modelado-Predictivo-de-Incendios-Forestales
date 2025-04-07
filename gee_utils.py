# gee_utils.py
# ------------------------------------------------------------
# Utilidades para Earth Engine + exportaciones con caché
# ------------------------------------------------------------
import os, time, ee, shutil

# ---------- 1.  Elegir carpeta de caché ----------
CACHE_DIR = "/content/gee_cache"     # fallback local
USING_DRIVE = False

try:
    # Solo existe en Colab; en entornos normales import falla
    from google.colab import drive, _ipython
    # get_ipython() solo funciona si hay kernel; evita AttributeError
    if _ipython.get_ipython() is not None:
        drive.mount('/content/drive', force_remount=False)
        CACHE_DIR = "/content/drive/My Drive/gee_cache"
        USING_DRIVE = True
        print("✅  Drive montado, usando caché en Drive:", CACHE_DIR)
except Exception as e:
    print("⚠️  No se montó Drive; usaré caché local:", CACHE_DIR, "(", e, ")")

os.makedirs(CACHE_DIR, exist_ok=True)

# ---------- 2.  Inicialización de Earth Engine ----------
def init_gee(service_acct_json=None):
    """
    Inicializa Google Earth Engine.
    - Si se pasa un dict con la clave de cuenta de servicio, usa credenciales de SA.
    - En Colab normal, pide autenticación OAuth una sola vez.
    """
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
            print("🔐  Autenticando con OAuth… sigue el popup")
            ee.Authenticate()
            ee.Initialize()

# ---------- 3.  Polling de tareas ----------
def wait_for_task(task, poll_interval=30):
    """
    Espera hasta que la tarea de exportación termine.
    Lanza RuntimeError si la tarea falla.
    """
    while task.active():
        print(f"⏳  Esperando… estado: {task.status()['state']}")
        time.sleep(poll_interval)
    status = task.status()
    if status['state'] != 'COMPLETED':
        raise RuntimeError(f"Tarea falló: {status}")
    print("✅  Tarea completada")

# ---------- 4.  Exportar con caché ----------
def export_if_needed(img, desc, region, scale, crs='EPSG:4326'):
    """
    Exporta la imagen a GeoTIFF en Drive **solo** si no existe en la caché.
    Devuelve la ruta al archivo .tif dentro de CACHE_DIR.
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
        fileFormat='GeoTIFF',
        crs=crs
    )
    task.start()
    wait_for_task(task)

    # ----- mover archivo desde Drive o fallback -----
    if USING_DRIVE:
        drive_path = f"/content/drive/My Drive/{desc}.tif"
        if not os.path.exists(drive_path):
            raise FileNotFoundError("Exportación terminada pero archivo no encontrado en Drive.")
        shutil.move(drive_path, tif_path)
        print(f"📥  Copiado a caché: {tif_path}")
    else:
        # Si no hay Drive, asumimos que la exportación fue a Google Cloud
        # o que el usuario descargará manualmente. Podrías añadir descarga aquí.
        raise RuntimeError("Exportación completada pero no hay Drive montado para copiar el archivo.")

    return tif_path
