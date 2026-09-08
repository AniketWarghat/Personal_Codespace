-- PostgreSQL Schema for NeonDB: survey_records
-- Mirrored faithfully from app-2.py process_dataframe()

CREATE TABLE IF NOT EXISTS survey_records (
    id SERIAL PRIMARY KEY,
    -- Raw Fields
    date VARCHAR(50),
    start_time VARCHAR(50),
    end_time VARCHAR(50),
    username VARCHAR(100),
    location VARCHAR(255),
    remarks1 TEXT,
    remarks2 TEXT,
    direction_raw VARCHAR(100),
    survey_type_raw VARCHAR(100),
    raw_data_json JSONB,

    -- Derived Fields
    surveyor VARCHAR(150),
    contact VARCHAR(100),
    direction VARCHAR(100),
    survey_type VARCHAR(100),
    vehicle_type VARCHAR(100),
    origin TEXT,
    destination TEXT,
    likely_shift VARCHAR(100),
    trip_frequency VARCHAR(100),
    trip_purpose_or_commodity TEXT,
    occupancy VARCHAR(50),
    entry_duration_sec INTEGER DEFAULT 0,
    survey_duration_mins NUMERIC(10, 2) DEFAULT 0,
    has_origin_destination BOOLEAN DEFAULT FALSE,
    bad_od_entry BOOLEAN DEFAULT FALSE,
    sample_quality_flags TEXT,
    sample_quality_suspicious BOOLEAN DEFAULT FALSE,

    -- System Fields
    last_synced_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    record_hash VARCHAR(64) UNIQUE
);

-- Optimized query indexes for Global Filters & Route Handlers
CREATE INDEX IF NOT EXISTS idx_survey_date ON survey_records(date);
CREATE INDEX IF NOT EXISTS idx_survey_type ON survey_records(survey_type);
CREATE INDEX IF NOT EXISTS idx_survey_direction ON survey_records(direction);
CREATE INDEX IF NOT EXISTS idx_survey_vehicle_type ON survey_records(vehicle_type);
CREATE INDEX IF NOT EXISTS idx_survey_surveyor ON survey_records(surveyor);
CREATE INDEX IF NOT EXISTS idx_survey_record_hash ON survey_records(record_hash);

