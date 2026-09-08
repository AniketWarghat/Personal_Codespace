export interface SurveyRecord {
  id?: number;
  date: string;
  start_time: string;
  end_time: string;
  username: string;
  location: string;
  remarks1: string;
  remarks2: string;
  direction_raw: string;
  survey_type_raw: string;
  // Derived columns
  surveyor: string;
  contact: string;
  direction: string;
  survey_type: string;
  vehicle_type: string;
  origin: string;
  destination: string;
  likely_shift: string;
  trip_frequency: string;
  trip_purpose_or_commodity: string;
  occupancy: string | number;
  entry_duration_sec: number;
  survey_duration_mins: number;
  has_origin_destination: boolean;
  bad_od_entry: boolean;
  sample_quality_flags: string;
  sample_quality_suspicious: boolean;
  last_synced_at?: string;
  record_hash?: string;
}

export interface FilterOptionsResponse {
  minDate: string;
  maxDate: string;
  surveyTypes: string[];
  directions: string[];
  vehicleTypes: string[];
  surveyors: string[];
  totalRecords: number;
  lastSyncedAt: string;
}

export interface SurveyDataResponse {
  records: SurveyRecord[];
  totalCount: number;
  filteredCount: number;
  lastSyncedAt: string;
}

export interface GlobalFilterState {
  dateFrom: string;
  dateTo: string;
  timeFrom: string;
  timeTo: string;
  surveyTypes: string[];
  directions: string[];
  vehicleTypes: string[];
  surveyors: string[];
}

