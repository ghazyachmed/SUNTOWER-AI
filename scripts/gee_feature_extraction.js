/**
 * SUNTOWER-AI — Google Earth Engine Script
 * Extracts geospatial features for telecom tower solar assessment
 * 
 * ASEAN GeoAI Fusion 2026 — HACK-ID-068
 * 
 * This script demonstrates real satellite data extraction from GEE.
 * It extracts GHI, elevation, NDVI, nighttime lights, and population
 * at each tower coordinate for the SUNTOWER-AI scoring engine.
 * 
 * To use: Upload tower coordinates as a GEE FeatureCollection (CSV/Shapefile),
 * then run this script to extract features at each point.
 */

// =================================================================
// 1. LOAD TOWER LOCATIONS
// =================================================================
// Option A: Upload your tower CSV as a GEE asset
// var towers = ee.FeatureCollection('users/YOUR_USERNAME/towers_indonesia');

// Option B: Define sample towers inline for demonstration
var towers = ee.FeatureCollection([
  ee.Feature(ee.Geometry.Point([107.6191, -6.9175]), {id: 1, name: 'Bandung_Center'}),
  ee.Feature(ee.Geometry.Point([107.5873, -6.9742]), {id: 2, name: 'Bandung_South'}),
  ee.Feature(ee.Geometry.Point([107.6870, -6.9522]), {id: 3, name: 'Gedebage'}),
  ee.Feature(ee.Geometry.Point([107.5500, -6.9000]), {id: 4, name: 'Cimahi'}),
  ee.Feature(ee.Geometry.Point([107.7100, -6.9300]), {id: 5, name: 'Rancaekek'}),
]);

// Define Area of Interest (West Java)
var aoi = ee.Geometry.Rectangle([107.4, -7.1, 107.8, -6.8]);

// =================================================================
// 2. SOLAR IRRADIANCE (GHI) — Global Solar Atlas
// =================================================================
// Using ERA5-Land surface solar radiation as GHI proxy
var era5 = ee.ImageCollection('ECMWF/ERA5_LAND/MONTHLY_AGGR')
  .filterDate('2022-01-01', '2022-12-31')
  .select('surface_solar_radiation_downwards_sum');

var annualGHI = era5.mean()
  .divide(1e6)  // Convert J/m² to MJ/m²
  .divide(3.6)  // Convert MJ to kWh
  .rename('ghi_kwh_m2_day');

// =================================================================
// 3. ELEVATION & SLOPE — SRTM 30m
// =================================================================
var srtm = ee.Image('USGS/SRTMGL1_003');
var elevation = srtm.select('elevation');
var slope = ee.Terrain.slope(srtm);

// =================================================================
// 4. POPULATION DENSITY — WorldPop
// =================================================================
var worldpop = ee.ImageCollection('WorldPop/GP/100m/pop')
  .filterDate('2020-01-01', '2020-12-31')
  .filter(ee.Filter.eq('country', 'IDN'))
  .mosaic()
  .rename('population');

// =================================================================
// 5. NIGHTTIME LIGHTS — VIIRS DNB
// =================================================================
var viirs = ee.ImageCollection('NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG')
  .filterDate('2022-01-01', '2022-12-31')
  .select('avg_rad');

var annualNTL = viirs.mean().rename('nightlight');

// =================================================================
// 6. LAND COVER — ESA WorldCover 10m
// =================================================================
var worldcover = ee.Image('ESA/WorldCover/v200/2021')
  .select('Map')
  .rename('landcover');

// =================================================================
// 7. VEGETATION (NDVI) — Sentinel-2
// =================================================================
var s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
  .filterBounds(aoi)
  .filterDate('2022-01-01', '2022-12-31')
  .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20));

var ndvi = s2.map(function(img) {
  return img.normalizedDifference(['B8', 'B4']).rename('ndvi');
}).mean();

// =================================================================
// 8. EXTRACT FEATURES AT TOWER LOCATIONS
// =================================================================

// Stack all layers
var featureStack = elevation
  .addBands(slope.rename('slope'))
  .addBands(annualGHI)
  .addBands(worldpop)
  .addBands(annualNTL)
  .addBands(worldcover)
  .addBands(ndvi);

// Extract values at each tower point
var extracted = featureStack.reduceRegions({
  collection: towers,
  reducer: ee.Reducer.mean(),
  scale: 100  // 100m resolution for extraction
});

// Also compute population within 5km buffer
var pop5km = towers.map(function(feature) {
  var buffer = feature.geometry().buffer(5000);
  var popSum = worldpop.reduceRegion({
    reducer: ee.Reducer.sum(),
    geometry: buffer,
    scale: 100,
    maxPixels: 1e9
  });
  return feature.set('population_5km', popSum.get('population'));
});

// =================================================================
// 9. VISUALIZATION
// =================================================================

// Base map
Map.setCenter(107.62, -6.92, 11);

// GHI visualization
var ghiVis = {
  min: 4.0,
  max: 6.0,
  palette: ['#313695', '#4575b4', '#74add1', '#abd9e9', '#fee090', '#fdae61', '#f46d43', '#d73027']
};
Map.addLayer(annualGHI.clip(aoi), ghiVis, 'Solar Irradiance (GHI)', true);

// Nighttime lights
Map.addLayer(annualNTL.clip(aoi), {min: 0, max: 60, palette: ['black', 'purple', 'yellow', 'white']},
  'Nighttime Lights (VIIRS)', false);

// Population
Map.addLayer(worldpop.clip(aoi), {min: 0, max: 5000, palette: ['white', 'yellow', 'orange', 'red']},
  'Population Density', false);

// NDVI
Map.addLayer(ndvi.clip(aoi), {min: 0, max: 0.8, palette: ['#d73027', '#fee08b', '#1a9850']},
  'Vegetation (NDVI)', false);

// Tower locations
Map.addLayer(towers, {color: '#fbbf24'}, 'Tower Locations');

// =================================================================
// 10. EXPORT RESULTS
// =================================================================

// Export extracted features as CSV
Export.table.toDrive({
  collection: extracted,
  description: 'SUNTOWER_Tower_Features',
  fileFormat: 'CSV',
  selectors: ['id', 'name', 'elevation', 'slope', 'ghi_kwh_m2_day',
              'population', 'nightlight', 'landcover', 'ndvi']
});

// Export population within 5km
Export.table.toDrive({
  collection: pop5km,
  description: 'SUNTOWER_Population_5km',
  fileFormat: 'CSV',
  selectors: ['id', 'name', 'population_5km']
});

print('SUNTOWER-AI GEE Feature Extraction');
print('Towers loaded:', towers.size());
print('Sample extraction:', extracted.first());
print('');
print('Available layers:');
print('  - Solar Irradiance (GHI) from ERA5');
print('  - Elevation & Slope from SRTM 30m');
print('  - Population from WorldPop 2020');
print('  - Nighttime Lights from VIIRS 2022');
print('  - Land Cover from ESA WorldCover');
print('  - Vegetation (NDVI) from Sentinel-2');
