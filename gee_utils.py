import ee

def init_gee():
    try:
        ee.Initialize()
    except Exception:
        # En Colab se abre el popup de autenticación
        ee.Authenticate()
        ee.Initialize()

def get_regions():
    gaul = ee.FeatureCollection('FAO/GAUL/2015/level1')
    return gaul.filter(ee.Filter.Or(
        ee.Filter.eq('ADM1_NAME', 'Cundinamarca'),
        ee.Filter.eq('ADM1_NAME', 'Boyaca')
    ))

def ndvi_lst_median(start, end, buffer_km=10, scale=250):
    regions = get_regions()
    roi = regions.geometry().buffer(buffer_km * 1000)

    ndvi = (ee.ImageCollection('MODIS/061/MOD13Q1')
            .filterBounds(roi).filterDate(start, end)
            .select('NDVI').median().multiply(0.0001))

    lst = (ee.ImageCollection('MODIS/061/MOD11A1')
           .filterBounds(roi).filterDate(start, end)
           .select('LST_Day_1km').median()
           .multiply(0.02).subtract(273.15).rename('LST'))

    ndvi = ndvi.reproject(crs='EPSG:4326', scale=scale).clip(regions)
    lst  = lst .reproject(crs='EPSG:4326', scale=scale).clip(regions)
    return ndvi, lst, regions

