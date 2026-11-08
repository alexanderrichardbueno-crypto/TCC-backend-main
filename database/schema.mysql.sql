-- PrevClima: esquema MySQL gerado a partir dos modelos atuais.
CREATE DATABASE IF NOT EXISTS prevclima CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE prevclima;

CREATE TABLE roles (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	code VARCHAR(32) NOT NULL, 
	display_name VARCHAR(64) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (code)
);

CREATE TABLE weather_stations (
	code VARCHAR(16) NOT NULL, 
	name VARCHAR(120) NOT NULL, 
	state VARCHAR(2), 
	kind VARCHAR(20) NOT NULL, 
	latitude NUMERIC(9, 6), 
	longitude NUMERIC(9, 6), 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (code), 
	CONSTRAINT ck_station_lat CHECK (latitude IS NULL OR latitude BETWEEN -90 AND 90), 
	CONSTRAINT ck_station_lon CHECK (longitude IS NULL OR longitude BETWEEN -180 AND 180)
);

CREATE INDEX ix_stations_state_name ON weather_stations (state, name);

CREATE TABLE station_observations (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	station_code VARCHAR(16) NOT NULL, 
	observed_at DATETIME NOT NULL, 
	period VARCHAR(10) NOT NULL, 
	temperature_c NUMERIC(6, 2), 
	minimum_c NUMERIC(6, 2), 
	maximum_c NUMERIC(6, 2), 
	humidity NUMERIC(5, 2), 
	precipitation_mm NUMERIC(9, 2), 
	wind_ms NUMERIC(6, 2), 
	source VARCHAR(32) NOT NULL, 
	imported_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_station_observation UNIQUE (station_code, observed_at, period), 
	CONSTRAINT ck_observation_humidity CHECK (humidity IS NULL OR humidity BETWEEN 0 AND 100), 
	CONSTRAINT ck_observation_rain CHECK (precipitation_mm IS NULL OR precipitation_mm >= 0), 
	CONSTRAINT ck_observation_wind CHECK (wind_ms IS NULL OR wind_ms >= 0), 
	CONSTRAINT ck_observation_period CHECK (period IN ('HOURLY', 'DAILY', 'MONTHLY')), 
	FOREIGN KEY(station_code) REFERENCES weather_stations (code) ON DELETE RESTRICT
);

CREATE INDEX ix_observations_time ON station_observations (observed_at);

CREATE TABLE users (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	public_code VARCHAR(24) NOT NULL, 
	name VARCHAR(120) NOT NULL, 
	email VARCHAR(254) NOT NULL, 
	password_hash VARCHAR(255) NOT NULL, 
	role_id INTEGER NOT NULL, 
	city VARCHAR(100), 
	state VARCHAR(2), 
	latitude NUMERIC(9, 6), 
	longitude NUMERIC(9, 6), 
	weather_notifications BOOL NOT NULL, 
	alert_sound BOOL NOT NULL, 
	dark_theme BOOL NOT NULL, 
	email_verified_at DATETIME, 
	is_active BOOL NOT NULL, 
	token_version INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_user_lat CHECK (latitude IS NULL OR latitude BETWEEN -90 AND 90), 
	CONSTRAINT ck_user_lon CHECK (longitude IS NULL OR longitude BETWEEN -180 AND 180), 
	CONSTRAINT ck_user_coordinates_pair CHECK ((latitude IS NULL AND longitude IS NULL) OR (latitude IS NOT NULL AND longitude IS NOT NULL)), 
	UNIQUE (public_code), 
	UNIQUE (email), 
	FOREIGN KEY(role_id) REFERENCES roles (id) ON DELETE RESTRICT
);

CREATE INDEX ix_users_name ON users (name);

CREATE INDEX ix_users_role_id ON users (role_id);

CREATE TABLE account_codes (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	user_id INTEGER NOT NULL, 
	purpose VARCHAR(16) NOT NULL, 
	code_hash VARCHAR(64) NOT NULL, 
	attempts INTEGER NOT NULL, 
	expires_at DATETIME NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_code_purpose CHECK (purpose IN ('VERIFY_EMAIL', 'RESET_PASSWORD')), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX ix_account_codes_user_purpose ON account_codes (user_id, purpose);

CREATE TABLE audit_events (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	actor_id INTEGER, 
	action VARCHAR(80) NOT NULL, 
	target_type VARCHAR(50) NOT NULL, 
	target_id VARCHAR(64) NOT NULL, 
	details JSON NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(actor_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_audit_target_created ON audit_events (target_type, target_id, created_at);

CREATE TABLE educational_contents (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	source_key VARCHAR(80), 
	author_id INTEGER, 
	title VARCHAR(180) NOT NULL, 
	body TEXT NOT NULL, 
	media_url VARCHAR(500), 
	reference_url VARCHAR(500) NOT NULL, 
	published_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (source_key), 
	FOREIGN KEY(author_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_education_published ON educational_contents (published_at);

CREATE TABLE forecasts (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	source_key VARCHAR(80), 
	created_by INTEGER, 
	city VARCHAR(100) NOT NULL, 
	state VARCHAR(2) NOT NULL, 
	latitude NUMERIC(9, 6), 
	longitude NUMERIC(9, 6), 
	`condition` VARCHAR(120) NOT NULL, 
	temperature_c NUMERIC(5, 2) NOT NULL, 
	minimum_c NUMERIC(5, 2) NOT NULL, 
	maximum_c NUMERIC(5, 2) NOT NULL, 
	humidity INTEGER NOT NULL, 
	wind_kmh NUMERIC(6, 2) NOT NULL, 
	rain_probability INTEGER NOT NULL, 
	severity VARCHAR(24) NOT NULL, 
	description TEXT, 
	polygon JSON, 
	source_name VARCHAR(120) NOT NULL, 
	source_url VARCHAR(500), 
	issued_at DATETIME NOT NULL, 
	valid_until DATETIME NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_forecast_validity CHECK (valid_until > issued_at), 
	CONSTRAINT ck_forecast_humidity CHECK (humidity BETWEEN 0 AND 100), 
	CONSTRAINT ck_forecast_rain CHECK (rain_probability BETWEEN 0 AND 100), 
	CONSTRAINT ck_forecast_lat CHECK (latitude IS NULL OR latitude BETWEEN -90 AND 90), 
	CONSTRAINT ck_forecast_lon CHECK (longitude IS NULL OR longitude BETWEEN -180 AND 180), 
	CONSTRAINT ck_forecast_coordinates_pair CHECK ((latitude IS NULL AND longitude IS NULL) OR (latitude IS NOT NULL AND longitude IS NOT NULL)), 
	UNIQUE (source_key), 
	FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_forecasts_coords_valid ON forecasts (latitude, longitude, valid_until);

CREATE INDEX ix_forecasts_location_valid ON forecasts (city, state, valid_until);

CREATE TABLE news (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	author_id INTEGER, 
	title VARCHAR(180) NOT NULL, 
	summary TEXT NOT NULL, 
	body TEXT NOT NULL, 
	source_url VARCHAR(500) NOT NULL, 
	image_url VARCHAR(500), 
	published_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(author_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_news_published ON news (published_at);

CREATE TABLE severe_forecasts (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	level INTEGER NOT NULL, 
	description VARCHAR(500) NOT NULL, 
	polygon JSON NOT NULL, 
	issued_at DATETIME NOT NULL, 
	valid_until DATETIME NOT NULL, 
	created_by INTEGER, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_severe_forecast_level CHECK (level BETWEEN 0 AND 4), 
	CONSTRAINT ck_severe_forecast_validity CHECK (valid_until > issued_at), 
	FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_severe_forecasts_valid ON severe_forecasts (valid_until);

CREATE TABLE weather_alerts (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	source_key VARCHAR(80), 
	created_by INTEGER, 
	origin VARCHAR(16) NOT NULL, 
	source_name VARCHAR(120) NOT NULL, 
	source_url VARCHAR(500), 
	validation_status VARCHAR(24) NOT NULL, 
	status_reason TEXT, 
	status_changed_by INTEGER, 
	status_changed_at DATETIME, 
	title VARCHAR(140) NOT NULL, 
	message TEXT NOT NULL, 
	event_type VARCHAR(40) NOT NULL, 
	severity VARCHAR(24) NOT NULL, 
	area_name VARCHAR(160) NOT NULL, 
	latitude NUMERIC(9, 6), 
	longitude NUMERIC(9, 6), 
	radius_km NUMERIC(7, 2), 
	polygon JSON, 
	recommendations JSON NOT NULL, 
	issued_at DATETIME NOT NULL, 
	valid_until DATETIME NOT NULL, 
	closed_at DATETIME, 
	deleted_at DATETIME, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_alert_validity CHECK (valid_until > issued_at), 
	CONSTRAINT ck_alert_lat CHECK (latitude IS NULL OR latitude BETWEEN -90 AND 90), 
	CONSTRAINT ck_alert_lon CHECK (longitude IS NULL OR longitude BETWEEN -180 AND 180), 
	CONSTRAINT ck_alert_coordinates_pair CHECK ((latitude IS NULL AND longitude IS NULL) OR (latitude IS NOT NULL AND longitude IS NOT NULL)), 
	CONSTRAINT ck_alert_radius CHECK (radius_km IS NULL OR radius_km > 0), 
	CONSTRAINT ck_alert_has_area CHECK (origin = 'INMET' OR polygon IS NOT NULL OR (latitude IS NOT NULL AND longitude IS NOT NULL AND radius_km IS NOT NULL)), 
	CONSTRAINT ck_alert_severity CHECK (severity IN ('LOW', 'MODERATE', 'HIGH', 'CRITICAL')), 
	CONSTRAINT ck_alert_validation_status CHECK (validation_status IN ('ACTIVE', 'FALSE_ALARM', 'NEEDS_CORRECTION')), 
	CONSTRAINT ck_alert_origin CHECK (origin IN ('MANUAL', 'INMET')), 
	UNIQUE (source_key), 
	FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE RESTRICT, 
	FOREIGN KEY(status_changed_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_alerts_active ON weather_alerts (valid_until, severity);

CREATE INDEX ix_alerts_validation ON weather_alerts (validation_status, valid_until);

CREATE TABLE alert_reads (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	user_id INTEGER NOT NULL, 
	alert_id INTEGER NOT NULL, 
	read_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_alert_read_user_alert UNIQUE (user_id, alert_id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(alert_id) REFERENCES weather_alerts (id) ON DELETE CASCADE
);

CREATE TABLE alert_reviews (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	alert_id INTEGER NOT NULL, 
	reviewer_id INTEGER NOT NULL, 
	previous_status VARCHAR(24) NOT NULL, 
	new_status VARCHAR(24) NOT NULL, 
	reason TEXT NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_alert_review_previous_status CHECK (previous_status IN ('ACTIVE', 'FALSE_ALARM', 'NEEDS_CORRECTION')), 
	CONSTRAINT ck_alert_review_new_status CHECK (new_status IN ('ACTIVE', 'FALSE_ALARM', 'NEEDS_CORRECTION')), 
	FOREIGN KEY(alert_id) REFERENCES weather_alerts (id) ON DELETE RESTRICT, 
	FOREIGN KEY(reviewer_id) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE INDEX ix_alert_reviews_alert_created ON alert_reviews (alert_id, created_at);

INSERT INTO roles (code, display_name) VALUES ('USER', 'Usuário'), ('METEOROLOGIST', 'Meteorologista');
