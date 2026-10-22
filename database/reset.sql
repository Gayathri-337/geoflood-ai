-- GeoFlood AI - DEVELOPMENT ONLY: deletes every GeoFlood table and all its data.
DROP TABLE IF EXISTS
    emergency_actions, flood_reports, critical_infrastructure, agricultural_areas,
    affected_roads, affected_villages, reference_features, flood_zones, flood_analysis,
    satellite_images, disaster_events, satellite_sources, users
CASCADE;
