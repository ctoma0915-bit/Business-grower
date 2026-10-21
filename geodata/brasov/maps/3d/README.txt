Brașov County - 3D relief sections
==================================

sections/BV50-<sheet>.glb      one 3D block per 1:50,000 topographic sheet (20 x 15 km, 50 m mesh,
                               true scale), draped with the topographic map, with bridges, tunnels,
                               power lines, cable cars / ski lifts and dams as separate objects
sections/BV-overview.glb       the whole county (200 m mesh)
sections/*_satellite.jpg       Sentinel-2 satellite image for the same footprint (optional drape)
viewer.html, lib/, index.json  the 3D viewer, works offline
index.json                     list of sections: bounds, elevation range, what each one contains

Open a model
------------
* Blender (3.0 or newer): File > Import > glTF 2.0 (.glb/.gltf). The terrain and each kind of
  infrastructure are separate objects; tunnels sit inside the hill, switch on X-ray (Alt+Z) to see
  them. For 3D printing, select the terrain and File > Export > STL.
* In a browser, without installing anything: drag the .glb onto https://gltf-viewer.donmccurdy.com
  or https://sandbox.babylonjs.com
* The viewer in this folder (needs Python): open a terminal in this folder, run
      python -m http.server
  and open http://localhost:8000/viewer.html  (browsers do not load models from a plain file)

Coordinates
-----------
Metres, Stereo 70 (EPSG:3844). X = easting - west edge of the sheet, -Z = northing - north edge,
Y = elevation (EGM2008). Each model stores its sheet, CRS and origin in the terrain node's
"extras"; the infrastructure nodes' "extras" list every feature (name, road number, length,
height above ground, rock over a tunnel).

Bridge deck and tunnel heights are modelled from the elevation model (OpenStreetMap has no
levels): good for seeing what crosses what and roughly how high or deep, not for design.

Sources: Copernicus DEM GLO-30 (DLR/Airbus); OpenStreetMap contributors / Overture Maps (ODbL);
Meta & WRI canopy height (CC BY 4.0); contains modified Copernicus Sentinel-2 data 2025.
