import ee, os, time, tempfile
from google.colab import drive

drive.mount('/content/drive')   #  se monta una vez

TMP_DIR = "/content/drive/My Drive/gee_cache"   #  carpeta‑caché en Drive
os.makedirs(TMP_DIR, exist_ok=True)

def init_gee(service_acct_json=None):
    """Inicializa Earth Engine con OAuth (popup) o cuenta de servicio."""
    if service_acct_json:
        creds = ee.ServiceAccountCredentials(
            service_account=service_acct_json["client_email"],
            key_data=service_acct_json
        )
        ee.Initialize(creds)
    else:
        try:
            ee.Initialize()
        except Exception:
            ee.Authenticate()
            ee.Initialize()

def wait_for_task(task, poll_interval=30):
    """Bloquea hasta que la tarea termine o falle."""
    while task.active():
        print(f"⏳  Esperando… estado: {task.status()['state']}")
        time.sleep(poll_interval)
    status = task.status()
    if status['state'] != 'COMPLETED':
        raise RuntimeError(f"Tarea falló: {status}")
    print("✅  Tarea completada")

def export_if_needed(img, desc, region, scale, crs='EPSG:4326'):
    """Exporta a Drive solo si el .tif no existe en la caché."""
    tif_path = os.path.join(TMP_DIR, f"{desc}.tif")
    if os.path.exists(tif_path):
        print(f"🔁  Usando caché local {tif_path}")
        return tif_path

    task = ee.batch.Export.image.toDrive(
        image=img, description=desc, fileNamePrefix=desc,
        scale=scale, region=region, fileFormat='GeoTIFF', crs=crs)
    task.start()
    wait_for_task(task)

    # Copiar desde Drive al runtime
    drive_path = f"/content/drive/My Drive/{desc}.tif"
    if not os.path.exists(drive_path):
        raise FileNotFoundError("Exportación terminada pero archivo no encontrado en Drive.")
    os.rename(drive_path, tif_path)
    return tif_path
