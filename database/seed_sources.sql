-- GeoFlood AI - the two imagery sources the project uses. Safe to run more than once.
INSERT INTO satellite_sources (name, platform, sensor_type, provider, description) VALUES
  ('Sen1Floods11 hand-labeled chips', 'Sentinel-1', 'SAR', 'Cloud to Street (dataset), ESA (imagery)',
   'Dataset chips: VV and VH backscatter in dB, 512 x 512 pixels'),
  ('Sentinel-1 (Copernicus Data Space)', 'Sentinel-1', 'SAR', 'ESA / Copernicus',
   'Planned for Phase 28. Not integrated yet.')
ON CONFLICT (name) DO NOTHING;
