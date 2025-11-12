/**
* Copyright (c) 2025
* 
* Autor: Juan David Amaris Martínez
* Afiliación: Universidad Nacional de Colombia, Sede Bogotá
* Contacto: [jamarism@unal.edu.co](mailto:jamarism@unal.edu.co)
* 
* Licencia: MIT.
* 
* Descripción general:
* - Prepara colecciones (CHIRPS, MODIS LST/MODIS PET/MODIS NDVI/MCD12Q1) y un ROI (Cundinamarca + Boyacá). 
* - Define funciones auxiliares pvar Pm ara mosaicos con relleno por ventana móvil, PET mensual ponderado, balance hídrico, suma móvil y SPEI con parámetros mensuales pre-calibrados. 
* - Calcula, para una fecha objetivo, SPEI-3 (como mosaico de los últimos 90 días) y un índice FDCI con pesos calibrados, además de TVDI y una capa HAZARD por cobertura. 
* - Carga detecciones FIRMS de ese día, identifica Hot Spots por umbrales FDCI/SPEI y visualiza resultados. 
*/
// =================== 1) Assets y Colecciones Globales ===================
// Parámetros mensuales (xi, alpha, kappa) para SPEI-3 (12 meses x 3 parámetros); -9999 indica nodata.
var PAR3 = ee.Image('projects/ee-jamarism/assets/SPEI_Params_TS3')
  .updateMask(ee.Image('projects/ee-jamarism/assets/SPEI_Params_TS3').neq(-9999));

// LST diaria MODIS (Terra + Aqua), banda LST_Day_1km (escala 0.02 Kelvin).
var LST_col = ee.ImageCollection('MODIS/061/MOD11A1').select('LST_Day_1km')
                .merge(ee.ImageCollection('MODIS/061/MYD11A1').select('LST_Day_1km'));

// Precipitación diaria CHIRPS (mm/día).
var CH_col  = ee.ImageCollection('UCSB-CHG/CHIRPS/DAILY').select('precipitation');

// PET MODIS 8-días (MOD16A2GF; kg/m^2/8d ~ mm/8d). Se pondera por solapamiento dentro del mes.
// var MOD_col = ee.ImageCollection('MODIS/061/MOD16A2GF').select('PET');
var MOD_col = ee.ImageCollection('MODIS/061/MOD16A2').select('PET');

// NDVI quincenal (MOD13Q1; escala 0.0001).
var NDVI_col= ee.ImageCollection('MODIS/061/MOD13Q1').select('NDVI');

// Cobertura de la tierra anual (MCD12Q1; LC_Type1, esquema IGBP).
var LC_col  = ee.ImageCollection('MODIS/061/MCD12Q1').select('LC_Type1');

// Proyección de referencia (CHIRPS) para reproyecciones de respaldo.
var chProj = CH_col.first().projection();

// ROI: Cundinamarca + Boyacá (GAUL nivel 1).
var ADM1 = ee.FeatureCollection('FAO/GAUL/2015/level1');
var ROI = ADM1
  .filter(ee.Filter.eq('ADM0_NAME', 'Colombia'))
  .filter(ee.Filter.inList('ADM1_NAME', ['Cundinamarca', 'Boyacá', 'Boyaca']))
  .geometry();


// =================== 2) FUNCIONES AUXILIARES ===================
/**
* createGapFilledMosaic
* 
* Crea un mosaico con relleno por ventana: busca imágenes en [targetDate - lookbackDays, targetDate]
* y devuelve el mosaico más reciente; si no hay imágenes, retorna una imagen vacía con la banda dada. 
* 
* @param {ee.ImageCollection} collection - Colección a mosaicar.
* @param {ee.Date} targetDate - Fecha objetivo (inclusive).
* @param {Number} lookbackDays - Ventana en días hacia atrás.
* @param {String} bandName - Nombre de banda de salida.
* @return {ee.Image} Imagen mosaico (o vacía) con nombre de banda bandName.
*/
function createGapFilledMosaic(collection, targetDate, lookbackDays, bandName) {
  targetDate = ee.Date(targetDate);
  var startDate = targetDate.advance(-lookbackDays, 'day');

  var recentImages = collection
    .filterDate(startDate, targetDate.advance(1, 'day'))
    .sort('system:time_start', false); // más reciente primero

  var mosaic   = recentImages.mosaic().rename(bandName);
  var fallback = ee.Image(0).updateMask(0).rename(bandName).reproject(chProj);

  // --- Reporte a consola ---
  var n = recentImages.size();

  var report = ee.Algorithms.If(
    n.gt(0),
    ee.Dictionary({
      layer: bandName,
      target: targetDate.format('YYYY-MM-dd'),
      used: ee.Date(ee.Image(recentImages.first()).get('system:time_start')).format('YYYY-MM-dd'),
      days_back: targetDate.difference(
        ee.Date(ee.Image(recentImages.first()).get('system:time_start')), 'day'
      ).int()
    }),
    ee.Dictionary({
      layer: bandName,
      target: targetDate.format('YYYY-MM-dd'),
      used: 'fallback(empty)',
      window_days: lookbackDays
    })
  );

  print('GapFill', report);

  return ee.Image(ee.Algorithms.If(n.gt(0), mosaic, fallback));
}


/**
* petMonthlyWeighted
* 
* Integra PET MOD16A2GF de 8 días al mes calendario, ponderando por días de solapamiento
* de cada compuesto en el intervalo mensual exacto. Retorna PET mensual en mm/mes. 
* 
* @param {ee.Date} mStart - Inicio de mes.
* @param {ee.Date} mEnd   - Fin de mes (exclusivo).
* @param {ee.ImageCollection} MOD - Colección MOD16A2GF (PET 8d).
* @return {ee.Image} Imagen PET mensual con propiedad system:time_start = mStart.
*/
function petMonthlyWeighted(mStart, mEnd, MOD){
  var coll = MOD.filterDate(mStart, mEnd);
  var weighted = coll.map(function(im){
    var imStart = ee.Date(im.get('system:time_start')), imEnd = imStart.advance(8, 'day');
    var overStart = ee.Date(ee.Number(imStart.millis()).max(mStart.millis()));
    var overEnd = ee.Date(ee.Number(imEnd.millis()).min(mEnd.millis()));
    var overlapDays = ee.Number(overEnd.difference(overStart, 'day')).max(0);
    var weight = overlapDays.divide(8);
    return im.multiply(0.1).multiply(weight).rename('PET'); // 0.1 para convertir a mm aproximado.
  });
  return ee.Image(ee.Algorithms.If(
    weighted.size().gt(0),
    ee.ImageCollection(weighted).sum().rename('PET'),
    ee.Image(0).updateMask(0).rename('PET').reproject(chProj)
  )).set('system:time_start', mStart.millis());
}

/**
* balanceMonthly
* 
* Calcula el balance hídrico mensual D = P - PET, preservando las marcas temporales mensuales. 
* 
* @param {ee.ImageCollection} P_ic - Precipitación mensual (banda 'P').
* @param {ee.ImageCollection} PET_ic - PET mensual (banda 'PET').
* @return {ee.ImageCollection} Colección con banda 'D' y system:time_start mensual.
*/
function balanceMonthly(P_ic, PET_ic){
  return P_ic.map(function(p){
    var t0  = ee.Date(p.get('system:time_start'));
    var pet = PET_ic.filterDate(t0, t0.advance(1,'month')).first();
    pet = ee.Image(ee.Algorithms.If(pet, pet, ee.Image(0).reproject(p.projection()).rename('PET')));
    return p.select('P').subtract(pet.select('PET')).rename('D').set('system:time_start', t0);
  });
}

/**
* rollingSum
* 
* Suma móvil de ventana k sobre una colección temporal ordenada; preserva la fecha del último elemento
* de cada ventana como system:time_start. 
* 
* @param {ee.ImageCollection} ic - Colección con banda escalar a sumar.
* @param {Number} k - Tamaño de ventana (número de pasos).
* @return {ee.ImageCollection} Colección con banda 'Dk'.
*/
function rollingSum(ic, k){
  ic = ic.sort('system:time_start');
  var L = ic.toList(ic.size());
  var n = L.size();
  return ee.ImageCollection(ee.Algorithms.If(n.gte(k),
    ee.ImageCollection(ee.List.sequence(ee.Number(k).subtract(1), n.subtract(1)).map(function(idx){
      idx = ee.Number(idx);
      var imgs = ee.List.sequence(idx.subtract(ee.Number(k).subtract(1)), idx)
                        .map(function(i){ return ee.Image(L.get(ee.Number(i))); });
      return ee.ImageCollection.fromImages(imgs).sum().rename('Dk')
        .set('system:time_start', ee.Image(L.get(idx)).get('system:time_start'));
    })),
    ee.ImageCollection([]) // si no hay suficientes meses, devuelve colección vacía
  ));
}


/**
* pickParamsByIndex
* 
* Selecciona las bandas de parámetros (xi, alpha, kappa) para el mes de la fecha dada
* desde una imagen apilada (12 bandas por parámetro). 
* 
* @param {ee.Image} paramsImg - Imagen con 36 bandas (12 por parámetro).
* @param {ee.Date} date - Fecha cuyo mes define los índices.
* @return {ee.Image} Imagen con bandas 'xi', 'alpha', 'kappa'.
*/
function pickParamsByIndex(paramsImg, date){
  var m = ee.Number(date.get('month'));
  var idx0  = m.subtract(1), idxAl = idx0.add(12), idxKa = idx0.add(24);
  var names = paramsImg.bandNames();
  return ee.Image.cat([
    paramsImg.select(ee.String(names.get(idx0))).rename('xi'),
    paramsImg.select(ee.String(names.get(idxAl))).rename('alpha'),
    paramsImg.select(ee.String(names.get(idxKa))).rename('kappa')
  ]);
}

/**
* speiFromParams
* 
* Convierte una colección de balances acumulados (Dk) a SPEI usando parámetros mensuales
* de una distribución logística generalizada (GLO) y la aproximación inversa a normal estándar. 
* 
* @param {ee.ImageCollection} Dk_ic - Colección con banda 'Dk'.
* @param {ee.Image} paramsImg - Imagen con parámetros mensuales (xi, alpha, kappa).
* @return {ee.ImageCollection} Colección con banda 'SPEI' y tiempos heredados.
*/
function speiFromParams(Dk_ic, paramsImg){
  return Dk_ic.map(function(img){
    var date = ee.Date(img.get('system:time_start'));
    var pars = pickParamsByIndex(paramsImg, date); // xi, alpha, kappa
    
    var Dk = img.select('Dk');
    var xi = pars.select('xi');
    var alpha = pars.select('alpha');
    var kappa = pars.select('kappa');

    // CDF GLO: F(x) = 1 / (1 + (1 - kappa*(x - xi)/alpha)^(1/kappa))
    var one = ee.Image(1.0);
    var u = Dk.subtract(xi).divide(alpha);                     // u = (Dk - xi)/alpha
    var base = one.subtract(kappa.multiply(u)).max(1e-9);      // base = (1 - kappa*u), restringida > 0
    var inv_kappa = one.divide(kappa);                         // 1/kappa
    var F = one.divide(one.add(base.pow(inv_kappa)));          // F(x)

    // Conversión a cuantil z ~ N(0,1) (Abramowitz & Stegun). Se usa P=1-F y clamp para estabilidad.
    var P = one.subtract(F).clamp(1e-6, 1 - 1e-6);
    var left = P.lte(0.5);
    var p_for_t = ee.Image(1).subtract(P).where(left, P);
    var t = p_for_t.log().multiply(-2).sqrt();

    var c0=2.515517, c1=0.802853, c2=0.010328, d1=1.432788, d2=0.189269, d3=0.001308;
    var z = t.expression(
      't - (c0 + c1*t + c2*t*t)/(1 + d1*t + d2*t*t + d3*t*t*t)',
      {t:t,c0:c0,c1:c1,c2:c2,d1:d1,d2:d2,d3:d3}
    );
    return z.where(left.not(), z.multiply(-1)).rename('SPEI').set('system:time_start', date);
  });
}


// =================== 3) FUNCIÓN DE CÁLCULO DE IMAGEN DIARIA ===================
// Usa pesos calibrados para FDCI y rellenos temporales razonables por variable.
/**
* calculateDailyStack
* 
* Para una fecha objetivo:
* - Calcula SPEI-3: P y PET mensuales del último año, D, suma móvil k=3, SPEI, y mosaico de 90 días. 
* - Construye LST, NDVI y LC por mosaicos con ventanas (30/45/730 días), recalibra unidades. 
* - Deriva TVDI por líneas seca/húmeda parametrizadas por NDVI; construye HAZARD por remapeo LC. 
* - Normaliza LST por percentiles fijos y compone FDCI con pesos calibrados. 
* - Devuelve una imagen con bandas SPEI3 y FDCI, con time_start = fecha objetivo. 
* 
* @param {ee.Date} date - Fecha objetivo.
* @return {ee.Image} Imagen con bandas ['SPEI3','FDCI'].
*/
function calculateDailyStack(date) {
  date = ee.Date(date);

  // --- Cálculo SPEI3 ---
  var start_spei = date.advance(-1, 'year');
  var end_spei   = date.advance(1, 'day');
  var nMonths = end_spei.difference(start_spei, 'month').toInt();
  var monthsSeq = ee.List.sequence(0, nMonths.subtract(1));

  // Precipitación y PET mensuales dentro de la ventana anual.
  var CH = CH_col.filterDate(start_spei, end_spei);
  var MOD = MOD_col.filterDate(start_spei, end_spei);

  // P mensual (suma diaria en cada mes) con fallback enmascarado
  var Pm = ee.ImageCollection.fromImages(monthsSeq.map(function(mOff){
    var mStart = start_spei.advance(ee.Number(mOff), 'month');
    var sub = CH.filterDate(mStart, mStart.advance(1, 'month'));
    var img = ee.Image(ee.Algorithms.If(
      sub.size().gt(0),
      sub.sum(),
      ee.Image(0).updateMask(0).reproject(chProj)
    )).rename('P')
      .set('system:time_start', mStart.millis());
    return img;
  })).sort('system:time_start');

  // PET mensual ponderado por solape de compuestos 8-días.
  var PETm = ee.ImageCollection.fromImages(monthsSeq.map(function(mOff){
    var mStart = start_spei.advance(ee.Number(mOff), 'month');
    return petMonthlyWeighted(mStart, mStart.advance(1, 'month'), MOD);
  })).sort('system:time_start');

  // D mensual y suma móvil a 3 meses; conversión a SPEI con parámetros precalibrados.
  var D  = balanceMonthly(Pm, PETm);
  var D3 = rollingSum(D, 3);
  var SPEI3 = speiFromParams(D3, PAR3);

  // SPEI3 más reciente por relleno de 90 días (último disponible).
  var SPEI3m = createGapFilledMosaic(SPEI3, date, 90, 'SPEI').rename('SPEI3');

  // --- Cálculo Variables FDCI ---
  // Mosaicos con ventanas razonables para reducir nodata y ruido temporal.
  var LST_img = createGapFilledMosaic(LST_col, date, 30, 'LST_Day_1km');
  var NDVI_img= createGapFilledMosaic(NDVI_col, date, 45, 'NDVI');
  var LC_img  = createGapFilledMosaic(LC_col, date, 730, 'LC_Type1');
  
  // Conversión de unidades: LST a °C (0.02 K - 273.15); NDVI sin escala; LC categórica.
  var LSTc   = LST_img.multiply(0.02).subtract(273.15).rename('LST');
  var NDVIu  = NDVI_img.multiply(0.0001).rename('NDVI');
  var LC     = LC_img.rename('LC');
  
  // TVDI parametrizado por NDVI (línea húmeda y seca lineales).
  var a1 = 8.06,  b1 = 0.22, a2 = -11.41, b2 = 48.03;
  var Ts_wet = NDVIu.multiply(a1).add(b1);
  var Ts_dry = NDVIu.multiply(a2).add(b2);
  var TVDI = LSTc.subtract(Ts_wet).divide(Ts_dry.subtract(Ts_wet)).clamp(0,1).rename('TVDI');
  
  // HAZARD por clase de cobertura (LC_Type1 IGBP) con pesos empíricos.
  var lcVals    = [1, 2, 3, 4, 5, 6, 7, 8, 9,10,11,12,13,14,15,16,17];
  var lcWeights = [0.85,0.6,0.6,0.6,0.82,0.72,0.4,0.8,0.8,0.5,0.1,0.35,0.05,0.48,0.3,0.12,0];
  var HAZARD = LC.remap(lcVals, lcWeights, 0).rename('HAZARD');
  
  // Normalización simple de LST con percentiles predefinidos (ajustables por región).
  var LST_P02 = 10.9, LST_P98 = 37.2;
  var LST_SER = LSTc.subtract(LST_P02).divide(LST_P98 - LST_P02).clamp(0, 1).rename('LST_norm');
  
  // --- Cálculo FDCI (con pesos calibrados) ---
  // Pesos originales (comentario histórico):
  // var w_lst  = 1, w_ndvi = -1, w_tvdi = 1, w_haz  = 1;
  // Pesos calibrados (se asume que producen FDCI ya en escala adecuada sin normalización adicional).
  var w_lst  = 0.918, w_ndvi = 0.017, w_tvdi = 0.465, w_haz  = 0.411;

  var FDCI = LST_SER.multiply(w_lst)
    .add(NDVIu.multiply(w_ndvi))
    .add(TVDI.multiply(w_tvdi))
    .add(HAZARD.multiply(w_haz))
    .add(1.0)
    .divide(4.0)
    .rename('FDCI');

  // Salida: bandas SPEI3 y FDCI con fecha de la consulta.
  return ee.Image.cat([SPEI3m, FDCI]).set('system:time_start', date.millis());
}


// =================== 4) INTERFAZ DE USUARIO Y VISUALIZACIÓN ===================

// --- 4.1) Funciones para crear Leyendas ---

/**
 * Crea una barra de color para leyendas continuas.
 * @param {Object} visParams - Parámetros de visualización (min, max, palette).
 * @return {ui.Thumbnail}
 */

function makeColorBar(visParams) {
  var lon = ee.Image.pixelLonLat().select('longitude');
  var grad = lon.multiply(ee.Number(visParams.max).subtract(visParams.min))
                .add(visParams.min);
  return ui.Thumbnail({
    image: grad.visualize(visParams),                   
    params: {bbox: '0,0,1,0.1', dimensions: '100x10', format: 'png'},
    style: {stretch: 'horizontal', margin: '0px 8px', maxHeight: '20px'},
  });
}

/**
 * Crea un panel de leyenda para una variable continua.
 * @param {String} title - Título de la leyenda.
 * @param {Object} visParams - Parámetros de visualización (min, max, palette).
 * @return {ui.Panel}
 */
function makeContinuousLegend(title, visParams) {
  var titleLabel = ui.Label(title, {fontWeight: 'bold', margin: '4px 0'});
  var colorBar = makeColorBar(visParams);
  var minLabel = ui.Label(visParams.min, {margin: '0 0 0 8px'});
  var maxLabel = ui.Label(visParams.max, {margin: '0 0 0 0', textAlign: 'right', stretch: 'horizontal'});
  var labelsPanel = ui.Panel([minLabel, maxLabel], ui.Panel.Layout.flow('horizontal'));
  return ui.Panel([titleLabel, colorBar, labelsPanel], null, {padding: '4px 8px'});
}

/**
 * Crea un panel de leyenda para variables categóricas.
 * @param {String} title - Título de la leyenda.
 * @param {Object} categories - Diccionario {nombre: color}.
 * @return {ui.Panel}
 */
function makeCategoricalLegend(title, categories) {
  var panel = ui.Panel([ui.Label(title, {fontWeight: 'bold', margin: '4px 0'})], null, {padding: '4px 8px'});
  for (var key in categories) {
    var color = categories[key];
    var colorBox = ui.Label('', {
      backgroundColor: color,
      padding: '8px',
      margin: '0 4px 0 0'
    });
    var label = ui.Label(key, {margin: '4px 0 0 0'});
    panel.add(ui.Panel([colorBox, label], ui.Panel.Layout.flow('horizontal')));
  }
  return panel;
}

// --- 4.2) Función principal para actualizar el mapa ---

// Define los páneles de UI fuera de la función para que se puedan referenciar.
var panelControl = ui.Panel({
  layout: ui.Panel.Layout.flow('horizontal'),
  style: {position: 'top-center', padding: '8px'}
});
var txtFecha = ui.Textbox({
  placeholder: 'YYYY-MM-DD',
  value: '2024-01-24', // Fecha por defecto
  style: {width: '100px'}
});
var btnActualizar = ui.Button('Actualizar Mapa');
var panelLeyenda = ui.Panel({
  style: {position: 'bottom-left', padding: '8px 15px', width: '250px'}
});

/**
 * Función que se ejecuta al presionar el botón.
 * Limpia el mapa, lee la fecha, recalcula y añade las capas y leyendas.
 */
function actualizarMapa() {
  // Limpiar mapa y páneles
  Map.clear();
  panelLeyenda.clear();
  Map.add(panelControl); // Re-añadir el panel de control
  Map.add(panelLeyenda); // Re-añadir el panel de leyenda
  
  // 1) Obtener fecha de la UI
  var fechaStr = txtFecha.getValue();
  if (!fechaStr) {
    print('Error: La fecha no puede estar vacía.');
    return;
  }
  var targetDate = ee.Date(fechaStr);
  print('Calculando para la fecha:', targetDate.format('YYYY-MM-dd'));

  // 2) Calcular stack diario y recortar al ROI.
  var dailyStack = calculateDailyStack(targetDate);
  var fdci = dailyStack.select('FDCI').clip(ROI);
  var spei3 = dailyStack.select('SPEI3').clip(ROI);

  // 3) Cargar incendios (FIRMS) para la fecha.
  var firms = ee.ImageCollection('FIRMS')
              .filterDate(targetDate, targetDate.advance(1, 'day'))
              .filterBounds(ROI)
              .select('confidence')
              .max()
              .clip(ROI);

  // 4) Identificar Hot Spots por umbrales.
  var fdciThreshold = fdci.gte(0.62);
  var speiThreshold = spei3.lte(0.1);
  var hotSpots = fdciThreshold.and(speiThreshold).selfMask().rename('HotSpot');

  // 5) Definir Parámetros de Visualización
  var visFDCI = {min: 0.25, max: 0.75, palette: ['green', 'yellow', 'orange', 'red']};
  var visSPEI = {min: -2.5, max: 2.5, palette: ['darkred', 'red', 'yellow', 'white', 'cyan', 'blue', 'darkblue']};
  var visFIRMS = {min: 0, max: 100, palette: ['orange', 'red', 'purple']};
  var visHotSpots = {palette: ['#FF00FF']};

  // 6) Añadir Capas al Mapa
  Map.centerObject(ROI, 8);
  Map.addLayer(ROI, {color: 'grey', opacity: 0.5}, 'ROI (Cundinamarca y Boyacá)');
  Map.addLayer(spei3, visSPEI, 'SPEI-3 (mosaico más reciente)');
  Map.addLayer(fdci, visFDCI, 'FDCI (calibrado)');
  Map.addLayer(hotSpots, visHotSpots, 'Hot Spots (FDCI>=0.62 y SPEI<=0.1)');
  Map.addLayer(
  firms.updateMask(firms.gt(0)),
  {min: 0, max: 100, palette: ['orange', 'red', 'purple']},
  'Incendios FIRMS (confianza)'
);
  
  // 7) Construir y añadir Leyendas
  panelLeyenda.add(ui.Label('Leyendas', {fontWeight: 'bold', fontSize: '16px', margin: '0 0 4px 0'}));
  panelLeyenda.add(makeContinuousLegend('FDCI (Riesgo)', visFDCI));
  panelLeyenda.add(makeContinuousLegend('SPEI-3 (Sequía)', visSPEI));
  panelLeyenda.add(makeContinuousLegend('FIRMS (Confianza)', visFIRMS));
  panelLeyenda.add(makeCategoricalLegend('Zonas de Alerta', {
    'Hot Spot (FDCI/SPEI)': visHotSpots.palette[0]
  }));
}

// --- 4.3) Configuración de la Interfaz ---

// Añadir widgets al panel de control
panelControl.add(ui.Label('Fecha (YYYY-MM-DD):'));
panelControl.add(txtFecha);
panelControl.add(btnActualizar);

// Conectar el botón a la función de actualización
btnActualizar.onClick(actualizarMapa);

// Añadir los páneles al mapa
Map.add(panelControl);
Map.add(panelLeyenda);


// =================== 5) EJECUCIÓN INICIAL ===================

// Ejecutar la función una vez al cargar el script con la fecha por defecto.
actualizarMapa();
